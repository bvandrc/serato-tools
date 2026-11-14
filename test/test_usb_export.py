import os
import shutil
import unittest
from unittest import mock

from serato_tools import usb_export
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate

from test.helpers import temp_dir


class GetCrateFilesTestCase(unittest.TestCase):
    """get_crate_files matching, against temp Subcrates/SmartCrates folders."""

    def setUp(self):
        tmp = temp_dir(self)
        self.crate_dir = os.path.join(tmp, usb_export.Crate.DIR)
        self.smart_crate_dir = os.path.join(tmp, usb_export.SmartCrate.DIR)
        os.makedirs(self.crate_dir)
        os.makedirs(self.smart_crate_dir)
        for patch in (
            mock.patch.object(usb_export.Crate, "DIR_PATH", self.crate_dir),
            mock.patch.object(usb_export.SmartCrate, "DIR_PATH", self.smart_crate_dir),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _add_file(self, name: str, smart: bool = False):
        with open(os.path.join(self.smart_crate_dir if smart else self.crate_dir, name), "w", encoding="utf-8"):
            pass

    def _matched_names(self, pattern: str) -> set[str]:
        return {os.path.basename(f) for f in usb_export.get_crate_files(pattern)}

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

        shutil.copy("test/data/database_v2_test.bin", os.path.join(self.serato_dir, DatabaseV2.FILENAME))
        db = DatabaseV2(os.path.join(self.serato_dir, DatabaseV2.FILENAME))
        db.filter_tracks(lambda track: False)
        for path in (self.a, self.b, self.c):
            db.entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, db.get_relative_path(path))]))
        db.save()

        self.house = self.add_crate(Crate, "House", [self.a, self.a_again])
        self.deep = self.add_crate(SmartCrate, "Deep", [self.b])
        self.add_crate(Crate, os.path.join("Serato Stems", "Stems"), [self.a, self.c])
        with open(os.path.join(self.serato_dir, "neworder.pref"), "w", encoding="utf-8") as f:
            f.write("[begin record]\n[crate]House\n[crate]Stems\n[end record]\n")

        for patch in (
            mock.patch.object(usb_export, "LOCAL_SERATO_DIR", self.serato_dir),
            mock.patch.object(usb_export, "LOCAL_SERATO_DRIVE", os.path.splitdrive(tmp)[0]),
            mock.patch.object(usb_export, "print"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

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
        usb_export.copy_crates_to_usb([self.house, self.deep], self.drive, "Tracks", root_crate="USB")

        crates = os.path.join(self.drive, "_Serato_", Crate.DIR)
        self.assertEqual(sorted(os.listdir(crates)), ["Serato Stems", "USB%%Deep.crate", "USB%%House.crate"])
        self.assertEqual(Crate(os.path.join(crates, "USB%%House.crate")).get_track_paths(), ["Tracks/a.mp3"])
        # renamed to .crate, but its contents are still a smart crate's
        self.assertEqual(SmartCrate(os.path.join(crates, "USB%%Deep.crate")).get_track_paths(), ["Tracks/b.mp3"])
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

    def test_replaces_the_drives_library_and_skips_unchanged_tracks(self):
        usb_export.copy_crates_to_usb([self.house], self.drive, "Tracks")
        stale = self.dest("_Serato_", Crate.DIR, "Old.crate")
        open(stale, "wb").close()  # pylint: disable=consider-using-with

        with mock.patch.object(usb_export.shutil, "copy2") as copy2:
            usb_export.copy_crates_to_usb([self.house], self.drive, "Tracks")
        copy2.assert_not_called()
        self.assertFalse(os.path.exists(stale), "the drive's _Serato_ folder is replaced")
        self.assertTrue(os.path.exists(self.dest("_Serato_", Crate.DIR, "House.crate")))


class TestCase(unittest.TestCase):
    def _run_main(self, drive: str, system: str) -> str:
        """Runs the CLI with `--drive drive` as if on `system`, and returns the drive folder it exports to."""
        argv = ["serato_usb_export", "--drive", drive, "--crates", "*"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(usb_export.platform, "system", return_value=system),
            mock.patch.object(usb_export, "get_crate_files", return_value=[]),
            mock.patch.object(usb_export, "copy_crates_to_usb") as copy_crates_to_usb,
        ):
            usb_export.main()
        return copy_crates_to_usb.call_args.kwargs["dest_drive_dir"]

    def test_drive_letter_becomes_drive_root(self):
        self.assertEqual(self._run_main("E", "Windows"), "E:\\")

    def test_drive_folder_is_kept(self):
        self.assertEqual(self._run_main("/Volumes/USB", "Darwin"), "/Volumes/USB")


if __name__ == "__main__":
    unittest.main()
