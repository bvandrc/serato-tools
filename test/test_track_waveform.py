import unittest

from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import NoWaveformError, del_geob, open_tagfile

from test.helpers import read_bytes, temp_mp3


class TestCase(unittest.TestCase):
    def test_parse(self):
        tags = TrackWaveform(read_bytes("test/data/track_waveform.bin"))
        self.assertEqual(
            b"".join(bytes(x) for x in list(tags.data)),
            read_bytes("test/data/track_waveform_parsed.bin"),
            "parsed data",
        )

    def test_without_a_waveform_raises(self):
        path = temp_mp3(self)
        tagfile = open_tagfile(path)
        del_geob(tagfile, TrackWaveform.GEOB_KEY)
        tagfile.save()
        with self.assertRaises(NoWaveformError) as caught:
            TrackWaveform(path)
        self.assertEqual(caught.exception.filename, path)

    def test_a_partial_row_raises(self):
        with self.assertRaisesRegex(ValueError, "row of 5 bytes"):
            TrackWaveform(read_bytes("test/data/track_waveform.bin") + b"\x00" * 5)


if __name__ == "__main__":
    unittest.main()
