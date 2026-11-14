import os
import shutil
import unittest

from serato_tools.track_autotags import TrackAutotags
from serato_tools.utils.track_tags import open_tag_file_or_data
from serato_tools.utils.ui import save_tag_file_or_data

from test.helpers import read_bytes, temp_dir, temp_mp3


class TestCase(unittest.TestCase):
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
