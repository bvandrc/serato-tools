# pylint: disable=protected-access
import unittest

from serato_tools.track_autotags import TrackAutotags

from test.helpers import read_bytes


class TestCase(unittest.TestCase):
    def test_parse_and_serialize(self):
        file_data = read_bytes("test/data/track_autotags.bin")
        tags = TrackAutotags(file_data)
        self.assertEqual(tags.bpm, 75.0, "parsed bpm")
        self.assertEqual(tags.autogain, -5.074, "parsed autogain")
        self.assertEqual(tags.gaindb, 0.0, "parsed gaindb")
        tags._serialize()
        self.assertEqual(tags._raw_data, file_data, "serialize")


if __name__ == "__main__":
    unittest.main()
