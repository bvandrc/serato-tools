import unittest
from unittest import mock
import os
import shutil
import tempfile

from src.serato_tools.library import Library

# library.py imports the installed package's classes, so build fixtures and patch with those
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils.bin_file_base import SeratoBinFile


class TestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.serato_dir = os.path.join(self._tmp.name, "_Serato_")
        self.music_dir = os.path.join(self._tmp.name, "Music")
        for d in [self.serato_dir, self.music_dir]:
            os.mkdir(d)
        self.db_file = os.path.join(self.serato_dir, DatabaseV2.FILENAME)
        shutil.copy("test/data/database_v2_test.bin", self.db_file)

    def make_track(self, name: str) -> str:
        path = os.path.join(self.music_dir, name)
        open(path, "wb").close()
        return path

    def add_to_database(self, *tracks: str):
        db = DatabaseV2(self.db_file)
        for track in tracks:
            db.entries.append(
                (DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, DatabaseV2.get_relative_path(track))])
            )
        db.save()

    def make_crate(self, crate_class: type[Crate] | type[SmartCrate], name: str, tracks: list[str]):
        crates_dir = os.path.join(self.serato_dir, crate_class.DIR)
        os.makedirs(crates_dir, exist_ok=True)
        crate = crate_class(os.path.join(crates_dir, name + crate_class.EXTENSION))
        crate.add_tracks(tracks)
        crate.save()

    def track_paths(self, file: SeratoBinFile) -> list[str]:
        return type(file)(file.filepath).get_track_paths()

    def saved_file_names(self):
        """Patches every library file's save to also record the saved file's name, into the returned list."""
        saved: list[str] = []
        original_save = SeratoBinFile.save

        def record_save(file: SeratoBinFile, *args, **kwargs):
            saved.append(os.path.basename(file.filepath))
            original_save(file, *args, **kwargs)

        patcher = mock.patch.object(SeratoBinFile, "save", autospec=True, side_effect=record_save)
        patcher.start()
        self.addCleanup(patcher.stop)
        return saved

    def test_files_are_parsed_when_first_needed(self):
        library = Library(os.path.join(self._tmp.name, "does not exist"))
        with self.assertRaises(FileNotFoundError, msg="database parsed on first access, not on init"):
            _ = library.database

        library = Library(self.serato_dir)
        self.assertEqual(library.crates, [], "no Subcrates folder means no crates")
        self.assertEqual(library.smart_crates, [], "no SmartCrates folder means no smart crates")
        self.assertIs(library.database, library.database, "database parsed once")

    def test_rename_track_file(self):
        src, dest = self.make_track("Old.mp3"), os.path.join(self.music_dir, "New.mp3")
        self.add_to_database(src)
        self.make_crate(Crate, "With", [src])
        self.make_crate(Crate, "Without", [])
        self.make_crate(SmartCrate, "Smart", [src])

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        library.rename_track_file(src, dest)

        self.assertTrue(os.path.exists(dest) and not os.path.exists(src), "file renamed")
        self.assertCountEqual(saved, [DatabaseV2.FILENAME, "With.crate", "Smart.scrate"], "only files with track saved")
        old_path, new_path = DatabaseV2.get_relative_path(src), DatabaseV2.get_relative_path(dest)
        db_paths = self.track_paths(library.database)
        self.assertIn(new_path, db_paths, "db path updated")
        self.assertNotIn(old_path, db_paths, "db old path gone")
        for crate in [*library.crates, *library.smart_crates]:
            if os.path.basename(crate.filepath) != "Without.crate":
                self.assertEqual(self.track_paths(crate), [new_path], f"{crate.filepath} path updated")

    def test_rename_track_file_refuses_to_overwrite(self):
        src, dest = self.make_track("Old.mp3"), self.make_track("Taken.mp3")
        self.add_to_database(src)

        saved = self.saved_file_names()
        # os.rename silently overwrites on POSIX, unlike on Windows, so test with that
        with mock.patch("os.rename", side_effect=os.replace):
            Library(self.serato_dir).rename_track_file(src, dest)

        self.assertTrue(os.path.exists(src), "src left in place")
        self.assertEqual(saved, [], "nothing saved")

    def test_remove_track_files(self):
        removed, missing, kept = (
            self.make_track("Removed.mp3"),
            self.make_track("Missing.mp3"),
            self.make_track("Kept.mp3"),
        )
        self.add_to_database(removed, missing, kept)
        self.make_crate(Crate, "With", [removed, kept])
        self.make_crate(Crate, "Without", [kept])
        self.make_crate(SmartCrate, "Smart", [missing])
        os.remove(missing)

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        library.remove_track_files([removed, missing])

        self.assertFalse(os.path.exists(removed), "file deleted")
        self.assertTrue(os.path.exists(kept), "other file kept")
        self.assertCountEqual(saved, [DatabaseV2.FILENAME, "With.crate", "Smart.scrate"], "only files with track saved")
        kept_path = DatabaseV2.get_relative_path(kept)
        db_paths = self.track_paths(library.database)
        self.assertIn(kept_path, db_paths, "other track kept in db")
        for track in [removed, missing]:
            self.assertNotIn(DatabaseV2.get_relative_path(track), db_paths, f"{track} removed from db, even if missing")
        for crate in library.crates:
            self.assertEqual(self.track_paths(crate), [kept_path], f"{crate.filepath} has only the kept track")
        self.assertEqual(self.track_paths(library.smart_crates[0]), [], "missing track removed from smart crate")


if __name__ == "__main__":
    unittest.main()
