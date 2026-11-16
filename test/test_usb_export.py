# pylint: disable=protected-access
import os
import shutil
import unittest
from typing import Any
from unittest import mock

from serato_tools import usb_export
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate

from test.helpers.bin_files import TEST_DATABASE
from test.helpers.files import read_bytes, temp_dir


class GetCrateFilesTestCase(unittest.TestCase):
    """get_crate_files matching, against temp Subcrates/SmartCrates folders."""

    def setUp(self):
        # stands in for a library's _Serato_ folder
        self.serato_dir = temp_dir(self)
        self.crate_dir = os.path.join(self.serato_dir, usb_export.Crate.DIR)
        self.smart_crate_dir = os.path.join(self.serato_dir, usb_export.SmartCrate.DIR)
        os.makedirs(self.crate_dir)
        os.makedirs(self.smart_crate_dir)

    def _add_file(self, name: str, smart: bool = False):
        with open(os.path.join(self.smart_crate_dir if smart else self.crate_dir, name), "w", encoding="utf-8"):
            pass

    def _matched_names(self, pattern: str) -> set[str]:
        return {os.path.basename(f) for f in usb_export.get_crate_files(pattern, self.serato_dir)}

    def test_glob_is_tried_before_regex(self):
        # "house*" is also a valid regex whose .search() would match "housing"
        self._add_file("house.crate")
        self._add_file("housing.crate")
        self.assertEqual(self._matched_names("house*"), {"house.crate"})

    def test_glob_matches_both_crate_kinds(self):
        self._add_file("house.crate")
        self._add_file("house.scrate", smart=True)
        self.assertEqual(self._matched_names("*house*"), {"house.crate", "house.scrate"})

    def test_pattern_invalid_as_glob_match_falls_back_to_regex(self):
        self._add_file("deep.crate")
        self._add_file("house.crate")
        self._add_file("techno.crate")
        self.assertEqual(self._matched_names("deep|house"), {"deep.crate", "house.crate"})

    def test_non_crate_files_are_never_matched(self):
        self._add_file("house.crate")
        self._add_file(".DS_Store")
        self._add_file("notes.txt")
        self.assertEqual(self._matched_names("*"), {"house.crate"})

    def test_missing_smart_crates_folder_is_no_smart_crates(self):
        self._add_file("house.crate")
        os.rmdir(self.smart_crate_dir)
        self.assertEqual(self._matched_names("*"), {"house.crate"})

    def test_invalid_regex_with_no_glob_match_is_empty(self):
        self._add_file("house.crate")
        self.assertEqual(self._matched_names("*[techno*"), set())


class CopyCratesToUsbTestCase(unittest.TestCase):
    """copy_crates_to_usb on a small library in a temp folder, exported to another temp folder as the drive."""

    def setUp(self):
        tmp = temp_dir(self)
        self.music = os.path.join(tmp, "music")
        self.serato_dir = os.path.join(tmp, "_Serato_")
        self.drive = os.path.join(tmp, "drive")
        for folder in (os.path.join(self.music, "one"), os.path.join(self.music, "two"), self.serato_dir, self.drive):
            os.makedirs(folder)
        self.a, self.b, self.a_again, self.c = (
            self.add_track(os.path.join(self.music, *parts))
            for parts in (("one", "a.mp3"), ("one", "b.mp3"), ("two", "a.mp3"), ("one", "c.mp3"))
        )
        self.add_track(os.path.join(self.music, "one", "a.serato-stems"))

        shutil.copy(TEST_DATABASE, os.path.join(self.serato_dir, DatabaseV2.FILENAME))
        db = DatabaseV2(os.path.join(self.serato_dir, DatabaseV2.FILENAME))
        db.filter_tracks(lambda track: False)
        for path in (self.a, self.b, self.c):
            db._entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, db.get_relative_path(path))]))
        db.save()

        self.house = self.add_crate(Crate, "House", [self.a, self.a_again])
        self.deep = self.add_crate(SmartCrate, "Deep", [self.b])
        self.add_crate(Crate, os.path.join("Serato Stems", "Stems"), [self.a, self.c])
        with open(os.path.join(self.serato_dir, "neworder.pref"), "w", encoding="utf-8") as f:
            f.write("[begin record]\n[crate]House\n[crate]Stems\n[end record]\n")

        patch = mock.patch.object(usb_export, "print")
        patch.start()
        self.addCleanup(patch.stop)

    def export(self, crate_files: list[str], **kwargs: Any):
        """Exports `crate_files` from this test's library to its drive, under `Tracks`."""
        usb_export.copy_crates_to_usb(crate_files, self.drive, "Tracks", source_serato_dir=self.serato_dir, **kwargs)

    @staticmethod
    def add_track(path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            f.write(path)
        return path

    def add_crate(self, crate_class: type[Crate] | type[SmartCrate], name: str, tracks: list[str]) -> str:
        path = os.path.join(self.serato_dir, crate_class.DIR, name + crate_class.EXTENSION)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        crate = crate_class(path)
        crate.add_tracks(tracks)
        crate.save()
        return path

    def dest(self, *parts: str) -> str:
        return os.path.join(self.drive, *parts)

    def test_exports_crates_their_tracks_and_a_database_of_them(self):
        self.export([self.house, self.deep], root_crate="USB")

        crates = os.path.join(self.drive, "_Serato_", Crate.DIR)
        self.assertEqual(sorted(os.listdir(crates)), ["Serato Stems", "USB%%Deep.crate", "USB%%House.crate"])
        self.assertEqual(Crate(os.path.join(crates, "USB%%House.crate")).get_track_paths(), ["Tracks/a.mp3"])
        # a smart crate becomes a regular crate of its tracks
        self.assertEqual(Crate(os.path.join(crates, "USB%%Deep.crate")).get_track_paths(), ["Tracks/b.mp3"])
        self.assertEqual(
            Crate(os.path.join(crates, "Serato Stems", "Stems.crate")).get_track_paths(),
            ["Tracks/a.mp3"],
            "only the exported tracks",
        )

        db = DatabaseV2(self.dest("_Serato_", DatabaseV2.FILENAME))
        self.assertEqual(db.get_track_paths(), ["Tracks/a.mp3", "Tracks/b.mp3"], "only the exported tracks")
        self.assertEqual([t.get_value(DatabaseV2.Fields.PLAYED) for t in db.get_tracks()], [False, False])

        with open(self.dest("_Serato_", "neworder.pref"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "[begin record]\n[crate]USB%%House\n[crate]Stems\n[end record]\n")

        self.assertEqual(sorted(os.listdir(self.dest("Tracks"))), ["a.mp3", "a.serato-stems", "b.mp3"])
        with open(self.dest("Tracks", "a.mp3"), encoding="utf-8") as f:
            self.assertEqual(f.read(), self.a, "the first of the tracks with that filename")

    def test_logs_the_database_and_stems_crate_it_writes(self):
        with self.assertLogs("serato-tools", "INFO") as logs:
            self.export([self.house])
        messages = [record.getMessage() for record in logs.records]
        self.assertIn(f"created database file {self.dest('_Serato_', DatabaseV2.FILENAME)}", messages)
        self.assertIn(f"copied crate {self.dest('_Serato_', Crate.SERATO_STEMS_CRATE_PATH)}", messages)

    def test_replaces_the_drives_library_and_skips_unchanged_tracks(self):
        self.export([self.house])
        stale = self.dest("_Serato_", Crate.DIR, "Old.crate")
        open(stale, "wb").close()  # pylint: disable=consider-using-with

        with mock.patch.object(usb_export.shutil, "copy2") as copy2:
            self.export([self.house])
        copy2.assert_not_called()
        self.assertFalse(os.path.exists(stale), "the drive's _Serato_ folder is replaced")
        self.assertTrue(os.path.exists(self.dest("_Serato_", Crate.DIR, "House.crate")))

    def test_a_track_with_two_stems_files_raises(self):
        self.add_track(os.path.join(self.music, "one", "a.mp3.serato-stems"))
        with self.assertRaisesRegex(ValueError, "more than 1 stems file"):
            self.export([self.house])


class ExportFromAnotherDriveTestCase(unittest.TestCase):
    """copy_crates_to_usb from a library whose _Serato_ folder is on a drive of its own, not the home library."""

    def setUp(self):
        tmp = os.path.realpath(temp_dir(self))
        self.source_drive, self.dest_drive = os.path.join(tmp, "Source"), os.path.join(tmp, "USB")
        self.source_serato_dir = os.path.join(self.source_drive, "_Serato_")
        os.makedirs(os.path.join(self.source_serato_dir, Crate.DIR))
        os.makedirs(os.path.join(self.source_drive, "Music"))
        os.makedirs(self.dest_drive)
        self.db_file = os.path.join(self.source_serato_dir, DatabaseV2.FILENAME)
        shutil.copy(TEST_DATABASE, self.db_file)
        patch = mock.patch.object(usb_export, "print")
        patch.start()
        self.addCleanup(patch.stop)

    def make_source_library(self, track_names: list[str]) -> str:
        """Adds the tracks to the source drive, its database, and one crate, and returns the crate's path."""
        tracks: list[str] = []
        for name in track_names:
            path = os.path.join(self.source_drive, "Music", name)
            with open(path, "wb") as f:
                f.write(name.encode())
            tracks.append(path)
        db = DatabaseV2(self.db_file)
        for track in tracks:
            relpath = DatabaseV2.get_relative_path(track, db.track_path_root)
            db._entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, relpath)]))
        db.save()
        crate = Crate(os.path.join(self.source_serato_dir, Crate.DIR, "House.crate"))
        crate.add_tracks(tracks)
        crate.save()
        return crate.filepath

    def dest_paths(self) -> tuple[list[str], list[str]]:
        """The track paths in the drive's House crate and database."""
        dest_serato_dir = os.path.join(self.dest_drive, "_Serato_")
        return (
            Crate(os.path.join(dest_serato_dir, Crate.DIR, "House.crate")).get_track_paths(),
            DatabaseV2(os.path.join(dest_serato_dir, DatabaseV2.FILENAME)).get_track_paths(),
        )

    def export(self, crate_file: str, dest_tracks_dir: str = "Tracks"):
        usb_export.copy_crates_to_usb(
            [crate_file],
            dest_drive_dir=self.dest_drive,
            dest_tracks_dir=dest_tracks_dir,
            source_serato_dir=self.source_serato_dir,
        )

    def test_exports_from_a_library_in_a_home_folder(self):
        with mock.patch("os.path.ismount", return_value=False):
            crate_file = self.make_source_library(["A.mp3", "B.mp3"])
            source_crate_bytes = read_bytes(crate_file)
            self.export(crate_file)

        self.assertEqual(sorted(os.listdir(os.path.join(self.dest_drive, "Tracks"))), ["A.mp3", "B.mp3"])
        crate_paths, db_paths = self.dest_paths()
        self.assertEqual(crate_paths, ["Tracks/A.mp3", "Tracks/B.mp3"], "crate points at the copied tracks")
        self.assertCountEqual(db_paths, ["Tracks/A.mp3", "Tracks/B.mp3"], "database has only the copied tracks")
        self.assertEqual(read_bytes(crate_file), source_crate_bytes, "source crate left as it was")

    def test_exports_from_a_library_on_an_external_drive(self):
        source_drive = os.path.normcase(self.source_drive)
        with mock.patch("os.path.ismount", side_effect=lambda p: os.path.normcase(p) == source_drive):
            crate_file = self.make_source_library(["A.mp3", "B.mp3"])
            self.assertEqual(Crate(crate_file).get_track_paths(), ["Music/A.mp3", "Music/B.mp3"], "relative to drive")
            self.export(crate_file)

        self.assertEqual(sorted(os.listdir(os.path.join(self.dest_drive, "Tracks"))), ["A.mp3", "B.mp3"])
        crate_paths, db_paths = self.dest_paths()
        self.assertEqual(crate_paths, ["Tracks/A.mp3", "Tracks/B.mp3"], "crate points at the copied tracks")
        self.assertCountEqual(db_paths, ["Tracks/A.mp3", "Tracks/B.mp3"], "database has only the copied tracks")

    def test_tracks_folder_given_as_a_full_path_is_stored_relative_to_the_drive(self):
        with mock.patch("os.path.ismount", return_value=False):
            crate_file = self.make_source_library(["A.mp3"])
            self.export(crate_file, dest_tracks_dir=os.path.join(self.dest_drive, "DJ", "Tracks"))

        self.assertTrue(os.path.isfile(os.path.join(self.dest_drive, "DJ", "Tracks", "A.mp3")), "copied")
        self.assertEqual(self.dest_paths(), (["DJ/Tracks/A.mp3"], ["DJ/Tracks/A.mp3"]))


class TestCase(unittest.TestCase):
    def _run_main(self, drive: str, system: str = "Darwin", extra_args: tuple[str, ...] = ()) -> mock.Mock:
        """Runs the CLI with `--drive drive` and `extra_args` as if on `system`, and returns copy_crates_to_usb's mock."""
        argv = ["serato_usb_export", "--drive", drive, "--crates", "*", *extra_args]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(usb_export.platform, "system", return_value=system),
            mock.patch.object(usb_export, "get_crate_files", return_value=[]),
            mock.patch.object(usb_export, "copy_crates_to_usb") as copy_crates_to_usb,
        ):
            usb_export.main()
        return copy_crates_to_usb

    def test_drive_letter_becomes_drive_root(self):
        self.assertEqual(self._run_main("E", "Windows").call_args.kwargs["dest_drive_dir"], "E:\\")

    def test_drive_folder_is_kept(self):
        self.assertEqual(self._run_main("/Volumes/USB", "Darwin").call_args.kwargs["dest_drive_dir"], "/Volumes/USB")

    def test_source_defaults_to_the_home_library(self):
        copy_crates_to_usb = self._run_main("/Volumes/USB")
        self.assertEqual(copy_crates_to_usb.call_args.kwargs["source_serato_dir"], usb_export.LOCAL_SERATO_DIR)

    def test_source_library_is_passed_on(self):
        copy_crates_to_usb = self._run_main("/Volumes/USB", extra_args=("--source", "/Volumes/Library/_Serato_"))
        self.assertEqual(copy_crates_to_usb.call_args.kwargs["source_serato_dir"], "/Volumes/Library/_Serato_")


if __name__ == "__main__":
    unittest.main()
