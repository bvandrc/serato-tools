"""Tests of TrackWaveform: parsing the Serato Overview tag."""

import unittest

from serato_tools.track_waveform import TrackWaveform

from test.helpers import read_bytes


class TestCase(unittest.TestCase):
    def test_parse(self):
        tags = TrackWaveform(read_bytes("test/data/track_waveform.bin"))
        self.assertEqual(
            b"".join(bytes(x) for x in list(tags.data)),
            read_bytes("test/data/track_waveform_parsed.bin"),
            "parsed data",
        )


if __name__ == "__main__":
    unittest.main()
