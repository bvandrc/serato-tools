import os
import unittest
from unittest import mock

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.utils.bin_file_base import SeratoBinFile

from test.helpers import TEST_CRATE, TEST_DATABASE, read_bytes, temp_copy, temp_dir


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

    def test_modify_with_two_rules_for_a_field_raises(self):
        db = DatabaseV2(TEST_DATABASE)
        rule: SeratoBinFile.ModifyRule = {"field": DatabaseV2.Fields.GENRE, "func": lambda *args: None}
        with self.assertRaisesRegex(ValueError, "1 rule per field"):
            db.modify([rule, rule])


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
    """has_changed and save, through Crate, the smallest of the bin file classes."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.file = temp_copy(self, TEST_CRATE, "Test.crate", self.tmp)

    def test_save_writes_its_own_file_only_when_changed(self):
        crate = Crate(self.file)
        self.assertFalse(crate.has_changed, "as loaded")
        with mock.patch("builtins.open", wraps=open) as opened:
            self.assertFalse(crate.save(), "unchanged")
        opened.assert_not_called()
        with mock.patch("builtins.open", wraps=open) as opened:
            self.assertTrue(crate.save(force=True), "forced")
        opened.assert_called_once_with(self.file, "wb")
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


if __name__ == "__main__":
    unittest.main()
