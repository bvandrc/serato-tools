import unittest
from unittest import mock

from src.serato_tools import usb_export


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
