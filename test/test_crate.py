# pylint: disable=protected-access
import unittest
import copy
import os
import tempfile

from src.serato_tools.crate import Crate

with open("test/data/crate.txt", "r", encoding="utf-8") as f:
    base_expected = f.read()


class TestCase(unittest.TestCase):
    def test_format_filepath(self):
        self.assertEqual(
            Crate.get_relative_path("C:\\Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3"),
            "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
        )
        self.assertEqual(
            Crate.get_relative_path("Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3"),
            "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
        )
        self.assertEqual(
            Crate.get_relative_path("C:/Music/DJ Tracks/Tripp St. - Enlighten.mp3"),
            "Music/DJ Tracks/Tripp St. - Enlighten.mp3",
        )
        self.assertEqual(
            Crate.get_relative_path("Music/DJ Tracks/Tripp St. - Enlighten.mp3"),
            "Music/DJ Tracks/Tripp St. - Enlighten.mp3",
        )

    def test_parse_and_modify_and_dump(self):
        file = os.path.abspath("test/data/TestCrate.crate")
        with open(file, mode="rb") as fp:
            file_data = fp.read()

        crate = Crate(file)

        self.maxDiff = None

        self.assertEqual(crate.raw_data, file_data, "raw_data read")
        expected = base_expected

        self.assertEqual(crate.__str__(), expected, "parse")

        crate.add_track("C:\\Users\\bvand\\Music\\DJ Tracks\\Soulacybin - Zeu.mp3")
        expected += "\notrk (Track): [ ptrk (Track Path): Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3 ]"
        self.assertEqual(crate.__str__(), expected, "track added")

        for t in [
            "C:\\Users\\bvand\\Music\\DJ Tracks\\Soulacybin - Zeu.mp3",
            "Users\\bvand\\Music\\DJ Tracks\\Soulacybin - Zeu.mp3",
            "C:/Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
            "Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
            "/Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
        ]:
            crate.add_track(t)
            self.assertEqual(crate.__str__(), expected, "duplicate track not added")

        crate.add_track("C:/Users/bvand/Music/DJ Tracks/Thundercat - Them Changes.mp3")
        expected += "\notrk (Track): [ ptrk (Track Path): Users/bvand/Music/DJ Tracks/Thundercat - Them Changes.mp3 ]"
        self.assertEqual(crate.__str__(), expected, "track added")

    def test_new_crate_does_not_share_entries_with_class_default(self):
        a = Crate("/tmp/serato_test_A.crate")
        a.add_track("/music/track1.mp3")

        b = Crate("/tmp/serato_test_B.crate")
        otrk_entries = [e for e in b.entries if e[0] == "otrk"]
        self.assertEqual(otrk_entries, [], "new Crate must not inherit tracks from a previous instance")

    def test_new_crate_does_not_share_nested_entries_with_class_default(self):
        default_entries = copy.deepcopy(Crate.DEFAULT_ENTRIES)

        a = Crate("/tmp/serato_test_C.crate")
        b = Crate("/tmp/serato_test_D.crate")

        for i, (field, value) in enumerate(a.entries):
            if isinstance(value, list):
                self.assertIsNot(value, Crate.DEFAULT_ENTRIES[i][1], f"{field} sublist shared with class default")
                self.assertIsNot(value, b.entries[i][1], f"{field} sublist shared between instances")

        sorting_value = a.entries[1][1]
        assert isinstance(sorting_value, list)
        sorting_value.append((Crate.Fields.COLUMN_NAME, "mutated"))

        self.assertEqual(Crate.DEFAULT_ENTRIES, default_entries, "class default must not be mutated")
        self.assertEqual(b.entries, default_entries, "other instance must not be mutated")

    def test_add_track_is_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = os.path.join(tmp, "Test.crate")
            crate = Crate(file)
            crate.add_track("/music/track1.mp3")
            crate.save()

            self.assertEqual(Crate(file).get_track_paths(), crate.get_track_paths())
            self.assertEqual(len(crate.get_track_paths()), 1)
