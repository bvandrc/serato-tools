# pylint: disable=protected-access
import unittest
import os

from src.serato_tools.track_waveform import TrackWaveform


class TestCase(unittest.TestCase):
    def test_parse(self):
        with open(os.path.abspath("test/data/track_waveform.bin"), mode="rb") as fp:
            file_data = fp.read()
        tags = TrackWaveform(file_data)
        self.assertEqual(tags.raw_data, file_data, "raw_data read")
        with open(os.path.abspath("test/data/track_waveform_parsed.bin"), mode="rb") as fp:
            expected_parsed_data = fp.read()
        self.assertEqual(
            b"".join(bytes(x) for x in list(tags.data)),
            expected_parsed_data,
            "parsed data",
        )
        self.assertEqual(
            b"".join(bytes(x) for x in list(tags.data)),
            expected_parsed_data,
            "data can be read repeatedly",
        )

    def test_untested_version_raises_at_construction(self):
        bad_data = bytes([0x99, 0x99]) + b"\x00" * 32
        with self.assertRaises(ValueError):
            TrackWaveform(bad_data)
