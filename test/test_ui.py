# pylint: disable=protected-access
import os
import shutil
import unittest

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.ui import open_tag_file_or_data, save_tag_file_or_data

from test.helpers import TEST_MP3, read_bytes, temp_dir, temp_mp3


class TestCase(unittest.TestCase):
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

    def test_save_tag_file_or_data_writes_a_changed_data_file_back(self):
        data_file = os.path.join(temp_dir(self), "Serato Autotags.octet-stream")
        shutil.copy("test/data/track_autotags.bin", data_file)
        tags = open_tag_file_or_data(TrackAutotags, data_file)
        self.assertFalse(save_tag_file_or_data(tags, data_file), "unchanged")
        tags.set(bpm=128)
        self.assertTrue(save_tag_file_or_data(tags, data_file))
        self.assertEqual(TrackAutotags(read_bytes(data_file)).bpm, 128)

    def test_save_tag_file_or_data_saves_an_audio_file(self):
        path = temp_mp3(self)
        tags = open_tag_file_or_data(TrackAutotags, path)
        tags.set(bpm=128)
        self.assertTrue(save_tag_file_or_data(tags, path))
        self.assertEqual(TrackAutotags(path).bpm, 128)


if __name__ == "__main__":
    unittest.main()
