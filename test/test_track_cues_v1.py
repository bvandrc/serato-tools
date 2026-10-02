# pylint: disable=protected-access
import unittest
import os

from src.serato_tools.track_cues_v1 import TrackCuesV1


class TestCase(unittest.TestCase):
    def setUp(self):
        with open(os.path.abspath("test/data/track_cues_v1.bin"), mode="rb") as fp:
            self.file_data = fp.read()

    def test_parse(self):
        tags = TrackCuesV1(self.file_data)
        self.assertEqual(tags.raw_data, self.file_data, "raw_data read")

    @unittest.skip("doesn't work with old data")
    def test_parse_and_dump(self):
        tags = TrackCuesV1(self.file_data)
        self.assertEqual(tags.raw_data, self.file_data, "raw_data read")
        tags._dump()
        self.assertEqual(tags.raw_data, self.file_data, "dump")

    def test_dump_without_trailing_color_raises(self):
        tags = TrackCuesV1(self.file_data)

        tags.entries = []
        with self.assertRaises(ValueError, msg="empty entries must not dump"):
            tags._dump()

        tags = TrackCuesV1(self.file_data)
        tags.entries = [e for e in tags.entries if not isinstance(e, TrackCuesV1.Color)]
        with self.assertRaises(ValueError, msg="entries without a trailing Color must not dump"):
            tags._dump()
