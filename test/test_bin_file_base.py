"""Tests of SeratoBinFile's shared behaviour, driven through a subclass: track paths, tracks, and has_changed."""

import os
import shutil
import unittest

from serato_tools.crate import Crate
from serato_tools.utils.bin_file_base import SeratoBinFile

from test.helpers import temp_dir


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


class HasChangedTestCase(unittest.TestCase):
    """has_changed, through Crate, the smallest of the bin file classes."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.file = os.path.join(self.tmp, "Test.crate")
        shutil.copy("test/data/TestCrate.crate", self.file)

    def test_has_changed(self):
        crate = Crate(self.file)
        self.assertFalse(crate.has_changed, "as loaded")

        crate.add_tracks(["/music/track1.mp3"])
        self.assertTrue(crate.has_changed, "track added")
        crate.save(os.path.join(self.tmp, "Copy.crate"))
        self.assertTrue(crate.has_changed, "saving a copy elsewhere leaves its own file unsaved")
        crate.save()
        self.assertFalse(crate.has_changed, "saved")

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
        crate = Crate(os.path.join(self.tmp, "New.crate"))
        self.assertTrue(crate.has_changed, "saving creates the file")
        crate.save()
        self.assertFalse(crate.has_changed)

    def test_file_loaded_from_json_hasnt_changed(self):
        json_file = os.path.join(self.tmp, "Test.json")
        Crate(self.file).write_json(json_file)
        crate = Crate(json_file)
        self.assertFalse(crate.has_changed)
        crate.add_tracks(["/music/track1.mp3"])
        self.assertTrue(crate.has_changed)


if __name__ == "__main__":
    unittest.main()
