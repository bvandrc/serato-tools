import unittest

from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import NoWaveformError

from test.helpers import mp3_without, read_bytes

WAVEFORM = "test/data/track_waveform.bin"


class TestCase(unittest.TestCase):
    def test_parse(self):
        tags = TrackWaveform(read_bytes(WAVEFORM))
        self.assertEqual(
            b"".join(bytes(x) for x in list(tags.data)),
            read_bytes("test/data/track_waveform_parsed.bin"),
            "parsed data",
        )

    def test_without_a_waveform_raises(self):
        path = mp3_without(self, TrackWaveform.GEOB_KEY)
        with self.assertRaises(NoWaveformError) as caught:
            TrackWaveform(path)
        self.assertEqual(caught.exception.filename, path)

    def test_a_partial_row_raises(self):
        with self.assertRaisesRegex(ValueError, "row of 5 bytes"):
            TrackWaveform(read_bytes(WAVEFORM) + b"\x00" * 5)


if __name__ == "__main__":
    unittest.main()
