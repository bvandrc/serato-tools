# pylint: disable=protected-access
import unittest
from unittest import mock
import os
import json
import shutil
import tempfile

from src.serato_tools.database_v2 import DatabaseV2


class TestCase(unittest.TestCase):
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

    def test_full_path_keeps_given_drive(self):
        path = "D:/Music/DJ Tracks/Tripp St. - Enlighten.mp3"
        self.assertEqual(DatabaseV2.get_full_path(path), os.path.normpath(path))

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

    def test_parse_and_modify(self):
        db = DatabaseV2(os.path.abspath("test/data/database_v2_test.bin"))

        self.maxDiff = None

        with open("test/data/database_v2_test_output.txt", "r", encoding="utf-16") as f:
            expected = f.read()
            self.assertEqual(db.__str__(), expected, "parse")

        original_entries = db.entries
        original_raw_data = db.raw_data
        self.assertFalse(db.modify([]), "reports no change")
        self.assertEqual(db.entries, original_entries, "was not modified")
        self.assertEqual(db.raw_data, original_raw_data, "was not modified")
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

    def test_rename_track_file_only_saves_crates_with_track(self):
        # rename_track_file imports Crate from the installed package, so patch that one
        from serato_tools.crate import Crate  # pylint: disable=import-outside-toplevel

        with tempfile.TemporaryDirectory() as tmp:
            src, dest = os.path.join(tmp, "Old.mp3"), os.path.join(tmp, "New.mp3")
            open(src, "wb").close()

            db_file = os.path.join(tmp, "database V2")
            shutil.copy("test/data/database_v2_test.bin", db_file)
            db = DatabaseV2(db_file)
            db.entries.append(
                (DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, DatabaseV2.get_relative_path(src))])
            )

            crates_dir = os.path.join(tmp, "Subcrates")
            os.mkdir(crates_dir)
            for name, has_track in [("With.crate", True), ("Without.crate", False)]:
                crate = Crate(os.path.join(crates_dir, name))
                if has_track:
                    crate.add_track(src)
                crate.save()

            saved: list[Crate] = []
            with (
                mock.patch.object(Crate, "DIR_PATH", crates_dir),
                mock.patch.object(Crate, "save", autospec=True, side_effect=saved.append),
            ):
                db.rename_track_file(src, dest)

            self.assertEqual(
                [os.path.basename(c.filepath) for c in saved], ["With.crate"], "only crate with track saved"
            )
            self.assertEqual(saved[0].get_track_paths(), [DatabaseV2.get_relative_path(dest)], "crate path updated")
            self.assertIn(DatabaseV2.get_relative_path(dest), DatabaseV2(db_file).get_track_paths(), "db path updated")

    def test_rename_track_file_skips_saving_db_without_track(self):
        # rename_track_file imports Crate from the installed package, so patch that one
        from serato_tools.crate import Crate  # pylint: disable=import-outside-toplevel

        with tempfile.TemporaryDirectory() as tmp:
            src, dest = os.path.join(tmp, "Old.mp3"), os.path.join(tmp, "New.mp3")
            open(src, "wb").close()

            db_file = os.path.join(tmp, "database V2")
            shutil.copy("test/data/database_v2_test.bin", db_file)
            db = DatabaseV2(db_file)
            os.remove(db_file)  # so any save shows up as the file reappearing

            crates_dir = os.path.join(tmp, "Subcrates")
            os.mkdir(crates_dir)
            with mock.patch.object(Crate, "DIR_PATH", crates_dir):
                db.rename_track_file(src, dest)

            self.assertTrue(os.path.exists(dest), "file renamed")
            self.assertFalse(os.path.exists(db_file), "db not saved")

    def test_modify_and_save_skips_save_when_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_file = os.path.join(tmp, "database V2")
            shutil.copy("test/data/database_v2_test.bin", db_file)
            db = DatabaseV2(db_file)
            os.remove(db_file)  # so any save shows up as the file reappearing

            no_match: list[DatabaseV2.ModifyRule] = [
                {"field": DatabaseV2.Fields.GROUPING, "files": ["Not In Library.mp3"], "func": lambda *args: "X"}
            ]
            db.modify_and_save(no_match)
            self.assertFalse(os.path.exists(db_file), "unchanged, so not saved")

            copy_file = os.path.join(tmp, "copy")
            db.modify_and_save(no_match, copy_file)
            self.assertTrue(os.path.exists(copy_file), "saved anyway when given another file")

            db.modify_and_save([{"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "X"}])
            self.assertTrue(os.path.exists(db_file), "changed, so saved")

    def test_find_missing_skips_save_when_nothing_relocated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_file = os.path.join(tmp, "database V2")
            shutil.copy("test/data/database_v2_test.bin", db_file)
            db = DatabaseV2(db_file)
            os.remove(db_file)  # so any save shows up as the file reappearing

            # the fixture's tracks don't exist here, so each one prompts; "s" skips it
            with mock.patch("builtins.input", return_value="s"), mock.patch("builtins.print"):
                db.find_missing()

            self.assertFalse(os.path.exists(db_file), "nothing relocated, so not saved")

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
