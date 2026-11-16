# pylint: disable=protected-access
import unittest
import struct
from unittest import mock

from serato_tools.track_beatgrid import TrackBeatgrid, main
from serato_tools.utils.beatgrid_analyze import BeatGridInfo
from serato_tools.utils.track_tags import NoBeatgridError

from test.helpers import read_bytes, temp_mp3


class TestCase(unittest.TestCase):
    def test_analyze_and_write_replaces_the_beats_found(self):
        beatgrid = TrackBeatgrid(temp_mp3(self))
        beatgrid.get_beats()
        analyzed = BeatGridInfo(100.0, [], 1.0, 0.0, 1.0, downbeats=[0.5, 2.9])
        with mock.patch("serato_tools.utils.beatgrid_analyze.analyze_beatgrid", return_value=analyzed):
            beatgrid.analyze_and_write()
        self.assertEqual(beatgrid.find_nearest_beat(520, 0.1), 500.0, "the new grid's first beat")

    def test_analyze_and_write_giving_an_invalid_grid_keeps_the_old_one(self):
        beatgrid = TrackBeatgrid(temp_mp3(self))
        entries, raw_data = beatgrid.entries, beatgrid._raw_data
        analyzed = BeatGridInfo(100.0, [], 1.0, 0.0, 1.0, downbeats=[2.9, 0.5])  # out of order
        with (
            mock.patch("serato_tools.utils.beatgrid_analyze.analyze_beatgrid", return_value=analyzed),
            self.assertRaises(ValueError),
        ):
            beatgrid.analyze_and_write()
        self.assertEqual((beatgrid.entries, beatgrid._raw_data), (entries, raw_data))

    def test_parse_and_serialize(self):
        file_data = read_bytes("test/data/track_beatgrid.bin")
        tags = TrackBeatgrid(file_data)
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
        self.assertEqual(tags._raw_data, file_data, "serialize")

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

                tags = TrackBeatgrid(read_bytes("test/data/track_beatgrid.bin"))
                tags.entries = (*markers, TrackBeatgrid.Footer(0))  # pyright: ignore[reportAttributeAccessIssue]
                with self.assertRaises(ValueError, msg="saving"):
                    tags._serialize()

    def no_beatgrid_mp3(self) -> str:
        path = temp_mp3(self)
        beatgrid = TrackBeatgrid(path)
        beatgrid.delete()
        beatgrid.save()
        return path

    def test_without_a_beatgrid_get_beat_position_raises(self):
        path = self.no_beatgrid_mp3()
        with self.assertRaises(NoBeatgridError) as caught:
            TrackBeatgrid(path).get_beat_position(45104)
        self.assertEqual(caught.exception.filename, path)

    def test_without_a_beatgrid_find_nearest_beat_returns_none(self):
        # as in 5.6.1: raising instead is a breaking change, left for 6.0
        self.assertIsNone(TrackBeatgrid(self.no_beatgrid_mp3()).find_nearest_beat(45104, 1 / 8))

    def test_no_beatgrid_error_from_bytes_has_no_filename(self):
        self.assertEqual(str(NoBeatgridError()), "no Serato BeatGrid tag")

    def test_cli_without_a_beatgrid_exits_with_the_error(self):
        path = self.no_beatgrid_mp3()
        with mock.patch("sys.argv", ["serato_beatgrid", path]), self.assertRaises(SystemExit) as caught:
            main()
        self.assertEqual(caught.exception.code, f"no Serato BeatGrid tag: {path}")

    def test_bytes_after_the_footer_raise(self):
        with self.assertRaisesRegex(ValueError, "1 bytes after its footer"):
            TrackBeatgrid(read_bytes("test/data/track_beatgrid.bin") + b"\x00")

    def test_entries_out_of_order_raise_on_saving(self):
        tags = TrackBeatgrid(read_bytes("test/data/track_beatgrid.bin"))
        for name, entries in (
            ("no terminal marker", (TrackBeatgrid.NonTerminalBeatgridMarker(1.0, 4), TrackBeatgrid.Footer(0))),
            ("the footer first", (TrackBeatgrid.Footer(0), TrackBeatgrid.TerminalBeatgridMarker(2.0, 120.0))),
        ):
            with self.subTest(name), self.assertRaises(ValueError):
                tags.entries = entries  # pyright: ignore[reportAttributeAccessIssue]
                tags._serialize()

    def test_analyzing_a_tag_read_from_bytes_raises(self):
        with self.assertRaisesRegex(ValueError, "read from bytes"):
            TrackBeatgrid(read_bytes("test/data/track_beatgrid.bin")).analyze_and_write()
