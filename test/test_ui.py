import unittest
from unittest import mock

from serato_tools.utils.ui import get_hex_editor, get_text_editor


class TestCase(unittest.TestCase):
    def test_a_missing_editor_raises(self):
        for get_editor, env_var in ((get_text_editor, "EDITOR"), (get_hex_editor, "HEXEDITOR")):
            with (
                self.subTest(env_var),
                mock.patch("serato_tools.utils.ui.shutil.which", return_value=None),
                self.assertRaisesRegex(FileNotFoundError, f"set {env_var}"),
            ):
                get_editor()


if __name__ == "__main__":
    unittest.main()
