import os
import shutil
import subprocess
import sys
import unittest
import warnings
from unittest import mock

# library.py imports the installed package's classes, so build fixtures and patch with those
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.library import Library
from serato_tools.smart_crate import SmartCrate
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_text_frames import TrackTextFrames
from serato_tools.utils.bin_file_base import SeratoBinFile

from test.helpers import temp_dir, temp_mp3, untagged_mp3


class TestCase(unittest.TestCase):
    def setUp(self):
        tmp = temp_dir(self)
        self.serato_dir = os.path.join(tmp, "_Serato_")
        self.music_dir = os.path.join(tmp, "Music")
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
        """The track paths in `file` as saved, read again from disk rather than from its entries in memory."""
        return type(file)(file.filepath).get_track_paths()

    def saved_file_names(self):
        """Records the name of each library file written from now on, however it's saved, into the returned list."""
        saved: list[str] = []

        def record_write(file, *args, **kwargs):
            if "w" in (args[0] if args else kwargs.get("mode", "r")):
                saved.append(os.path.basename(file))
            return open(file, *args, **kwargs)  # pylint: disable=unspecified-encoding

        # every way of saving a bin file opens it for writing in its module
        patcher = mock.patch("serato_tools.utils.bin_file_base.open", side_effect=record_write, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        return saved

    def test_files_are_parsed_when_first_needed(self):
        library = Library(os.path.join(self.serato_dir, "does not exist"))
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
        renamed = library.rename_track_file(src, dest)

        self.assertTrue(renamed, "returns that it renamed")
        self.assertTrue(os.path.exists(dest) and not os.path.exists(src), "file renamed")
        self.assertCountEqual(saved, [DatabaseV2.FILENAME, "With.crate", "Smart.scrate"], "only files with track saved")
        old_path, new_path = DatabaseV2.get_relative_path(src), DatabaseV2.get_relative_path(dest)
        db_paths = self.track_paths(library.database)
        self.assertIn(new_path, db_paths, "db path updated")
        self.assertNotIn(old_path, db_paths, "db old path gone")
        for crate in [*library.crates, *library.smart_crates]:
            if os.path.basename(crate.filepath) != "Without.crate":
                self.assertEqual(self.track_paths(crate), [new_path], f"{crate.filepath} path updated")

    def test_rename_track_file_in_a_given_database(self):
        src, dest = self.make_track("Old.mp3"), os.path.join(self.music_dir, "New.mp3")
        self.add_to_database(src)
        db = DatabaseV2(self.db_file)
        db.entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, "Unsaved.mp3")]))

        saved = self.saved_file_names()
        Library(self.serato_dir, database=db).rename_track_file(src, dest)

        self.assertIn(DatabaseV2.get_relative_path(dest), db.get_track_paths(), "the given database updated")
        self.assertEqual(saved, [DatabaseV2.FILENAME], "and saved once")
        self.assertIn("Unsaved.mp3", self.track_paths(db), "with its unsaved changes, rather than reparsed")

    def test_rename_track_file_refuses_to_overwrite(self):
        src, dest = self.make_track("Old.mp3"), self.make_track("Taken.mp3")
        self.add_to_database(src)

        saved = self.saved_file_names()
        # os.rename silently overwrites on POSIX, unlike on Windows, so test with that
        with mock.patch("os.rename", side_effect=os.replace):
            renamed = Library(self.serato_dir).rename_track_file(src, dest)

        self.assertFalse(renamed, "returns that it didn't rename")
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

    def test_batch_writes_each_changed_file_once(self):
        first, second = self.make_track("First.mp3"), self.make_track("Second.mp3")
        removed = self.make_track("Removed.mp3")
        self.add_to_database(first, second, removed)
        self.make_crate(Crate, "With", [first, second])
        self.make_crate(Crate, "Without", [removed])

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        new_first, new_second = (os.path.join(self.music_dir, name) for name in ["New First.mp3", "New Second.mp3"])
        with library.batch():
            library.rename_track_file(first, new_first)
            library.rename_track_file(second, new_second)
            library.remove_track_files([removed])

            self.assertEqual(saved, [], "nothing written yet")
            self.assertTrue(os.path.exists(new_first), "track file renamed right away")
            self.assertFalse(os.path.exists(removed), "track file deleted right away")

        self.assertCountEqual(saved, [DatabaseV2.FILENAME, "With.crate", "Without.crate"], "each file written once")
        new_paths = [DatabaseV2.get_relative_path(p) for p in [new_first, new_second]]
        db_paths = self.track_paths(library.database)
        for path in new_paths:
            self.assertIn(path, db_paths, "db path updated")
        self.assertNotIn(DatabaseV2.get_relative_path(removed), db_paths, "track removed from db")
        # by name: crates are listed in directory order, which isn't sorted on every filesystem
        crate = next(c for c in library.crates if os.path.basename(c.filepath) == "With.crate")
        self.assertEqual(self.track_paths(crate), new_paths, "crate paths updated")

    def test_batch_saves_when_the_block_raises(self):
        src, dest = self.make_track("Old.mp3"), os.path.join(self.music_dir, "New.mp3")
        self.add_to_database(src)

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        with self.assertRaises(RuntimeError, msg="the exception still propagates"):
            with library.batch():
                library.rename_track_file(src, dest)
                raise RuntimeError("stopped partway")

        self.assertEqual(saved, [DatabaseV2.FILENAME])
        self.assertIn(DatabaseV2.get_relative_path(dest), self.track_paths(library.database), "points at renamed file")

    def test_nested_batch_saves_when_the_outermost_ends(self):
        first, second = self.make_track("First.mp3"), self.make_track("Second.mp3")
        self.add_to_database(first, second)

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        with library.batch():
            with library.batch():
                library.rename_track_file(first, os.path.join(self.music_dir, "New First.mp3"))
            self.assertEqual(saved, [], "inner batch doesn't save")
            library.rename_track_file(second, os.path.join(self.music_dir, "New Second.mp3"))

        self.assertEqual(saved, [DatabaseV2.FILENAME], "outer batch saves once")

    def test_save_serializes_each_parsed_file_once(self):
        track = self.make_track("Track.mp3")
        self.add_to_database(track)
        self.make_crate(Crate, "Crate", [track])

        library = Library(self.serato_dir)
        library.database.modify([{"field": DatabaseV2.Fields.GENRE, "files": [track], "func": lambda *args: "House"}])
        _ = library.crates
        with mock.patch.object(
            SeratoBinFile, "to_bytes", autospec=True, side_effect=SeratoBinFile.to_bytes
        ) as to_bytes:
            library.save()
        self.assertCountEqual(
            [os.path.basename(f.filepath) for f, in (c.args for c in to_bytes.call_args_list)],
            [DatabaseV2.FILENAME, "Crate.crate"],
            "the changed database and the unchanged crate, once each",
        )

    def test_save_writes_direct_changes(self):
        track = self.make_track("Track.mp3")
        self.add_to_database(track)

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        library.database.modify([{"field": DatabaseV2.Fields.GENRE, "files": [track], "func": lambda *args: "House"}])
        self.assertEqual(library.save(), [library.database.filepath])

        self.assertEqual(saved, [DatabaseV2.FILENAME])
        self.assertEqual(self.db_values(DatabaseV2.Fields.GENRE)[DatabaseV2.get_relative_path(track)], "House")

    def test_save_writes_a_passed_database_before_it_is_read(self):
        track = self.make_track("Track.mp3")
        self.add_to_database(track)
        database = DatabaseV2(self.db_file)
        database.modify([{"field": DatabaseV2.Fields.GENRE, "files": [track], "func": lambda *args: "House"}])

        saved = self.saved_file_names()
        library = Library(self.serato_dir, database=database)
        self.assertEqual(library.save(), [database.filepath])

        self.assertNotIn("database", vars(library), "save doesn't read library.database")
        self.assertEqual(saved, [DatabaseV2.FILENAME])
        self.assertEqual(self.db_values(DatabaseV2.Fields.GENRE)[DatabaseV2.get_relative_path(track)], "House")

    def test_save_skips_unchanged_and_unparsed_files(self):
        self.make_crate(Crate, "Crate", [self.make_track("Track.mp3")])

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        self.assertEqual(library.save(), [], "nothing parsed")
        self.assertNotIn("database", vars(library), "save doesn't parse anything")

        _ = library.database, library.crates
        self.assertEqual(library.save(), [], "nothing changed")
        self.assertEqual(saved, [])

    def copy_analyzed_track(self, name: str) -> str:
        """A copy of the test mp3, which has every Serato tag, as `name` in the music folder."""
        return temp_mp3(self, name, self.music_dir)

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

    def test_set_db_track_tags_text_frames(self):
        track = self.copy_analyzed_track("Text.mp3")
        self.add_to_database(track)
        # key: (value, ID3 frame, the frame's text, database field, its value)
        cases = {
            "title": ("A Title", "TIT2", "A Title", DatabaseV2.Fields.TITLE, "A Title"),
            "artist": ("An Artist", "TPE1", "An Artist", DatabaseV2.Fields.ARTIST, "An Artist"),
            "album": ("An Album", "TALB", "An Album", DatabaseV2.Fields.ALBUM, "An Album"),
            "genre": ("A Genre", "TCON", "A Genre", DatabaseV2.Fields.GENRE, "A Genre"),
            "key": ("8A", "TKEY", "8A", DatabaseV2.Fields.KEY, "8A"),
            "grouping": ("TAGGED", "TIT1", "TAGGED", DatabaseV2.Fields.GROUPING, "TAGGED"),
            "publisher": ("A Publisher", "TPUB", "A Publisher", DatabaseV2.Fields.PUBLISHER, "A Publisher"),
            "composer": ("A Composer", "TCOM", "A Composer", DatabaseV2.Fields.COMPOSER, "A Composer"),
            "year": ("2020", "TDRC", "2020", DatabaseV2.Fields.YEAR, "2020"),
            "remixer": ("A Remixer", "TPE4", "A Remixer", DatabaseV2.Fields.REMIXER, "A Remixer"),
            "track_number": (3, "TRCK", "3", DatabaseV2.Fields.TRACK_NUMBER, 3),
            "disc_number": (2, "TPOS", "2", DatabaseV2.Fields.DISC_NUMBER, 2),
        }

        Library(self.serato_dir).set_db_tracks_tags({track: {key: case[0] for key, case in cases.items()}})  # type: ignore

        frames = TrackTextFrames(track)
        relpath = DatabaseV2.get_relative_path(track)
        for key, (_, frame_id, frame_text, field, db_value) in cases.items():
            with self.subTest(key):
                self.assertEqual(frames.get(frame_id), frame_text, "file")
                self.assertEqual(self.db_values(field)[relpath], db_value, "database")

    def test_set_db_track_tags_comment(self):
        track = self.copy_analyzed_track("Comment.mp3")
        self.add_to_database(track)
        relpath = DatabaseV2.get_relative_path(track)
        library = Library(self.serato_dir)

        library.set_db_track_tags(track, comment="A Comment")
        self.assertEqual(TrackTextFrames(track).get(TrackTextFrames.Fields.COMMENT), "A Comment", "file")
        self.assertEqual(self.db_values(DatabaseV2.Fields.COMMENT)[relpath], "A Comment", "database")

        library.set_db_track_tags(track, comment="")
        self.assertIsNone(TrackTextFrames(track).get(TrackTextFrames.Fields.COMMENT), "removed from the file")
        self.assertNotIn(relpath, self.db_values(DatabaseV2.Fields.COMMENT), "removed from the database")

    def test_set_db_track_tags_in_a_batch_saves_the_database_when_it_ends(self):
        track = self.copy_analyzed_track("Colored.mp3")
        self.add_to_database(track)

        saved = self.saved_file_names()
        library = Library(self.serato_dir)
        with library.batch():
            self.assertTrue(library.set_db_track_tags(track, color=TrackCuesV2.TrackColors.PURPLE))
            self.assertEqual(saved, [], "database not written yet")
            self.assertEqual(
                TrackCuesV2(track).get_track_color(), TrackCuesV2.TrackColors.PURPLE.value, "file tagged right away"
            )

        self.assertEqual(saved, [DatabaseV2.FILENAME])
        self.assertEqual(self.db_values(DatabaseV2.Fields.COLOR)[DatabaseV2.get_relative_path(track)], 0xBB99FF)

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

    def test_set_db_track_tags_deletes_tags_v1_unless_told_not_to(self):
        for delete_tags_v1 in (True, False):
            with self.subTest(delete_tags_v1=delete_tags_v1), warnings.catch_warnings():
                # passed to each file's save, not to the deprecated parameter on its edits
                warnings.simplefilter("error", DeprecationWarning)
                track = self.copy_analyzed_track(f"Delete{delete_tags_v1}.mp3")
                self.add_to_database(track)

                Library(self.serato_dir).set_db_track_tags(
                    track, color=TrackCuesV2.TrackColors.RED, delete_tags_v1=delete_tags_v1
                )

                tagfile = TrackCuesV2(track).tagfile
                assert tagfile is not None
                self.assertEqual(f"GEOB:{TrackCuesV1.GEOB_KEY}" in tagfile, not delete_tags_v1)

    def test_set_db_track_tags_unchanged_skips_saving(self):
        track = self.copy_analyzed_track("Grey.mp3")
        self.add_to_database(track)
        library = Library(self.serato_dir)
        library.set_db_track_tags(track, color=TrackCuesV2.TrackColors.GREY)

        saved = self.saved_file_names()
        self.assertFalse(library.set_db_track_tags(track, color=TrackCuesV2.TrackColors.GREY))
        self.assertEqual(saved, [], "database not saved")

    def test_set_db_track_tags_creates_a_missing_tag(self):
        track = untagged_mp3(self, "New.mp3", self.music_dir)
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
                {track: {"color": TrackCuesV2.TrackColors.RED, "rating": 5}}  # type: ignore[typeddict-unknown-key]
            )
        self.assertEqual(saved, [], "database not saved")
        self.assertEqual(TrackCuesV2(track).get_track_color(), b"\xbb\xbb\xbb", "file not changed")

    def test_set_db_tracks_tags_failing_later_track_changes_nothing(self):
        first = self.copy_analyzed_track("First.mp3")
        self.add_to_database(first)
        batches = {
            "unreadable file": {
                first: {"color": TrackCuesV2.TrackColors.RED},
                "Second.flac": {"beatgrid_locked": True},
            },
            "bad value": {first: {"color": TrackCuesV2.TrackColors.RED}, first + "2": {"color": "red"}},
        }
        saved = self.saved_file_names()
        for name, tracks in batches.items():
            with self.subTest(name):
                with self.assertRaises((ValueError, AttributeError)):
                    Library(self.serato_dir).set_db_tracks_tags(tracks)  # type: ignore[arg-type]
                self.assertEqual(saved, [], "database not saved")
                self.assertEqual(TrackCuesV2(first).get_track_color(), b"\xbb\xbb\xbb", "first file not changed")

    def test_set_db_tracks_tags_with_no_values_doesnt_open_the_file(self):
        # an unsupported file type would raise when opened
        self.assertFalse(Library(self.serato_dir).set_db_tracks_tags({"Unopened.flac": {}}))

    def test_set_db_track_tags_track_not_in_database_warns(self):
        track = self.copy_analyzed_track("Unknown.mp3")

        with self.assertLogs(level="WARNING") as logs:
            changed = Library(self.serato_dir).set_db_track_tags(track, color=TrackCuesV2.TrackColors.RED)

        self.assertFalse(changed, "database unchanged")
        self.assertIn("isn't in the database", "\n".join(logs.output))
        self.assertEqual(TrackCuesV2(track).get_track_color(), TrackCuesV2.TrackColors.RED.value, "file still set")

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
