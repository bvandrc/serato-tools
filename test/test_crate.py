import unittest
import copy
import os

from serato_tools.crate import Crate

from test.helpers import read_bytes, temp_dir

with open("test/data/crate.txt", "r", encoding="utf-8") as f:
    base_expected = f.read()


class TestCase(unittest.TestCase):
    def test_parse_and_modify_and_serialize(self):
        file = os.path.abspath("test/data/TestCrate.crate")
        crate = Crate(file)

        self.maxDiff = None

        self.assertEqual(crate.to_bytes(), read_bytes(file), "to_bytes")
        expected = base_expected

        self.assertEqual(crate.__str__(), expected, "parse")

        # absolute in this OS's form: C:\Users\... on Windows, /Users/... elsewhere
        full_track_path = os.path.join(
            os.path.splitdrive(os.getcwd())[0], os.sep, "Users", "bvand", "Music", "DJ Tracks", "Soulacybin - Zeu.mp3"
        )
        crate.add_tracks([full_track_path])
        expected += "\notrk (Track): [ ptrk (Track Path): Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3 ]"
        self.assertEqual(crate.__str__(), expected, "track added")

        same_track_paths = [
            full_track_path,
            "Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
            "/Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
        ]
        if os.name == "nt":
            # backslashes are only separators on Windows
            same_track_paths += [
                "C:\\Users\\bvand\\Music\\DJ Tracks\\Soulacybin - Zeu.mp3",
                "Users\\bvand\\Music\\DJ Tracks\\Soulacybin - Zeu.mp3",
                "C:/Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
            ]
        crate.add_tracks(same_track_paths)
        self.assertEqual(crate.__str__(), expected, "duplicate tracks not added")

        crate.add_tracks([os.path.join(os.path.dirname(full_track_path), "Thundercat - Them Changes.mp3")])
        expected += "\notrk (Track): [ ptrk (Track Path): Users/bvand/Music/DJ Tracks/Thundercat - Them Changes.mp3 ]"
        self.assertEqual(crate.__str__(), expected, "track added")

    def test_new_crate_does_not_share_entries_with_class_default(self):
        default_entries = copy.deepcopy(Crate.DEFAULT_ENTRIES)
        tmp = temp_dir(self)

        a = Crate(os.path.join(tmp, "A.crate"))
        a.add_tracks(["/music/track1.mp3"])
        b = Crate(os.path.join(tmp, "B.crate"))

        for i, (field, value) in enumerate(a.entries[: len(default_entries)]):
            if isinstance(value, list):
                self.assertIsNot(value, Crate.DEFAULT_ENTRIES[i][1], f"{field} sublist shared with class default")
                self.assertIsNot(value, b.entries[i][1], f"{field} sublist shared between instances")

        sorting_value = a.entries[1][1]
        assert isinstance(sorting_value, list)
        sorting_value.append((Crate.Fields.COLUMN_NAME, "mutated"))

        self.assertEqual(Crate.DEFAULT_ENTRIES, default_entries, "class default must not be mutated")
        self.assertEqual(b.entries, default_entries, "other instance must not inherit tracks or nested edits")

    def test_add_tracks_is_saved(self):
        file = os.path.join(temp_dir(self), "Test.crate")
        crate = Crate(file)
        crate.add_tracks(["/music/track1.mp3"])
        crate.save()

        self.assertEqual(Crate(file).get_track_paths(), crate.get_track_paths())
        self.assertEqual(len(crate.get_track_paths()), 1)


if __name__ == "__main__":
    unittest.main()
