# pylint: disable=protected-access
import unittest
import os

from serato_tools.track_cues_v1 import TrackCuesV1


class TestCase(unittest.TestCase):
    def setUp(self):
        with open(os.path.abspath("test/data/track_cues_v1.bin"), mode="rb") as fp:
            self.file_data = fp.read()

    def test_parse(self):
        tags = TrackCuesV1(self.file_data)
        self.assertEqual(tags._raw_data, self.file_data, "raw_data read")  # pylint: disable=protected-access

    def test_parse_and_serialize(self):
        tags = TrackCuesV1(self.file_data)
        self.assertEqual(tags._raw_data, self.file_data, "raw_data read")  # pylint: disable=protected-access
        tags._serialize()
        self.assertEqual(tags._raw_data, self.file_data, "serialize")  # pylint: disable=protected-access

    def test_serialize_without_trailing_color_raises(self):
        tags = TrackCuesV1(self.file_data)

        tags.entries = []
        with self.assertRaises(ValueError, msg="empty entries must not serialize"):
            tags._serialize()

        tags = TrackCuesV1(self.file_data)
        tags.entries = [e for e in tags.entries if not isinstance(e, TrackCuesV1.Color)]
        with self.assertRaises(ValueError, msg="entries without a trailing Color must not serialize"):
            tags._serialize()

    def test_a_tag_unlike_seratos_raises(self):
        # track_cues_v1.bin's entries: 0-2 are set cues, 3-4 unset cues, and 5-13 unset loops
        def entry_byte(entry: int, offset: int) -> int:
            return 6 + 0x16 * entry + offset

        def changed(index: int, value: bytes) -> bytes:
            return self.file_data[:index] + value + self.file_data[index + len(value) :]

        cases = {
            "13 entries": changed(2, b"\x00\x00\x00\x0d")[: -0x16 - 4] + self.file_data[-4:],
            "a loop in a cue's place": changed(entry_byte(0, 20), b"\x03"),
            "a cue in a loop's place": changed(entry_byte(5, 20), b"\x01"),
            "a locked cue": changed(entry_byte(0, 21), b"\x01"),
            "an unset position that isn't 7f7f7f7f": changed(entry_byte(3, 1), b"\x00"),
            "an unexpected field5": changed(entry_byte(0, 10), b"\x01"),
            "trailing bytes": self.file_data + b"\x00",
        }
        for name, data in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                TrackCuesV1(data)

    def test_untested_version_raises_at_construction(self):
        with self.assertRaises(ValueError):
            TrackCuesV1(bytes([0x99, 0x99]))
