# pylint: disable=protected-access
import unittest
import os

from src.serato_tools.track_autotags import TrackAutotags


class TestCase(unittest.TestCase):
    def test_parse_and_dump(self):
        with open(os.path.abspath("test/data/track_autotags.bin"), mode="rb") as fp:
            file_data = fp.read()
        tags = TrackAutotags(file_data)
        self.assertEqual(tags.raw_data, file_data, "raw_data read")
        self.assertEqual(tags.bpm, 75.0, "parsed bpm")
        self.assertEqual(tags.autogain, -5.074, "parsed autogain")
        self.assertEqual(tags.gaindb, 0.0, "parsed gaindb")
        tags._dump()
        self.assertEqual(tags.raw_data, file_data, "dump")
