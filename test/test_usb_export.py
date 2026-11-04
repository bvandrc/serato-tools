import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from serato_tools import usb_export


class GetCrateFilesTestCase(unittest.TestCase):
    """get_crate_files matching, against temp Subcrates/SmartCrates folders."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # stands in for a library's _Serato_ folder
        self.serato_dir = tmp.name
        self.crate_dir = os.path.join(self.serato_dir, usb_export.Crate.DIR)
        self.smart_crate_dir = os.path.join(self.serato_dir, usb_export.SmartCrate.DIR)
        os.makedirs(self.crate_dir)
        os.makedirs(self.smart_crate_dir)

    def _add_file(self, name: str, smart: bool = False):
        with open(os.path.join(self.smart_crate_dir if smart else self.crate_dir, name), "w", encoding="utf-8"):
            pass

    def _matched_names(self, pattern: str) -> set[str]:
        return {os.path.basename(f) for f in usb_export.get_crate_files(pattern, self.serato_dir)}

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
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # stands in for the drive of the library to export from
        self.source_drive = os.path.realpath(self._tmp.name)
        self.source_serato_dir = os.path.join(self.source_drive, "_Serato_")
        os.makedirs(self.source_serato_dir)

    def _run_main(self, drive: str = "/Volumes/USB", source: str | None = None, system: str = "Darwin"):
        """Runs the CLI as if on `system`, and returns the keyword arguments it calls `copy_crates_to_usb` with.

        `source` defaults to the test's source library.
        """
        source = self.source_serato_dir if source is None else source
        argv = ["serato_usb_export", "--drive", drive, "--crates", "*", "--source", source]
        with (
            mock.patch("sys.argv", argv),
            mock.patch.object(usb_export.platform, "system", return_value=system),
            mock.patch.object(usb_export, "get_crate_files", return_value=[]),
            mock.patch.object(usb_export, "copy_crates_to_usb") as copy_crates_to_usb,
        ):
            usb_export.main()
        return copy_crates_to_usb.call_args.kwargs

    def test_drive_letter_becomes_drive_root(self):
        self.assertEqual(self._run_main(drive="E", system="Windows")["dest_drive_dir"], "E:\\")

    def test_drive_folder_is_kept(self):
        self.assertEqual(self._run_main(drive="/Volumes/USB")["dest_drive_dir"], "/Volumes/USB")

    def test_source_serato_folder_is_kept(self):
        self.assertEqual(self._run_main(source=self.source_serato_dir)["source_serato_dir"], self.source_serato_dir)

    def test_source_drive_finds_its_serato_folder(self):
        self.assertEqual(self._run_main(source=self.source_drive)["source_serato_dir"], self.source_serato_dir)

    def test_source_folder_without_library_is_an_error(self):
        with contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
            self._run_main(source=os.path.join(self.source_drive, "Nope"))
        self.assertIn("no Serato library folder", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
