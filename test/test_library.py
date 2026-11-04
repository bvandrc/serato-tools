import unittest
from unittest import mock
import os
import shutil
import subprocess
import sys
import tempfile

from serato_tools.library import Library

# library.py imports the installed package's classes, so build fixtures and patch with those
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.track_cues_v2 import TrackCuesV2
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

    def copy_analyzed_track(self, name: str) -> str:
        path = os.path.join(self.music_dir, name)
        shutil.copy("test/data/test_mp3.mp3", path)
        return path

    def db_values(self, field: DatabaseV2.Fields) -> dict[str, SeratoBinFile.Value]:
        """Each saved database track's value of `field`, by path, for the tracks that have it."""
        return {t.relpath: t.get_value(field) for t in DatabaseV2(self.db_file).get_tracks() if field in t.fields}

    def test_set_db_track_tags(self):
        track = self.copy_analyzed_track("Colored.mp3")
        other = self.copy_analyzed_track("Other.mp3")
        self.add_to_database(track, other)

        saved = self.saved_file_names()
        changed = Library(self.serato_dir).set_db_track_tags(
            track, color=TrackCuesV2.TrackColors.PURPLE, beatgrid_locked=True
        )

        self.assertTrue(changed)
        self.assertEqual(saved, [DatabaseV2.FILENAME], "database saved once")
        tags = TrackCuesV2(track)
        self.assertEqual(tags.get_track_color(), TrackCuesV2.TrackColors.PURPLE.value, "color set in tags")
        self.assertTrue(tags.is_beatgrid_locked(), "lock set in tags")
        relpath, other_relpath = DatabaseV2.get_relative_path(track), DatabaseV2.get_relative_path(other)
        colors, locks = self.db_values(DatabaseV2.Fields.COLOR), self.db_values(DatabaseV2.Fields.BEATGRID_LOCKED)
        self.assertEqual(colors[relpath], 0xBB99FF, "color set in db, as 0xRRGGBB")
        self.assertIs(locks[relpath], True, "lock set in db")
        self.assertNotIn(other_relpath, colors, "other track's color left alone")
        self.assertNotIn(other_relpath, locks, "other track's lock left alone")
        self.assertEqual(TrackCuesV2(other).get_track_color(), b"\xbb\xbb\xbb", "other track's file left alone")

    def test_set_db_tracks_tags_sets_each_its_own_values(self):
        red, blue = self.copy_analyzed_track("Red.mp3"), self.copy_analyzed_track("Blue.mp3")
        self.add_to_database(red, blue)

        saved = self.saved_file_names()
        Library(self.serato_dir).set_db_tracks_tags(
            {red: {"color": TrackCuesV2.TrackColors.RED}, blue: {"color": TrackCuesV2.TrackColors.BLUE1}}
        )

        self.assertEqual(saved, [DatabaseV2.FILENAME], "database saved once for every track")
        colors = self.db_values(DatabaseV2.Fields.COLOR)
        self.assertEqual(colors[DatabaseV2.get_relative_path(red)], 0xFF9999)
        self.assertEqual(colors[DatabaseV2.get_relative_path(blue)], 0x99BBFF)
        self.assertEqual(TrackCuesV2(red).get_track_color(), TrackCuesV2.TrackColors.RED.value)
        self.assertEqual(TrackCuesV2(blue).get_track_color(), TrackCuesV2.TrackColors.BLUE1.value)

    def test_set_db_track_tags_unchanged_skips_saving(self):
        track = self.copy_analyzed_track("Grey.mp3")
        self.add_to_database(track)
        library = Library(self.serato_dir)
        library.set_db_track_tags(track, color=TrackCuesV2.TrackColors.GREY)

        saved = self.saved_file_names()
        self.assertFalse(library.set_db_track_tags(track, color=TrackCuesV2.TrackColors.GREY))
        self.assertEqual(saved, [], "database not saved")

    def test_set_db_track_tags_creates_a_missing_tag(self):
        track = self.copy_analyzed_track("New.mp3")
        tags = TrackCuesV2(track)
        tags.delete()
        tags.save()
        self.add_to_database(track)

        Library(self.serato_dir).set_db_track_tags(track, color=TrackCuesV2.TrackColors.RED, beatgrid_locked=True)

        tags = TrackCuesV2(track)
        self.assertEqual(tags.get_track_color(), TrackCuesV2.TrackColors.RED.value, "color added to the file")
        self.assertTrue(tags.is_beatgrid_locked(), "lock added to the file")
        self.assertEqual(self.db_values(DatabaseV2.Fields.COLOR)[DatabaseV2.get_relative_path(track)], 0xFF9999)

    def test_set_db_track_tags_unknown_key_changes_nothing(self):
        track = self.copy_analyzed_track("Track.mp3")
        self.add_to_database(track)

        saved = self.saved_file_names()
        with self.assertRaises(ValueError):
            Library(self.serato_dir).set_db_tracks_tags(
                {track: {"color": TrackCuesV2.TrackColors.RED, "title": "x"}}  # type: ignore[typeddict-unknown-key]
            )
        self.assertEqual(saved, [], "database not saved")
        self.assertEqual(TrackCuesV2(track).get_track_color(), b"\xbb\xbb\xbb", "file not changed")

    def test_set_db_track_tags_without_track_tags_extra(self):
        # a fresh interpreter, with mutagen blocked as if the track_tags extra weren't installed
        code = """if True:
            import sys
            sys.modules["mutagen"] = None
            from serato_tools.library import Library
            library = Library(sys.argv[1])
            library.database  # the rest of Library still works
            try:
                library.set_db_track_tags("track.mp3", beatgrid_locked=True)
            except ImportError as error:
                print(error)
        """
        result = subprocess.run(
            [sys.executable, "-c", code, self.serato_dir], capture_output=True, text=True, check=True
        )
        self.assertIn('pip install "serato-tools[track_tags]"', result.stdout)


if __name__ == "__main__":
    unittest.main()
