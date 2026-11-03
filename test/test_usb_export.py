import unittest
from unittest import mock
import os
import shutil
import tempfile

from src.serato_tools.usb_export import copy_crates_to_usb

# usb_export.py imports the installed package's classes, so build fixtures with those
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2


class TestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = os.path.realpath(self._tmp.name)
        self.source_drive, self.dest_drive = os.path.join(tmp, "Source"), os.path.join(tmp, "USB")
        self.source_serato_dir = os.path.join(self.source_drive, "_Serato_")
        os.makedirs(os.path.join(self.source_serato_dir, Crate.DIR))
        os.makedirs(os.path.join(self.source_drive, "Music"))
        os.makedirs(self.dest_drive)
        self.db_file = os.path.join(self.source_serato_dir, DatabaseV2.FILENAME)
        shutil.copy("test/data/database_v2_test.bin", self.db_file)

    def make_source_library(self, track_names: list[str]) -> str:
        """Adds the tracks to the source drive, its database, and one crate, and returns the crate's path."""
        tracks = []
        for name in track_names:
            path = os.path.join(self.source_drive, "Music", name)
            with open(path, "wb") as f:
                f.write(name.encode())
            tracks.append(path)
        db = DatabaseV2(self.db_file)
        for track in tracks:
            relpath = DatabaseV2.get_relative_path(track, db.track_path_root)
            db.entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, relpath)]))
        db.save()
        crate = Crate(os.path.join(self.source_serato_dir, Crate.DIR, "House.crate"))
        crate.add_tracks(tracks)
        crate.save()
        return crate.filepath

    def assert_exported(self, track_names: list[str]):
        dest_paths = [f"Tracks/{name}" for name in track_names]
        for name in track_names:
            self.assertTrue(os.path.isfile(os.path.join(self.dest_drive, "Tracks", name)), f"{name} copied")
        dest_serato_dir = os.path.join(self.dest_drive, "_Serato_")
        self.assertEqual(
            Crate(os.path.join(dest_serato_dir, Crate.DIR, "House.crate")).get_track_paths(),
            dest_paths,
            "crate points at the copied tracks",
        )
        self.assertCountEqual(
            DatabaseV2(os.path.join(dest_serato_dir, DatabaseV2.FILENAME)).get_track_paths(),
            dest_paths,
            "database has only the copied tracks",
        )

    def export(self, crate_file: str):
        copy_crates_to_usb(
            [crate_file],
            dest_drive_dir=self.dest_drive,
            dest_tracks_dir="Tracks",
            source_serato_dir=self.source_serato_dir,
        )

    def test_export_from_home_library(self):
        with mock.patch("os.path.ismount", return_value=False):
            crate_file = self.make_source_library(["A.mp3", "B.mp3"])
            with open(crate_file, "rb") as f:
                source_crate_bytes = f.read()
            self.export(crate_file)

        self.assert_exported(["A.mp3", "B.mp3"])
        with open(crate_file, "rb") as f:
            self.assertEqual(f.read(), source_crate_bytes, "source crate left as it was")

    def test_export_from_external_drive_library(self):
        source_drive = os.path.normcase(self.source_drive)
        with mock.patch("os.path.ismount", side_effect=lambda p: os.path.normcase(p) == source_drive):
            crate_file = self.make_source_library(["A.mp3", "B.mp3"])
            self.assertEqual(Crate(crate_file).get_track_paths(), ["Music/A.mp3", "Music/B.mp3"], "relative to drive")
            self.export(crate_file)

        self.assert_exported(["A.mp3", "B.mp3"])


if __name__ == "__main__":
    unittest.main()
