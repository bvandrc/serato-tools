# pylint: disable=protected-access
import unittest
import os
import json

from src.serato_tools.database_v2 import DatabaseV2
from src.serato_tools.utils.bin_file_base import SeratoBinFile


class TestCase(unittest.TestCase):
    def test_duplicate_field_in_track_raises(self):
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

    def test_format_filepath(self):
        self.assertEqual(
            DatabaseV2.get_relative_path("C:\\Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3"),
            "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
        )
        self.assertEqual(
            DatabaseV2.get_relative_path("Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3"),
            "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
        )
        self.assertEqual(
            DatabaseV2.get_relative_path("C:/Music/DJ Tracks/Tripp St. - Enlighten.mp3"),
            "Music/DJ Tracks/Tripp St. - Enlighten.mp3",
        )
        self.assertEqual(
            DatabaseV2.get_relative_path("Music/DJ Tracks/Tripp St. - Enlighten.mp3"),
            "Music/DJ Tracks/Tripp St. - Enlighten.mp3",
        )

    def test_parse_and_dump(self):
        file = os.path.abspath("test/data/database_v2_test.bin")
        with open(file, mode="rb") as fp:
            file_data = fp.read()

        db = DatabaseV2(file)

        self.maxDiff = None
        self.assertEqual(db.raw_data, file_data, "raw_data read")

        with open("test/data/database_v2_test_output.txt", "r", encoding="utf-16") as f:
            expected = f.read()
            self.assertEqual(db.__str__(), expected, "parse")

        db._dump()
        self.assertEqual(db.raw_data, file_data, "raw_data read")

    def test_parse_and_modify(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))

        self.maxDiff = None

        with open("test/data/database_v2_test_output.txt", "r", encoding="utf-16") as f:
            expected = f.read()
            self.assertEqual(db.__str__(), expected, "parse")

        original_entries = db.entries
        original_raw_data = db.raw_data
        db.modify([])
        self.assertEqual(db.entries, original_entries, "was not modified")
        self.assertEqual(db.raw_data, original_raw_data, "was not modified")
        self.assertEqual(db.__str__(), expected, "was not modified")

        new_time = int(1735748100)
        db.modify(
            [
                {"field": DatabaseV2.Fields.DATE_ADDED_U, "func": lambda *args: new_time},
                {"field": DatabaseV2.Fields.DATE_ADDED_T, "func": lambda *args: str(new_time)},
                {"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "NEW_GROUPING"},
            ]
        )
        with open("test/data/database_v2_test_modified_output.txt", "r", encoding="utf-16") as f:
            self.assertEqual(db.__str__(), f.read(), "was modified correctly")
        with open("test/data/database_v2_test_modified_output.bin", "rb") as f:
            self.assertEqual(db.raw_data, f.read(), "was modified correctly")

        db.modify(
            [
                {
                    "field": DatabaseV2.Fields.GENRE,
                    "func": lambda *args: "NEW_GENRE",
                    "files": [
                        "Users\\bvand\\Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3",
                        "C:/Users/bvand/Music/DJ Tracks/Tripp St. - Enlighten.mp3",
                    ],
                },
            ]
        )
        with open("test/data/database_v2_test_modified_output_2.txt", "r", encoding="utf-8") as f:
            self.assertEqual(db.__str__(), f.read(), "was modified correctly, given files")
        with open("test/data/database_v2_test_modified_output_2.bin", "rb") as f:
            self.assertEqual(db.raw_data, f.read(), "was modified correctly, given files")

    def test_dedupe(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_duplicates.bin"))

        with open("test/data/database_v2_duplicates_output.txt", "r", encoding="utf-8") as f:
            self.assertEqual(db.__str__(), f.read(), "original")

        db.remove_duplicates()

        with open("test/data/database_v2_duplicates_output_deduped.txt", "r", encoding="utf-8") as f:
            self.assertEqual(db.__str__(), f.read(), "deduped")

    def test_to_json_object(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))

        with open("test/data/database_v2_json.json", "r", encoding="utf-8") as f:
            self.assertEqual(db.to_json_object(), json.loads(f.read()))

    def test_from_json_object(self):
        db_from_json = DatabaseV2(os.path.abspath("test/data/database_v2_json.json"))
        db_from_bin = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))

        self.assertEqual(db_from_json.__str__(), db_from_bin.__str__())

        json_object = db_from_bin.to_json_object()
        db_from_json.from_json_object(json_object)

        self.assertEqual(db_from_json.__str__(), db_from_bin.__str__())
