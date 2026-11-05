# pylint: disable=protected-access
import unittest
import os
import struct

from serato_tools.track_beatgrid import TrackBeatgrid


class TestCase(unittest.TestCase):
    def test_parse_and_serialize(self):
        with open(os.path.abspath("test/data/track_beatgrid.bin"), mode="rb") as fp:
            file_data = fp.read()
        tags = TrackBeatgrid(file_data)
        self.assertEqual(tags._raw_data, file_data, "raw_data read")  # pylint: disable=protected-access
        assert tags.entries is not None
        self.assertEqual(
            tags.entries,
            (
                TrackBeatgrid.TerminalBeatgridMarker(position_s=0.029895611107349396, bpm=75.0),
                TrackBeatgrid.Footer(unknown=0),
            ),
            "parsed entries",
        )
        tags._serialize()
        self.assertEqual(tags._raw_data, file_data, "serialize")  # pylint: disable=protected-access

    def test_a_grid_serato_wouldnt_write_raises(self):
        Marker = TrackBeatgrid.NonTerminalBeatgridMarker
        Last = TrackBeatgrid.TerminalBeatgridMarker
        cases = {
            "a marker with 0 beats": (Marker(1.0, 0), Last(2.0, 120.0)),
            "a marker at the same position as the one before": (Marker(1.0, 4), Last(1.0, 120.0)),
            "a marker before the one before": (Marker(1.0, 4), Marker(3.0, 4), Last(2.0, 120.0)),
            "a BPM of 0": (Marker(1.0, 4), Last(2.0, 0.0)),
            "a NaN BPM": (Last(2.0, float("nan")),),
        }
        for name, markers in cases.items():
            with self.subTest(name):
                data = b"\x01\x00" + struct.pack(">I", len(markers))
                for marker in markers:
                    data += struct.pack(">f", marker.position_s)
                    data += struct.pack(">f" if isinstance(marker, Last) else ">I", marker[1])
                with self.assertRaises(ValueError, msg="parsing"):
                    TrackBeatgrid(data + b"\x00")

                with open("test/data/track_beatgrid.bin", "rb") as f:
                    tags = TrackBeatgrid(f.read())
                tags.entries = (*markers, TrackBeatgrid.Footer(0))  # pyright: ignore[reportAttributeAccessIssue]
                with self.assertRaises(ValueError, msg="saving"):
                    tags._serialize()

    def test_untested_version_raises_at_construction(self):
        with self.assertRaises(ValueError):
            TrackBeatgrid(bytes([0x99, 0x99]))
