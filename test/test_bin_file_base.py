import copy
import json
import os
import unittest
from unittest import mock

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate

# bin_file_base raises the installed package's DataTypeError, so catch that one
from serato_tools.utils.bin_file_base import DataTypeError, SeratoBinFile

from test.helpers.bin_files import TEST_CRATE, TEST_DATABASE, bin_file_writes
from test.helpers.files import read_bytes, read_text, temp_copy, temp_dir


def temp_db(testcase: unittest.TestCase) -> str:
    """A copy of the test database, as its own file name in a new temporary folder."""
    return temp_copy(testcase, TEST_DATABASE, DatabaseV2.FILENAME)


class PathTestCase(unittest.TestCase):
    def assertRelativePaths(self, cases: dict[str, str]):
        for path, expected in cases.items():
            with self.subTest(path):
                self.assertEqual(SeratoBinFile.get_relative_path(path), expected)

    def test_relative_path(self):
        self.assertRelativePaths(
            {"Music/DJ Tracks/Tripp St. - Enlighten.mp3": "Music/DJ Tracks/Tripp St. - Enlighten.mp3"}
        )

    @unittest.skipUnless(os.name == "nt", "Windows drive letters and backslash separators")
    def test_windows_relative_path(self):
        self.assertRelativePaths(
            {
                "C:\\Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3": "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
                "Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3": "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
                "C:/Music/DJ Tracks/Tripp St. - Enlighten.mp3": "Music/DJ Tracks/Tripp St. - Enlighten.mp3",
            }
        )

    @unittest.skipIf(os.name == "nt", "POSIX paths")
    def test_posix_relative_path(self):
        self.assertRelativePaths(
            {
                "/Users/Username/Music/DJ Tracks/Tripp St. - Enlighten.mp3": "Users/Username/Music/DJ Tracks/Tripp St. - Enlighten.mp3"
            }
        )

    @unittest.skipUnless(os.name == "nt", "Windows drive letters")
    def test_full_path_keeps_given_drive(self):
        path = "D:/Music/DJ Tracks/Tripp St. - Enlighten.mp3"
        self.assertEqual(SeratoBinFile.get_full_path(path), os.path.normpath(path))

    @unittest.skipIf(os.name == "nt", "POSIX paths")
    def test_full_path_keeps_absolute_posix_path(self):
        path = "/Volumes/USB/Music/DJ Tracks/Tripp St. - Enlighten.mp3"
        self.assertEqual(SeratoBinFile.get_full_path(path), path)

    def test_full_path_without_drive_is_absolute(self):
        # Serato stores track paths with no drive or leading separator
        full_path = SeratoBinFile.get_full_path("Music/DJ Tracks/Tripp St. - Enlighten.mp3")
        self.assertTrue(os.path.isabs(full_path), full_path)
        self.assertTrue(full_path.endswith(os.path.normpath("/Music/DJ Tracks/Tripp St. - Enlighten.mp3")), full_path)


class ParseTestCase(unittest.TestCase):
    """Loading a file: from its bytes, from JSON, or, for a file that doesn't exist yet, from its class's defaults."""

    def test_a_file_cut_off_raises(self):
        data = read_bytes(TEST_DATABASE)
        tmp = temp_dir(self)
        for name, cut_at in (("partway through a header", 3), ("partway through an entry", len(data) - 1)):
            with self.subTest(name):
                path = os.path.join(tmp, f"{cut_at}.crate")
                with open(path, "wb") as f:
                    f.write(data[:cut_at])
                with self.assertRaisesRegex(ValueError, "file ends partway through"):
                    DatabaseV2(path)

    def test_new_file_shares_no_entries_with_its_class_default(self):
        # DatabaseV2 can't be created new. Crate and SmartCrate share CrateBase.DEFAULT_VIEW_ENTRIES' sublists
        defaults = {cls: copy.deepcopy(cls.DEFAULT_ENTRIES) for cls in (Crate, SmartCrate)}
        for cls, default_entries in defaults.items():
            with self.subTest(cls.__name__):
                tmp = temp_dir(self)
                a = cls(os.path.join(tmp, "A" + cls.EXTENSION))
                a.add_tracks(["/music/track1.mp3"])
                b = cls(os.path.join(tmp, "B" + cls.EXTENSION))

                for i, (field, value) in enumerate(a.entries[: len(default_entries)]):
                    if isinstance(value, list):
                        self.assertIsNot(value, cls.DEFAULT_ENTRIES[i][1], f"{field} sublist shared with class default")
                        self.assertIsNot(value, b.entries[i][1], f"{field} sublist shared between instances")
                        value.append((SeratoBinFile.Fields.COLUMN_NAME, "mutated"))

                for other_cls, other_default in defaults.items():
                    self.assertEqual(other_cls.DEFAULT_ENTRIES, other_default, f"{other_cls.__name__} default mutated")
                self.assertEqual(b.entries, default_entries, "other instance must not inherit tracks or nested edits")

    def test_json_round_trip(self):
        db_from_bin = DatabaseV2(TEST_DATABASE)
        self.assertEqual(
            db_from_bin.to_json_object(), json.loads(read_text("test/data/database_v2_json.json")), "to_json_object"
        )

        db_from_json = DatabaseV2(os.path.abspath("test/data/database_v2_json.json"))
        self.assertEqual(db_from_json.__str__(), db_from_bin.__str__(), "loaded from a JSON file")

        db_from_json.entries = []
        db_from_json.from_json_object(db_from_bin.to_json_object())
        self.assertEqual(db_from_json.__str__(), db_from_bin.__str__(), "from_json_object")

    def test_mistyped_json_value_is_refused(self):
        db = DatabaseV2(TEST_DATABASE)
        original_entries = copy.deepcopy(db.entries)
        json_obj = db.to_json_object()
        track = json_obj[1]["value"]
        assert isinstance(track, list)
        uadd = next(e for e in track if e["field"] == DatabaseV2.Fields.DATE_ADDED_U)
        uadd["value"], uadd["type"] = "not an int", "str"

        json_file = os.path.join(temp_dir(self), "db.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_obj, f)
        with self.assertRaises(DataTypeError, msg="on load"):
            DatabaseV2(json_file)

        with self.assertRaises(DataTypeError, msg="into an existing db"):
            db.from_json_object(json_obj)
        self.assertEqual(db.entries, original_entries, "existing entries left as they were")


class TracksTestCase(unittest.TestCase):
    """Changing a file's tracks, through DatabaseV2, whose tracks have the most fields."""

    def test_modify(self):
        db = DatabaseV2(TEST_DATABASE)
        self.maxDiff = None

        original_entries = copy.deepcopy(db.entries)
        original_str = db.__str__()
        self.assertFalse(db.modify([]), "reports no change")
        self.assertEqual(db.entries, original_entries, "was not modified")
        self.assertEqual(db.__str__(), original_str, "was not modified")

        new_time = int(1735748100)
        changed = db.modify(
            [
                {"field": DatabaseV2.Fields.DATE_ADDED_U, "func": lambda *args: new_time},
                {"field": DatabaseV2.Fields.DATE_ADDED_T, "func": lambda *args: str(new_time)},
                {"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "NEW_GROUPING"},
            ]
        )
        self.assertTrue(changed, "reports change")
        self.assertEqual(
            db.__str__(),
            read_text("test/data/database_v2_test_modified_output.txt", "utf-16"),
            "was modified correctly",
        )
        self.assertEqual(
            db.to_bytes(), read_bytes("test/data/database_v2_test_modified_output.bin"), "was modified correctly"
        )

        db.modify(
            [
                {
                    "field": DatabaseV2.Fields.GENRE,
                    "func": lambda *args: "NEW_GENRE",
                    "files": [
                        "Users/bvand/Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
                        os.path.join(os.sep, "Users", "bvand", "Music", "DJ Tracks", "Tripp St. - Enlighten.mp3"),
                    ]
                    # backslashes and drive letters only mean something on Windows
                    + (
                        [
                            "Users\\bvand\\Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3",
                            "C:/Users/bvand/Music/DJ Tracks/Tripp St. - Enlighten.mp3",
                        ]
                        if os.name == "nt"
                        else []
                    ),
                },
            ]
        )
        self.assertEqual(
            db.__str__(),
            read_text("test/data/database_v2_test_modified_output_2.txt"),
            "was modified correctly, given files",
        )
        self.assertEqual(
            db.to_bytes(),
            read_bytes("test/data/database_v2_test_modified_output_2.bin"),
            "was modified correctly, given files",
        )

    def test_modify_with_two_rules_for_a_field_raises(self):
        db = DatabaseV2(TEST_DATABASE)
        rule: SeratoBinFile.ModifyRule = {"field": DatabaseV2.Fields.GENRE, "func": lambda *args: None}
        with self.assertRaisesRegex(ValueError, "1 rule per field"):
            db.modify([rule, rule])

    def test_modify_empty_value_removes_field(self):
        # as Serato does when a tag is cleared
        db_file = temp_db(self)
        db = DatabaseV2(db_file)
        target = "Users/bvand/Music/DJ Tracks/SiR - D'Evils.mp3"
        other = "Users/bvand/Music/DJ Tracks/Slaycub - Visceral Planet.mp3"
        clear_grouping: list[DatabaseV2.ModifyRule] = [
            {"field": DatabaseV2.Fields.GROUPING, "files": [target], "func": lambda *args: ""}
        ]

        def grouping(database: DatabaseV2, relpath: str):
            track = next(t for t in database.get_tracks() if t.relpath == relpath)
            return track.get_value(DatabaseV2.Fields.GROUPING) if DatabaseV2.Fields.GROUPING in track.fields else None

        self.assertTrue(db.modify(clear_grouping), "reports removal")
        self.assertIsNone(grouping(db, target), "removed rather than set empty")
        self.assertEqual(grouping(db, other), "UNTAGGED", "other tracks left as they were")
        self.assertFalse(db.modify(clear_grouping), "reports no change when already gone")
        db.save()
        self.assertIsNone(grouping(DatabaseV2(db_file), target), "removed in the saved file")

        with self.assertRaises(ValueError, msg="a track can't be without its path"):
            db.modify([{"field": DatabaseV2.Fields.FILE_PATH, "files": [target], "func": lambda *args: ""}])

    def test_modify_tracks_given_files(self):
        db = DatabaseV2(TEST_DATABASE)
        target = "Users/bvand/Music/DJ Tracks/Tripp St. - Enlighten.mp3"

        seen: list[str] = []

        def func(track: DatabaseV2.Track):
            seen.append(track.relpath)
            return track

        db.modify_tracks(func, files=[target])
        self.assertEqual(seen, [DatabaseV2.get_relative_path(target)], "only the given track is passed to func")

    def test_remove_tracks(self):
        db = DatabaseV2(TEST_DATABASE)
        paths = db.get_track_paths()
        self.assertGreater(len(paths), 2)

        self.assertTrue(db.remove_tracks(paths[:2]), "reports removal")
        self.assertEqual(db.get_track_paths(), paths[2:], "removes exactly the given tracks, keeping order")
        self.assertFalse(db.remove_tracks(paths[:2]), "reports no change when already gone")

    def test_remove_duplicates(self):
        db = DatabaseV2("test/data/database_v2_duplicates.bin")
        self.assertEqual(db.__str__(), read_text("test/data/database_v2_duplicates_output.txt"), "original")
        self.assertTrue(db.remove_duplicates(), "reports removal")
        self.assertEqual(db.__str__(), read_text("test/data/database_v2_duplicates_output_deduped.txt"), "deduped")
        self.assertFalse(db.remove_duplicates(), "nothing left to remove")


class TrackTestCase(unittest.TestCase):
    def test_duplicate_field_raises(self):
        # a repeated field would be silently collapsed/duplicated on round-trip, corrupting the file
        with self.assertRaises(ValueError):
            SeratoBinFile.Track(
                [
                    (SeratoBinFile.Fields.FILE_PATH.value, "a.mp3"),
                    (SeratoBinFile.Fields.GENRE.value, "House"),
                    (SeratoBinFile.Fields.GENRE.value, "Techno"),
                ],
                path_key=SeratoBinFile.Fields.FILE_PATH.value,
            )

    def test_remove_field(self):
        path, genre = SeratoBinFile.Fields.FILE_PATH.value, SeratoBinFile.Fields.GENRE.value
        track = SeratoBinFile.Track([(path, "a.mp3"), (genre, "House")], path_key=path)
        only_path = [(path, "a.mp3")]

        self.assertTrue(track.remove_field(genre), "reports removal")
        self.assertEqual(track.to_entries(), only_path, "removed from the entries written back")
        self.assertFalse(track.remove_field(genre), "reports no change when already gone")

        # as Serato does when a tag is cleared
        track.set_value(genre, "House")
        track.set_value(genre, "")
        self.assertEqual(track.to_entries(), only_path, "set_value empty removes it, rather than setting it empty")
        track.set_value(genre, "")
        self.assertEqual(track.to_entries(), only_path, "set_value empty doesn't add it when already gone")

        for remove_path in (lambda: track.remove_field(path), lambda: track.set_value(path, "")):
            with self.assertRaises(ValueError, msg="a track can't be without its path"):
                remove_path()
        self.assertEqual(track.to_entries(), only_path, "path kept")


class SaveTestCase(unittest.TestCase):
    """has_changed and save, mostly through Crate, the smallest of the bin file classes."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.file = temp_copy(self, TEST_CRATE, "Test.crate", self.tmp)
        self.written = bin_file_writes(self)

    def test_save_writes_its_own_file_only_when_changed(self):
        crate = Crate(self.file)
        self.assertFalse(crate.has_changed, "as loaded")
        self.assertFalse(crate.save(), "unchanged")
        self.assertEqual(self.written, [], "unchanged, so not written")
        self.assertTrue(crate.save(force=True), "forced")
        self.assertEqual(self.written, ["Test.crate"], "forced, so written")
        copy = os.path.join(self.tmp, "Copy.crate")
        self.assertTrue(crate.save(copy), "saving elsewhere always writes")
        self.assertEqual(read_bytes(copy), read_bytes(self.file), "as it was")

        crate.add_tracks(["/music/track1.mp3"])
        self.assertTrue(crate.has_changed, "track added")
        crate.save(copy)
        self.assertTrue(crate.has_changed, "saving a copy elsewhere leaves its own file unsaved")
        with mock.patch.object(Crate, "to_bytes", autospec=True, side_effect=Crate.to_bytes) as to_bytes:
            self.assertTrue(crate.save())
        self.assertEqual(to_bytes.call_count, 1, "serialized once, to check and to write")
        self.assertEqual(Crate(self.file).get_track_paths(), crate.get_track_paths(), "written")
        self.assertFalse(crate.has_changed, "saved")
        self.assertFalse(crate.save(), "not written again")

        sorting = crate.entries[1][1]
        assert isinstance(sorting, list)
        sorting.append((Crate.Fields.COLUMN_NAME, "edited in place"))
        self.assertTrue(crate.has_changed, "nested entry edited in place")
        sorting.pop()
        self.assertFalse(crate.has_changed, "edited back")

    @unittest.skipIf(os.name == "nt", "creating a symlink needs extra privileges on Windows")
    def test_saving_through_a_symlink_is_saving_its_own_file(self):
        link = os.path.join(self.tmp, "Link.crate")
        os.symlink(self.file, link)
        crate = Crate(self.file)
        crate.add_tracks(["/music/track1.mp3"])
        crate.save(link)
        self.assertFalse(crate.has_changed)

    def test_new_file_has_changed_until_saved(self):
        file = os.path.join(self.tmp, "New.crate")
        crate = Crate(file)
        self.assertTrue(crate.has_changed, "saving creates the file")
        crate.add_tracks(["/music/track1.mp3"])
        crate.save()
        self.assertFalse(crate.has_changed)
        self.assertEqual(Crate(file).get_track_paths(), crate.get_track_paths(), "created with its tracks")

    def test_file_loaded_from_json_hasnt_changed(self):
        json_file = os.path.join(self.tmp, "Test.json")
        Crate(self.file).write_json(json_file)
        crate = Crate(json_file)
        self.assertFalse(crate.has_changed)
        crate.add_tracks(["/music/track1.mp3"])
        self.assertTrue(crate.has_changed)

    def test_save_leaves_file_as_it_was_on_error(self):
        orig = read_bytes(TEST_DATABASE)
        db_file = temp_db(self)

        db = DatabaseV2(db_file)
        db.entries.append((DatabaseV2.Fields.TRACK, "not a list"))
        with self.assertRaises(DataTypeError):
            db.save()
        self.assertEqual(read_bytes(db_file), orig, "serialization error")

        class SavesTooEarly(DatabaseV2):
            def __init__(self, file: str):
                self.filepath = file
                self.save()
                super().__init__(file)

        with self.assertRaises(RuntimeError):
            SavesTooEarly(db_file)
        self.assertEqual(read_bytes(db_file), orig, "save before parse finished")

    def test_methods_that_save_skip_it_when_unchanged(self):
        db_file = temp_db(self)
        db = DatabaseV2(db_file)

        no_match: list[DatabaseV2.ModifyRule] = [
            {"field": DatabaseV2.Fields.GROUPING, "files": ["Not In Library.mp3"], "func": lambda *args: "X"}
        ]
        db.modify_and_save(no_match)
        self.assertEqual(self.written, [], "modify_and_save unchanged, so not saved")
        if os.name == "nt":  # paths are only case-insensitive on Windows
            db.modify_and_save(no_match, db_file.upper())
            self.assertEqual(self.written, [], "same file in other case, unchanged, so not saved")

        # the fixture's tracks don't exist here, so each one prompts; "s" skips it
        with mock.patch("builtins.input", return_value="s"), mock.patch("builtins.print"):
            db.find_missing()
        self.assertEqual(self.written, [], "find_missing relocated nothing, so not saved")

        db.modify_and_save(no_match, os.path.join(os.path.dirname(db_file), "copy"))
        self.assertEqual(self.written, ["copy"], "saved anyway when given another file")

        db.modify_and_save([{"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "X"}])
        self.assertEqual(self.written, ["copy", DatabaseV2.FILENAME], "changed, so saved")


if __name__ == "__main__":
    unittest.main()
