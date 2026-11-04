import os
import tempfile
import unittest
from unittest import mock

from src.serato_tools import usb_export


class GetCrateFilesTestCase(unittest.TestCase):
    """get_crate_files matching, against temp Subcrates/SmartCrates folders."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.crate_dir = os.path.join(tmp.name, usb_export.Crate.DIR)
        self.smart_crate_dir = os.path.join(tmp.name, usb_export.SmartCrate.DIR)
        os.makedirs(self.crate_dir)
        os.makedirs(self.smart_crate_dir)
        # patch the classes usb_export actually references, not the src.-prefixed twins
        for patch in (
            mock.patch.object(usb_export.Crate, "DIR_PATH", self.crate_dir),
            mock.patch.object(usb_export.SmartCrate, "DIR_PATH", self.smart_crate_dir),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _add_file(self, name: str, smart: bool = False):
        with open(os.path.join(self.smart_crate_dir if smart else self.crate_dir, name), "w", encoding="utf-8"):
            pass

    def _matched_names(self, pattern: str) -> set[str]:
        return {os.path.basename(f) for f in usb_export.get_crate_files(pattern)}

    def test_glob_is_tried_before_regex(self):
        # "house*" is also a valid regex whose .search() would match "housing"
        self._add_file("house.crate")
        self._add_file("housing.crate")
        self.assertEqual(self._matched_names("house*"), {"house.crate"})

    def test_glob_matches_both_crate_kinds(self):
        self._add_file("house.crate")
        self._add_file("house.scrate", smart=True)
        self.assertEqual(self._matched_names("*house*"), {"house.crate", "house.scrate"})

    def test_pattern_invalid_as_glob_match_falls_back_to_regex(self):
        self._add_file("deep.crate")
        self._add_file("house.crate")
        self._add_file("techno.crate")
        self.assertEqual(self._matched_names("deep|house"), {"deep.crate", "house.crate"})

    def test_non_crate_files_are_never_matched(self):
        self._add_file("house.crate")
        self._add_file(".DS_Store")
        self._add_file("notes.txt")
        self.assertEqual(self._matched_names("*"), {"house.crate"})

    def test_missing_smart_crates_folder_is_no_smart_crates(self):
        self._add_file("house.crate")
        os.rmdir(self.smart_crate_dir)
        self.assertEqual(self._matched_names("*"), {"house.crate"})

    def test_invalid_regex_with_no_glob_match_is_empty(self):
        self._add_file("house.crate")
        self.assertEqual(self._matched_names("*[techno*"), set())


class TestCase(unittest.TestCase):
    def _run_main(self, drive: str, system: str) -> str:
        """Runs the CLI with `--drive drive` as if on `system`, and returns the drive folder it exports to."""
        argv = ["serato_usb_export", "--drive", drive, "--crates", "*"]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(usb_export.platform, "system", return_value=system),
            mock.patch.object(usb_export, "get_crate_files", return_value=[]),
            mock.patch.object(usb_export, "copy_crates_to_usb") as copy_crates_to_usb,
        ):
            usb_export.main()
        return copy_crates_to_usb.call_args.kwargs["dest_drive_dir"]

    def test_drive_letter_becomes_drive_root(self):
        self.assertEqual(self._run_main("E", "Windows"), "E:\\")

    def test_drive_folder_is_kept(self):
        self.assertEqual(self._run_main("/Volumes/USB", "Darwin"), "/Volumes/USB")


if __name__ == "__main__":
    unittest.main()
