import unittest
from unittest import mock
import os
import shutil
import tempfile

from src.serato_tools.library import Library
from src.serato_tools.utils import HOME_TRACK_PATH_ROOT, get_track_path_root

# library.py imports the installed package's classes, so build fixtures with those
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2


class TestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # stands in for an external drive's root, e.g. E:\ or /Volumes/USB
        self.drive = os.path.join(os.path.realpath(self._tmp.name), "USB")
        self.serato_dir = os.path.join(self.drive, "_Serato_")
        os.makedirs(os.path.join(self.serato_dir, Crate.DIR))
        os.makedirs(os.path.join(self.drive, "Music"))

    def as_mount(self, *mount_points: str):
        """Makes os.path.ismount report only `mount_points` as mounted, for the rest of the test."""
        mounted = {os.path.normcase(p) for p in mount_points}
        patcher = mock.patch("os.path.ismount", side_effect=lambda p: os.path.normcase(p) in mounted)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_track(self, name: str) -> str:
        path = os.path.join(self.drive, "Music", name)
        open(path, "wb").close()
        return path

    def test_root_of_external_drive_library(self):
        self.as_mount(self.drive)
        for file in [
            os.path.join(self.serato_dir, DatabaseV2.FILENAME),
            os.path.join(self.serato_dir, Crate.DIR, "House.crate"),
            os.path.join(self.serato_dir, Crate.DIR, "Serato Stems", "Stems.crate"),
        ]:
            self.assertEqual(get_track_path_root(file), self.drive, f"root of {file}")

    def test_root_of_home_library_is_its_drive_root(self):
        self.as_mount()
        drive_root = os.path.join(os.path.splitdrive(self.serato_dir)[0], os.sep)
        self.assertEqual(get_track_path_root(os.path.join(self.serato_dir, DatabaseV2.FILENAME)), drive_root)

    def test_root_of_file_outside_a_serato_folder_is_home_library_root(self):
        self.as_mount(self.drive)
        self.assertEqual(get_track_path_root(os.path.join(self.drive, "Music", "Exported.crate")), HOME_TRACK_PATH_ROOT)

    def test_paths_relative_to_given_root(self):
        track = os.path.join(self.drive, "Music", "Track.mp3")
        self.assertEqual(DatabaseV2.get_relative_path(track, self.drive), "Music/Track.mp3")
        self.assertEqual(DatabaseV2.get_full_path("Music/Track.mp3", self.drive), track)

        # a sibling folder whose name starts with the root's isn't inside it
        sibling_track = os.path.join(self.drive + "2", "Music", "Track.mp3")
        self.assertEqual(
            DatabaseV2.get_relative_path(sibling_track, self.drive),
            DatabaseV2.get_relative_path(sibling_track),
            "outside root, only the drive is dropped",
        )

    @unittest.skipUnless(os.name == "nt", "Windows drive letters")
    def test_windows_external_drive_paths(self):
        self.assertEqual(DatabaseV2.get_relative_path("E:\\Music\\Track.mp3", "E:\\"), "Music/Track.mp3")
        self.assertEqual(DatabaseV2.get_full_path("Music/Track.mp3", "E:\\"), "E:\\Music\\Track.mp3")
        self.as_mount("E:\\")
        self.assertEqual(get_track_path_root("E:\\_Serato_\\database V2"), "E:\\")

    @unittest.skipIf(os.name == "nt", "POSIX mount points")
    def test_posix_external_drive_paths(self):
        self.assertEqual(
            DatabaseV2.get_relative_path("/Volumes/USB/Music/Track.mp3", "/Volumes/USB"), "Music/Track.mp3"
        )
        self.assertEqual(DatabaseV2.get_full_path("Music/Track.mp3", "/Volumes/USB"), "/Volumes/USB/Music/Track.mp3")
        self.as_mount("/Volumes/USB")
        self.assertEqual(get_track_path_root("/Volumes/USB/_Serato_/database V2"), "/Volumes/USB")

    def test_external_drive_library_tracks(self):
        self.as_mount(self.drive)
        shutil.copy("test/data/database_v2_test.bin", os.path.join(self.serato_dir, DatabaseV2.FILENAME))
        old, kept = self.make_track("Old.mp3"), self.make_track("Kept.mp3")
        new = os.path.join(self.drive, "Music", "New.mp3")

        crate = Crate(os.path.join(self.serato_dir, Crate.DIR, "USB.crate"))
        crate.add_tracks([old, kept])
        self.assertEqual(crate.get_track_paths(), ["Music/Old.mp3", "Music/Kept.mp3"], "stored relative to the drive")
        self.assertEqual(crate.get_track_paths(include_drive=True), [old, kept], "resolved from the drive")
        crate.save()

        library = Library(self.serato_dir)
        library.rename_track_file(old, new)
        self.assertEqual(Crate(crate.filepath).get_track_paths(), ["Music/New.mp3", "Music/Kept.mp3"], "renamed")

        library.remove_track_files([new])
        self.assertEqual(Crate(crate.filepath).get_track_paths(), ["Music/Kept.mp3"], "removed")
        self.assertFalse(os.path.exists(new), "file deleted")


if __name__ == "__main__":
    unittest.main()
