"""Tests of TrackCuesV1: byte-exact parsing and serialization of the legacy Serato Markers_ tag."""

# pylint: disable=protected-access
import unittest

from serato_tools.track_cues_v1 import TrackCuesV1

from test.helpers import read_bytes


class TestCase(unittest.TestCase):
    def setUp(self):
        self.file_data = read_bytes("test/data/track_cues_v1.bin")

    def test_parse_and_serialize(self):
        tags = TrackCuesV1(self.file_data)
        unset = "start_position_set=False, start_position=None, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\x00\\x00\\x00'"
        self.assertEqual(
            [str(e) for e in tags.entries],
            [
                "Entry(start_position_set=True, start_position=0, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\xcc\\x00\\x00', type=<EntryType.CUE: 1>, is_locked=0)",
                "Entry(start_position_set=True, start_position=218456, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\xcc\\x88\\x00', type=<EntryType.CUE: 1>, is_locked=0)",
                "Entry(start_position_set=True, start_position=60004, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\x00\\x00\\xcc', type=<EntryType.CUE: 1>, is_locked=0)",
                *[f"Entry({unset}, type=<EntryType.INVALID: 0>, is_locked=0)"] * 2,
                *[f"Entry({unset}, type=<EntryType.LOOP: 3>, is_locked=0)"] * 9,
                "Color(color=b'\\xff\\xff\\xff')",
            ],
            "parsed entries: 3 cues, 2 unset cues, 9 unset loops, and the track color",
        )
        tags._serialize()
        self.assertEqual(tags._raw_data, self.file_data, "serialize")

    def test_serialize_without_trailing_color_raises(self):
        tags = TrackCuesV1(self.file_data)

        tags.entries = []
        with self.assertRaises(ValueError, msg="empty entries must not serialize"):
            tags._serialize()

        tags = TrackCuesV1(self.file_data)
        tags.entries = [e for e in tags.entries if not isinstance(e, TrackCuesV1.Color)]
        with self.assertRaises(ValueError, msg="entries without a trailing Color must not serialize"):
            tags._serialize()


if __name__ == "__main__":
    unittest.main()
