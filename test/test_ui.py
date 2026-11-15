# pylint: disable=protected-access
import unittest
from unittest import mock

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.ui import get_hex_editor, get_text_editor, open_tag_file_or_data

from test.helpers import TEST_MP3, read_bytes


class TestCase(unittest.TestCase):
    def test_a_missing_editor_raises(self):
        for get_editor, env_var in ((get_text_editor, "EDITOR"), (get_hex_editor, "HEXEDITOR")):
            with (
                self.subTest(env_var),
                mock.patch("serato_tools.utils.ui.shutil.which", return_value=None),
                self.assertRaisesRegex(FileNotFoundError, f"set {env_var}"),
            ):
                get_editor()

    def test_open_tag_file_or_data_reads_an_audio_file_or_the_tags_own_bytes(self):
        fixtures = {
            TrackCuesV2: "track_cues_v2",
            TrackCuesV1: "track_cues_v1",
            TrackBeatgrid: "track_beatgrid",
            TrackAutotags: "track_autotags",
            TrackWaveform: "track_waveform",
        }
        for tag_class, name in fixtures.items():
            with self.subTest(tag_class.__name__):
                data_file = f"test/data/{name}.bin"
                tags = open_tag_file_or_data(tag_class, data_file)
                self.assertIsNone(tags.tagfile, "read as bytes")
                self.assertEqual(tags._raw_data, read_bytes(data_file))
                self.assertIsNotNone(open_tag_file_or_data(tag_class, TEST_MP3).tagfile, "read as audio")


if __name__ == "__main__":
    unittest.main()
