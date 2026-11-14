import os
import unittest

from serato_tools.crate import Crate

from test.helpers.bin_files import TEST_CRATE
from test.helpers.files import read_bytes, read_text, temp_dir

base_expected = read_text("test/data/crate.txt")


class TestCase(unittest.TestCase):
    def test_parse_and_modify_and_serialize(self):
        file = os.path.abspath(TEST_CRATE)
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

    def test_saving_needs_the_crate_extension(self):
        crate = Crate(os.path.join(temp_dir(self), "Test.crate"))
        with self.assertRaisesRegex(ValueError, "should end with .crate"):
            crate.save(os.path.join(temp_dir(self), "Test.txt"))


if __name__ == "__main__":
    unittest.main()
