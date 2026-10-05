# pylint: disable=protected-access
import unittest
import os

from src.serato_tools.track_beatgrid import TrackBeatgrid


class TestCase(unittest.TestCase):
    def test_parse_and_dump(self):
        with open(os.path.abspath("test/data/track_beatgrid.bin"), mode="rb") as fp:
            file_data = fp.read()
        tags = TrackBeatgrid(file_data)
        self.assertEqual(tags.raw_data, file_data, "raw_data read")
        assert tags.entries is not None
        self.assertEqual(
            tags.entries,
            (
                TrackBeatgrid.TerminalBeatgridMarker(position_s=0.029895611107349396, bpm=75.0),
                TrackBeatgrid.Footer(unknown=0),
            ),
            "parsed entries",
        )
        tags._dump()
        self.assertEqual(tags.raw_data, file_data, "dump")

    def test_untested_version_raises_at_construction(self):
        with self.assertRaises(ValueError):
            TrackBeatgrid(bytes([0x99, 0x99]))
