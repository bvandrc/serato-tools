# pylint: disable=protected-access
import copy
import json
import os
import shutil
import unittest
from unittest import mock

from serato_tools.database_v2 import DatabaseV2

# bin_file_base raises the installed package's DataTypeError, so catch that one
from serato_tools.utils.bin_file_base import DataTypeError

from test.helpers import read_bytes, temp_dir


class TestCase(unittest.TestCase):
    def test_parse_and_serialize(self):
        file = os.path.abspath("test/data/database_v2_test.bin")
        db = DatabaseV2(file)

        self.maxDiff = None
        self.assertEqual(db.to_bytes(), read_bytes(file), "to_bytes")

        with open("test/data/database_v2_test_output.txt", "r", encoding="utf-16") as f:
            expected = f.read()
            self.assertEqual(db.__str__(), expected, "parse")

    def test_remove_tracks(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))
        paths = db.get_track_paths()
        self.assertGreater(len(paths), 2)

        self.assertTrue(db.remove_tracks(paths[:2]), "reports removal")
        self.assertEqual(db.get_track_paths(), paths[2:], "removes exactly the given tracks, keeping order")
        self.assertFalse(db.remove_tracks(paths[:2]), "reports no change when already gone")

    def test_parse_and_modify(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))
        self.maxDiff = None
        expected = db.__str__()

        original_entries = copy.deepcopy(db.entries)
        original_bytes = db.to_bytes()
        self.assertFalse(db.modify([]), "reports no change")
        self.assertEqual(db.entries, original_entries, "was not modified")
        self.assertEqual(db.to_bytes(), original_bytes, "was not modified")
        self.assertEqual(db.__str__(), expected, "was not modified")

        new_time = int(1735748100)
        changed = db.modify(
            [
                {"field": DatabaseV2.Fields.DATE_ADDED_U, "func": lambda *args: new_time},
                {"field": DatabaseV2.Fields.DATE_ADDED_T, "func": lambda *args: str(new_time)},
                {"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "NEW_GROUPING"},
            ]
        )
        self.assertTrue(changed, "reports change")
        with open("test/data/database_v2_test_modified_output.txt", "r", encoding="utf-16") as f:
            self.assertEqual(db.__str__(), f.read(), "was modified correctly")
        with open("test/data/database_v2_test_modified_output.bin", "rb") as f:
            self.assertEqual(db.to_bytes(), f.read(), "was modified correctly")

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
        with open("test/data/database_v2_test_modified_output_2.txt", "r", encoding="utf-8") as f:
            self.assertEqual(db.__str__(), f.read(), "was modified correctly, given files")
        with open("test/data/database_v2_test_modified_output_2.bin", "rb") as f:
            self.assertEqual(db.to_bytes(), f.read(), "was modified correctly, given files")

    def test_modify_and_save_skips_save_when_unchanged(self):
        tmp = temp_dir(self)
        db_file = os.path.join(tmp, "database V2")
        shutil.copy("test/data/database_v2_test.bin", db_file)
        db = DatabaseV2(db_file)
        os.remove(db_file)  # so any save shows up as the file reappearing

        no_match: list[DatabaseV2.ModifyRule] = [
            {"field": DatabaseV2.Fields.GROUPING, "files": ["Not In Library.mp3"], "func": lambda *args: "X"}
        ]
        db.modify_and_save(no_match)
        self.assertFalse(os.path.exists(db_file), "unchanged, so not saved")
        if os.name == "nt":  # paths are only case-insensitive on Windows
            db.modify_and_save(no_match, db_file.upper())
            self.assertFalse(os.path.exists(db_file), "same file in other case, unchanged, so not saved")

        copy_file = os.path.join(tmp, "copy")
        db.modify_and_save(no_match, copy_file)
        self.assertTrue(os.path.exists(copy_file), "saved anyway when given another file")

        db.modify_and_save([{"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "X"}])
        self.assertTrue(os.path.exists(db_file), "changed, so saved")

    def test_modify_empty_value_removes_field(self):
        # as Serato does when a tag is cleared
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))
        target = "Users/bvand/Music/DJ Tracks/SiR - D'Evils.mp3"
        other = "Users/bvand/Music/DJ Tracks/Slaycub - Visceral Planet.mp3"
        clear_grouping: list[DatabaseV2.ModifyRule] = [
            {"field": DatabaseV2.Fields.GROUPING, "files": [target], "func": lambda *args: ""}
        ]

        def grouping(relpath: str):
            track = next(t for t in db.get_tracks() if t.relpath == relpath)
            return track.get_value(DatabaseV2.Fields.GROUPING) if DatabaseV2.Fields.GROUPING in track.fields else None

        self.assertTrue(db.modify(clear_grouping), "reports removal")
        self.assertIsNone(grouping(target), "removed rather than set empty")
        self.assertEqual(grouping(other), "UNTAGGED", "other tracks left as they were")
        self.assertFalse(db.modify(clear_grouping), "reports no change when already gone")

        with self.assertRaises(ValueError, msg="a track can't be without its path"):
            db.modify([{"field": DatabaseV2.Fields.FILE_PATH, "files": [target], "func": lambda *args: ""}])

    def test_modify_and_save_empty_value_removes_field(self):
        tmp = temp_dir(self)
        db_file = os.path.join(tmp, "database V2")
        shutil.copy("test/data/database_v2_test.bin", db_file)
        target = "Users/bvand/Music/DJ Tracks/SiR - D'Evils.mp3"

        DatabaseV2(db_file).modify_and_save(
            [{"field": DatabaseV2.Fields.GROUPING, "files": [target], "func": lambda *args: ""}]
        )
        track = next(t for t in DatabaseV2(db_file).get_tracks() if t.relpath == target)
        self.assertNotIn(DatabaseV2.Fields.GROUPING, track.fields, "removed in the saved file")

    def test_find_missing_skips_save_when_nothing_relocated(self):
        tmp = temp_dir(self)
        db_file = os.path.join(tmp, "database V2")
        shutil.copy("test/data/database_v2_test.bin", db_file)
        db = DatabaseV2(db_file)
        os.remove(db_file)  # so any save shows up as the file reappearing

        # the fixture's tracks don't exist here, so each one prompts; "s" skips it
        with mock.patch("builtins.input", return_value="s"), mock.patch("builtins.print"):
            db.find_missing()

        self.assertFalse(os.path.exists(db_file), "nothing relocated, so not saved")

    def test_find_missing_relocates_tracks_found_in_a_folder_given(self):
        tmp = temp_dir(self)
        db_file = os.path.join(tmp, "database V2")
        shutil.copy("test/data/database_v2_test.bin", db_file)
        db = DatabaseV2(db_file)
        first, *rest = db.get_track_paths()
        found_dir = os.path.join(tmp, "found")
        os.mkdir(found_dir)
        found = os.path.join(found_dir, os.path.basename(first))
        open(found, "wb").close()  # pylint: disable=consider-using-with

        # the folder for the first track, which later missing tracks are also looked for in; "s" skips the rest
        answers = iter([found_dir])
        with mock.patch("builtins.input", side_effect=lambda prompt: next(answers, "s")), mock.patch("builtins.print"):
            db.find_missing()

        self.assertEqual(DatabaseV2(db_file).get_track_paths(), [DatabaseV2.get_relative_path(found), *rest], "saved")

    def test_save_leaves_file_as_it_was_on_error(self):
        orig = read_bytes("test/data/database_v2_test.bin")

        tmp = temp_dir(self)
        db_file = os.path.join(tmp, "database V2")
        shutil.copy("test/data/database_v2_test.bin", db_file)

        db = DatabaseV2(db_file)
        db.entries.append((DatabaseV2.Fields.TRACK, "not a list"))
        with self.assertRaises(DataTypeError):
            db.save()
        with open(db_file, "rb") as f:
            self.assertEqual(f.read(), orig, "serialization error")

        class SavesTooEarly(DatabaseV2):
            def __init__(self, file: str):
                self.filepath = file
                self.save()
                super().__init__(file)

        with self.assertRaises(RuntimeError):
            SavesTooEarly(db_file)
        with open(db_file, "rb") as f:
            self.assertEqual(f.read(), orig, "save before parse finished")

    def test_mistyped_json_value_is_refused(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))
        original_entries = copy.deepcopy(db.entries)
        json_obj = db.to_json_object()
        track = json_obj[1]["value"]
        assert isinstance(track, list)
        uadd = next(e for e in track if e["field"] == DatabaseV2.Fields.DATE_ADDED_U)
        uadd["value"], uadd["type"] = "not an int", "str"

        tmp = temp_dir(self)
        json_file = os.path.join(tmp, "db.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_obj, f)
        with self.assertRaises(DataTypeError, msg="on load"):
            DatabaseV2(json_file)

        with self.assertRaises(DataTypeError, msg="into an existing db"):
            db.from_json_object(json_obj)
        self.assertEqual(db.entries, original_entries, "existing entries left as they were")

    def test_modify_tracks_given_files(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))
        target = "Users/bvand/Music/DJ Tracks/Tripp St. - Enlighten.mp3"

        seen: list[str] = []

        def func(track: DatabaseV2.Track):
            seen.append(track.relpath)
            return track

        db.modify_tracks(func, files=[target])
        self.assertEqual(seen, [DatabaseV2.get_relative_path(target)], "only the given track is passed to func")

    def test_dedupe(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_duplicates.bin"))

        with open("test/data/database_v2_duplicates_output.txt", "r", encoding="utf-8") as f:
            self.assertEqual(db.__str__(), f.read(), "original")

        self.assertTrue(db.remove_duplicates(), "reports removal")

        with open("test/data/database_v2_duplicates_output_deduped.txt", "r", encoding="utf-8") as f:
            self.assertEqual(db.__str__(), f.read(), "deduped")

        self.assertFalse(db.remove_duplicates(), "nothing left to remove")

    def test_get_corrupt_tracks(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))
        self.assertEqual(db.get_corrupt_tracks(), {}, "no corrupt tracks in the test database")

        fields = DatabaseV2.Fields
        db.entries += [
            (
                fields.TRACK,
                [(fields.FILE_PATH, "Music/Bad.mp3"), (fields.CORRUPT, True), (fields.CORRUPT_REASON, "why")],
            ),
            (fields.TRACK, [(fields.FILE_PATH, "Music/No Reason.mp3"), (fields.CORRUPT, True)]),
            (fields.TRACK, [(fields.FILE_PATH, "Music/Fine.mp3"), (fields.CORRUPT, False)]),
        ]
        self.assertEqual(
            db.get_corrupt_tracks(),
            {DatabaseV2.get_full_path("Music/Bad.mp3"): "why", DatabaseV2.get_full_path("Music/No Reason.mp3"): ""},
        )

    def test_json_round_trip(self):
        db_from_bin = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))
        with open("test/data/database_v2_json.json", "r", encoding="utf-8") as f:
            self.assertEqual(db_from_bin.to_json_object(), json.load(f), "to_json_object")

        db_from_json = DatabaseV2(os.path.abspath("test/data/database_v2_json.json"))
        self.assertEqual(db_from_json.__str__(), db_from_bin.__str__(), "loaded from a JSON file")

        db_from_json.entries = []
        db_from_json.from_json_object(db_from_bin.to_json_object())
        self.assertEqual(db_from_json.__str__(), db_from_bin.__str__(), "from_json_object")
