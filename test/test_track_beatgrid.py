# pylint: disable=protected-access
import struct
import unittest

from serato_tools.track_beatgrid import TrackBeatgrid, main
from serato_tools.utils.track_tags import NoBeatgridError

from test.helpers.cli import cli_args
from test.helpers.files import read_bytes
from test.helpers.track_tags import TEST_MP3, mp3_without

BEATGRID = "test/data/track_beatgrid.bin"


class TestCase(unittest.TestCase):
    def test_parse(self):
        tags = TrackBeatgrid(read_bytes(BEATGRID))
        assert tags.entries is not None
        self.assertEqual(
            tags.entries,
            (
                TrackBeatgrid.TerminalBeatgridMarker(position_s=0.029895611107349396, bpm=75.0),
                TrackBeatgrid.Footer(unknown=0),
            ),
            "parsed entries",
        )

    def test_get_snapped_position_ignores_1ms_by_default(self):
        beatgrid = TrackBeatgrid(TEST_MP3)
        beat = beatgrid.find_nearest_beat(45104, 1)  # the test mp3's first cue, 42 ms before a beat
        assert beat is not None
        beat_ms = round(beat)
        self.assertIsNone(beatgrid.get_snapped_position(beat_ms + 1, 1 / 8))
        self.assertIsNone(beatgrid.get_snapped_position(beat_ms - 1, 1 / 8))
        self.assertEqual(beatgrid.get_snapped_position(beat_ms + 2, 1 / 8), beat_ms)
        self.assertEqual(beatgrid.get_snapped_position(beat_ms + 1, 1 / 8, min_ms_change=1), beat_ms)
        self.assertIsNone(beatgrid.get_snapped_position(beat_ms + 60, 1 / 1000), "outside tolerance")

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

                tags = TrackBeatgrid(read_bytes(BEATGRID))
                tags.entries = (*markers, TrackBeatgrid.Footer(0))
                with self.assertRaises(ValueError, msg="saving"):
                    tags._serialize()

    def test_without_a_beatgrid_finding_beats_raises(self):
        # rather than returning None, which reads as "don't move the cue"
        path = mp3_without(self, TrackBeatgrid.GEOB_KEY)
        beatgrid = TrackBeatgrid(path)
        for name, find in (
            ("get_snapped_position", lambda: beatgrid.get_snapped_position(45104, 1 / 8)),
            ("find_nearest_beat", lambda: beatgrid.find_nearest_beat(45104, 1 / 8)),
            ("get_beat_position", lambda: beatgrid.get_beat_position(45104)),
        ):
            with self.subTest(name), self.assertRaises(NoBeatgridError) as caught:
                find()
            self.assertEqual(caught.exception.filename, path)

    def test_no_beatgrid_error_from_bytes_has_no_filename(self):
        self.assertEqual(str(NoBeatgridError()), "no Serato BeatGrid tag")

    def test_cli_without_a_beatgrid_exits_with_the_error(self):
        path = mp3_without(self, TrackBeatgrid.GEOB_KEY)
        with cli_args("serato_beatgrid", path), self.assertRaises(SystemExit) as caught:
            main()
        self.assertEqual(caught.exception.code, f"no Serato BeatGrid tag: {path}")

    def test_bytes_after_the_footer_raise(self):
        with self.assertRaisesRegex(ValueError, "1 bytes after its footer"):
            TrackBeatgrid(read_bytes(BEATGRID) + b"\x00")

    def test_entries_out_of_order_raise_on_saving(self):
        tags = TrackBeatgrid(read_bytes(BEATGRID))
        for name, entries in (
            ("no terminal marker", (TrackBeatgrid.NonTerminalBeatgridMarker(1.0, 4), TrackBeatgrid.Footer(0))),
            ("the footer first", (TrackBeatgrid.Footer(0), TrackBeatgrid.TerminalBeatgridMarker(2.0, 120.0))),
        ):
            with self.subTest(name), self.assertRaises(ValueError):
                tags.entries = entries  # pyright: ignore[reportAttributeAccessIssue]
                tags._serialize()
