import os
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
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_text_frames import TrackTextFrames
from serato_tools.utils.bin_file_base import SeratoBinFile

from test.helpers import TEST_DATABASE, bin_file_writes, has_tags_v1, temp_copy, temp_dir, temp_mp3, untagged_mp3

relpath = DatabaseV2.get_relative_path


class TestCase(unittest.TestCase):
    def setUp(self):
        tmp = temp_dir(self)
        self.serato_dir = os.path.join(tmp, "_Serato_")
        self.music_dir = os.path.join(tmp, "Music")
        for d in [self.serato_dir, self.music_dir]:
            os.mkdir(d)
        self.db_file = temp_copy(self, TEST_DATABASE, DatabaseV2.FILENAME, self.serato_dir)

    def music_path(self, name: str) -> str:
        """The path of `name` in the music folder, whether or not it exists."""
        return os.path.join(self.music_dir, name)

    def make_track(self, name: str) -> str:
        """An empty file as `name` in the music folder."""
        path = self.music_path(name)
        open(path, "wb").close()
        return path

    def copy_analyzed_track(self, name: str) -> str:
        """A copy of the test mp3, which has every Serato tag, as `name` in the music folder."""
        return temp_mp3(self, name, self.music_dir)

    def add_to_database(self, *tracks: str):
        db = DatabaseV2(self.db_file)
        for track in tracks:
            db.entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, relpath(track))]))
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

    def db_values(self, field: DatabaseV2.Fields) -> dict[str, SeratoBinFile.Value]:
        """Each saved database track's value of `field`, by path, for the tracks that have it."""
        return {t.relpath: t.get_value(field) for t in DatabaseV2(self.db_file).get_tracks() if field in t.fields}

    def set_genre(self, database: DatabaseV2, track: str):
        """Sets `track`'s genre to House in `database`, without saving it."""
        database.modify([{"field": DatabaseV2.Fields.GENRE, "files": [track], "func": lambda *args: "House"}])

    def files_named(self, library: Library, names: list[str]) -> list[SeratoBinFile]:
        """The library's database and crates whose file names are in `names`."""
        return [
            f
            for f in [library.database, *library.crates, *library.smart_crates]
            if os.path.basename(f.filepath) in names
        ]

    def test_files_are_parsed_when_first_needed(self):
        library = Library(os.path.join(self.serato_dir, "does not exist"))
        with self.assertRaises(FileNotFoundError, msg="database parsed on first access, not on init"):
            _ = library.database

        library = Library(self.serato_dir)
        self.assertEqual(library.crates, [], "no Subcrates folder means no crates")
        self.assertEqual(library.smart_crates, [], "no SmartCrates folder means no smart crates")
        self.assertIs(library.database, library.database, "database parsed once")

    def test_rename_track_file(self):
        src, dest = self.make_track("Old.mp3"), self.music_path("New.mp3")
        self.add_to_database(src)
        self.make_crate(Crate, "With", [src])
        self.make_crate(Crate, "Without", [])
        self.make_crate(SmartCrate, "Smart", [src])

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        changed = library.rename_track_file(src, dest)

        self.assertTrue(os.path.exists(dest) and not os.path.exists(src), "file renamed")
        self.assertCountEqual(saved, [DatabaseV2.FILENAME, "With.crate", "Smart.scrate"], "only files with track saved")
        self.assertCountEqual(changed, [f.filepath for f in self.files_named(library, saved)], "returns those files")
        old_path, new_path = relpath(src), relpath(dest)
        db_paths = self.track_paths(library.database)
        self.assertIn(new_path, db_paths, "db path updated")
        self.assertNotIn(old_path, db_paths, "db old path gone")
        for crate in [*library.crates, *library.smart_crates]:
            if os.path.basename(crate.filepath) != "Without.crate":
                self.assertEqual(self.track_paths(crate), [new_path], f"{crate.filepath} path updated")

    def test_rename_track_file_in_a_given_database(self):
        src, dest = self.make_track("Old.mp3"), self.music_path("New.mp3")
        self.add_to_database(src)
        db = DatabaseV2(self.db_file)
        db.entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, "Unsaved.mp3")]))

        saved = bin_file_writes(self)
        Library(self.serato_dir, database=db).rename_track_file(src, dest)

        self.assertIn(relpath(dest), db.get_track_paths(), "the given database updated")
        self.assertEqual(saved, [DatabaseV2.FILENAME], "and saved once")
        self.assertIn("Unsaved.mp3", self.track_paths(db), "with its unsaved changes, rather than reparsed")

    def test_rename_track_file_refuses_to_overwrite(self):
        src = self.make_track("Old.mp3")
        self.add_to_database(src)
        saved = bin_file_writes(self)

        cases = {
            # os.rename silently overwrites on POSIX, unlike on Windows, so test with Windows' behaviour
            "dest exists": (self.make_track("Taken.mp3"), os.replace),
            # as on Windows, for a clash os.path.exists misses, such as a case change on some filesystems
            "os.rename finds a clash": (self.music_path("New.mp3"), FileExistsError),
        }
        for name, (dest, rename) in cases.items():
            with self.subTest(name):
                with mock.patch("os.rename", side_effect=rename), self.assertRaises(FileExistsError):
                    Library(self.serato_dir).rename_track_file(src, dest)

                self.assertTrue(os.path.exists(src), "src left in place")
                self.assertEqual(saved, [], "nothing saved")
                self.assertIn(relpath(src), self.track_paths(DatabaseV2(self.db_file)), "db unchanged")

    def test_rename_track_file_not_in_the_library(self):
        src, dest = self.make_track("Unimported.mp3"), self.music_path("New.mp3")

        saved = bin_file_writes(self)
        changed = Library(self.serato_dir).rename_track_file(src, dest)

        self.assertTrue(os.path.exists(dest) and not os.path.exists(src), "file still renamed")
        self.assertEqual(changed, [], "no library file changed")
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

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        result = library.remove_track_files([removed, missing])

        self.assertFalse(os.path.exists(removed), "file deleted")
        self.assertTrue(os.path.exists(kept), "other file kept")
        self.assertEqual(result.files_deleted, [removed], "lists only the file that was there to delete")
        self.assertCountEqual(saved, [DatabaseV2.FILENAME, "With.crate", "Smart.scrate"], "only files with track saved")
        self.assertCountEqual(result.library_files_changed, [f.filepath for f in self.files_named(library, saved)])
        kept_path = relpath(kept)
        db_paths = self.track_paths(library.database)
        self.assertIn(kept_path, db_paths, "other track kept in db")
        for track in [removed, missing]:
            self.assertNotIn(relpath(track), db_paths, f"{track} removed from db, even if missing")
        for crate in library.crates:
            self.assertEqual(self.track_paths(crate), [kept_path], f"{crate.filepath} has only the kept track")
        self.assertEqual(self.track_paths(library.smart_crates[0]), [], "missing track removed from smart crate")

    def test_batch_writes_each_changed_file_once(self):
        first, second = self.make_track("First.mp3"), self.make_track("Second.mp3")
        removed = self.make_track("Removed.mp3")
        self.add_to_database(first, second, removed)
        self.make_crate(Crate, "With", [first, second])
        self.make_crate(Crate, "Without", [removed])

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        new_first, new_second = (self.music_path(name) for name in ["New First.mp3", "New Second.mp3"])
        with library.batch():
            library.rename_track_file(first, new_first)
            library.rename_track_file(second, new_second)
            removed_result = library.remove_track_files([removed])

            self.assertEqual(saved, [], "nothing written yet")
            self.assertCountEqual(
                removed_result.library_files_changed,
                [f.filepath for f in self.files_named(library, [DatabaseV2.FILENAME, "Without.crate"])],
                "lists the files it changed, though they aren't written until the block ends",
            )
            self.assertTrue(os.path.exists(new_first), "track file renamed right away")
            self.assertFalse(os.path.exists(removed), "track file deleted right away")

        self.assertCountEqual(saved, [DatabaseV2.FILENAME, "With.crate", "Without.crate"], "each file written once")
        new_paths = [relpath(p) for p in [new_first, new_second]]
        db_paths = self.track_paths(library.database)
        for path in new_paths:
            self.assertIn(path, db_paths, "db path updated")
        self.assertNotIn(relpath(removed), db_paths, "track removed from db")
        # by name: crates are listed in directory order, which isn't sorted on every filesystem
        crate = next(c for c in library.crates if os.path.basename(c.filepath) == "With.crate")
        self.assertEqual(self.track_paths(crate), new_paths, "crate paths updated")

    def test_batch_saves_when_the_block_raises(self):
        src, dest = self.make_track("Old.mp3"), self.music_path("New.mp3")
        self.add_to_database(src)

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        with self.assertRaises(RuntimeError, msg="the exception still propagates"):
            with library.batch():
                library.rename_track_file(src, dest)
                raise RuntimeError("stopped partway")

        self.assertEqual(saved, [DatabaseV2.FILENAME])
        self.assertIn(relpath(dest), self.track_paths(library.database), "points at renamed file")

    def test_nested_batch_saves_when_the_outermost_ends(self):
        first, second = self.make_track("First.mp3"), self.make_track("Second.mp3")
        self.add_to_database(first, second)

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        with library.batch():
            with library.batch():
                library.rename_track_file(first, self.music_path("New First.mp3"))
            self.assertEqual(saved, [], "inner batch doesn't save")
            library.rename_track_file(second, self.music_path("New Second.mp3"))

        self.assertEqual(saved, [DatabaseV2.FILENAME], "outer batch saves once")

    def test_save_writes_direct_changes_serializing_each_parsed_file_once(self):
        track = self.make_track("Track.mp3")
        self.add_to_database(track)
        self.make_crate(Crate, "Crate", [track])

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        self.set_genre(library.database, track)
        _ = library.crates
        with mock.patch.object(
            SeratoBinFile, "to_bytes", autospec=True, side_effect=SeratoBinFile.to_bytes
        ) as to_bytes:
            self.assertEqual(library.save(), [library.database.filepath], "returns the files written")

        self.assertCountEqual(
            [os.path.basename(f.filepath) for f, in (c.args for c in to_bytes.call_args_list)],
            [DatabaseV2.FILENAME, "Crate.crate"],
            "the changed database and the unchanged crate, serialized once each",
        )
        self.assertEqual(saved, [DatabaseV2.FILENAME], "only the changed database written")
        self.assertEqual(self.db_values(DatabaseV2.Fields.GENRE)[relpath(track)], "House")

    def test_save_writes_a_passed_database_before_it_is_read(self):
        track = self.make_track("Track.mp3")
        self.add_to_database(track)
        database = DatabaseV2(self.db_file)
        self.set_genre(database, track)

        saved = bin_file_writes(self)
        library = Library(self.serato_dir, database=database)
        self.assertEqual(library.save(), [database.filepath])

        self.assertNotIn("database", vars(library), "save doesn't read library.database")
        self.assertEqual(saved, [DatabaseV2.FILENAME])
        self.assertEqual(self.db_values(DatabaseV2.Fields.GENRE)[relpath(track)], "House")

    def test_save_skips_unchanged_and_unparsed_files(self):
        self.make_crate(Crate, "Crate", [self.make_track("Track.mp3")])

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        self.assertEqual(library.save(), [], "nothing parsed")
        self.assertNotIn("database", vars(library), "save doesn't parse anything")

        _ = library.database, library.crates
        self.assertEqual(library.save(), [], "nothing changed")
        self.assertEqual(saved, [])

    def test_set_db_track_tags(self):
        track = self.copy_analyzed_track("Colored.mp3")
        other = self.copy_analyzed_track("Other.mp3")
        self.add_to_database(track, other)

        saved = bin_file_writes(self)
        result = Library(self.serato_dir).set_db_track_tags(
            track, color=TrackCuesV2.TrackColors.PURPLE, beatgrid_locked=True
        )

        self.assertTrue(result.database_changed)
        self.assertEqual(result.files_written, [track])
        self.assertEqual(saved, [DatabaseV2.FILENAME], "database saved once")
        tags = TrackCuesV2(track)
        self.assertEqual(tags.get_track_color(), TrackCuesV2.TrackColors.PURPLE.value, "color set in tags")
        self.assertTrue(tags.is_beatgrid_locked(), "lock set in tags")
        track_relpath, other_relpath = relpath(track), relpath(other)
        colors, locks = self.db_values(DatabaseV2.Fields.COLOR), self.db_values(DatabaseV2.Fields.BEATGRID_LOCKED)
        self.assertEqual(colors[track_relpath], 0xBB99FF, "color set in db, as 0xRRGGBB")
        self.assertIs(locks[track_relpath], True, "lock set in db")
        self.assertNotIn(other_relpath, colors, "other track's color left alone")
        self.assertNotIn(other_relpath, locks, "other track's lock left alone")
        self.assertEqual(TrackCuesV2(other).get_track_color(), b"\xbb\xbb\xbb", "other track's file left alone")

    def test_set_db_track_tags_text_frames(self):
        track = self.copy_analyzed_track("Text.mp3")
        self.add_to_database(track)
        # key: (value, ID3 frame, database field); the frame holds the value as text, and the database as it is
        cases = {
            "title": ("A Title", "TIT2", DatabaseV2.Fields.TITLE),
            "artist": ("An Artist", "TPE1", DatabaseV2.Fields.ARTIST),
            "album": ("An Album", "TALB", DatabaseV2.Fields.ALBUM),
            "genre": ("A Genre", "TCON", DatabaseV2.Fields.GENRE),
            "key": ("8A", "TKEY", DatabaseV2.Fields.KEY),
            "grouping": ("TAGGED", "TIT1", DatabaseV2.Fields.GROUPING),
            "publisher": ("A Publisher", "TPUB", DatabaseV2.Fields.PUBLISHER),
            "composer": ("A Composer", "TCOM", DatabaseV2.Fields.COMPOSER),
            "year": ("2020", "TDRC", DatabaseV2.Fields.YEAR),
            "remixer": ("A Remixer", "TPE4", DatabaseV2.Fields.REMIXER),
            "track_number": (3, "TRCK", DatabaseV2.Fields.TRACK_NUMBER),
            "disc_number": (2, "TPOS", DatabaseV2.Fields.DISC_NUMBER),
        }

        Library(self.serato_dir).set_db_tracks_tags({track: {key: case[0] for key, case in cases.items()}})  # type: ignore

        frames = TrackTextFrames(track)
        track_relpath = relpath(track)
        for key, (value, frame_id, field) in cases.items():
            with self.subTest(key):
                self.assertEqual(frames.get(frame_id), str(value), "file")
                self.assertEqual(self.db_values(field)[track_relpath], value, "database")

    def test_set_db_track_tags_comment(self):
        track = self.copy_analyzed_track("Comment.mp3")
        self.add_to_database(track)
        library = Library(self.serato_dir)

        library.set_db_track_tags(track, comment="A Comment")
        self.assertEqual(TrackTextFrames(track).get(TrackTextFrames.Fields.COMMENT), "A Comment", "file")
        self.assertEqual(self.db_values(DatabaseV2.Fields.COMMENT)[relpath(track)], "A Comment", "database")

        library.set_db_track_tags(track, comment="")
        self.assertIsNone(TrackTextFrames(track).get(TrackTextFrames.Fields.COMMENT), "removed from the file")
        self.assertNotIn(relpath(track), self.db_values(DatabaseV2.Fields.COMMENT), "removed from the database")

    def test_set_db_track_tags_in_a_batch_saves_the_database_when_it_ends(self):
        track = self.copy_analyzed_track("Colored.mp3")
        self.add_to_database(track)

        saved = bin_file_writes(self)
        library = Library(self.serato_dir)
        with library.batch():
            self.assertTrue(library.set_db_track_tags(track, color=TrackCuesV2.TrackColors.PURPLE).database_changed)
            self.assertEqual(saved, [], "database not written yet")
            self.assertEqual(
                TrackCuesV2(track).get_track_color(), TrackCuesV2.TrackColors.PURPLE.value, "file tagged right away"
            )

        self.assertEqual(saved, [DatabaseV2.FILENAME])
        self.assertEqual(self.db_values(DatabaseV2.Fields.COLOR)[relpath(track)], 0xBB99FF)

    def test_set_db_tracks_tags_sets_each_its_own_values(self):
        red, blue = self.copy_analyzed_track("Red.mp3"), self.copy_analyzed_track("Blue.mp3")
        self.add_to_database(red, blue)

        saved = bin_file_writes(self)
        Library(self.serato_dir).set_db_tracks_tags(
            {red: {"color": TrackCuesV2.TrackColors.RED}, blue: {"color": TrackCuesV2.TrackColors.BLUE1}}
        )

        self.assertEqual(saved, [DatabaseV2.FILENAME], "database saved once for every track")
        colors = self.db_values(DatabaseV2.Fields.COLOR)
        self.assertEqual(colors[relpath(red)], 0xFF9999)
        self.assertEqual(colors[relpath(blue)], 0x99BBFF)
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

                self.assertEqual(has_tags_v1(track), not delete_tags_v1)

    def test_set_db_tracks_tags_writes_only_what_changed(self):
        changed, unchanged = self.copy_analyzed_track("Changed.mp3"), self.copy_analyzed_track("Unchanged.mp3")
        self.add_to_database(changed, unchanged)
        library = Library(self.serato_dir)
        library.set_db_track_tags(unchanged, color=TrackCuesV2.TrackColors.GREY)

        saved = bin_file_writes(self)
        result = library.set_db_track_tags(unchanged, color=TrackCuesV2.TrackColors.GREY)
        self.assertFalse(result.database_changed)
        self.assertEqual(result.files_written, [], "file not written")
        self.assertEqual(saved, [], "database not saved")

        result = library.set_db_tracks_tags(
            {changed: {"color": TrackCuesV2.TrackColors.PURPLE}, unchanged: {"color": TrackCuesV2.TrackColors.GREY}}
        )
        self.assertTrue(result.database_changed)
        self.assertEqual(result.files_written, [changed], "lists only the file it wrote")

    def test_set_db_track_tags_creates_a_missing_tag(self):
        track = untagged_mp3(self, "New.mp3", self.music_dir)
        self.add_to_database(track)

        Library(self.serato_dir).set_db_track_tags(track, color=TrackCuesV2.TrackColors.RED, beatgrid_locked=True)

        tags = TrackCuesV2(track)
        self.assertEqual(tags.get_track_color(), TrackCuesV2.TrackColors.RED.value, "color added to the file")
        self.assertTrue(tags.is_beatgrid_locked(), "lock added to the file")
        self.assertEqual(self.db_values(DatabaseV2.Fields.COLOR)[relpath(track)], 0xFF9999)

    def test_set_db_track_tags_unknown_key_changes_nothing(self):
        track = self.copy_analyzed_track("Track.mp3")
        self.add_to_database(track)

        saved = bin_file_writes(self)
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
        saved = bin_file_writes(self)
        for name, tracks in batches.items():
            with self.subTest(name):
                with self.assertRaises((ValueError, AttributeError)):
                    Library(self.serato_dir).set_db_tracks_tags(tracks)
                self.assertEqual(saved, [], "database not saved")
                self.assertEqual(TrackCuesV2(first).get_track_color(), b"\xbb\xbb\xbb", "first file not changed")

    def test_set_db_tracks_tags_with_no_values_doesnt_open_the_file(self):
        # an unsupported file type would raise when opened
        result = Library(self.serato_dir).set_db_tracks_tags({"Unopened.flac": {}})
        self.assertFalse(result.database_changed)
        self.assertEqual(result.files_written, [])

    def test_set_db_track_tags_track_not_in_database_warns(self):
        track = self.copy_analyzed_track("Unknown.mp3")

        with self.assertLogs(level="WARNING") as logs:
            result = Library(self.serato_dir).set_db_track_tags(track, color=TrackCuesV2.TrackColors.RED)

        self.assertFalse(result.database_changed, "database unchanged")
        self.assertEqual(result.files_written, [track], "file still written")
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
