# pylint: disable=protected-access
import struct
import unittest
from unittest import mock

from mutagen.mp3 import MP3

from serato_tools.track_beatgrid import TrackBeatgrid, main
from serato_tools.utils.beatgrid_analyze import BeatGridInfo
from serato_tools.utils.track_tags import GeobKeys, NoBeatgridError, set_geob

from test.helpers import TEST_MP3, read_bytes, temp_mp3

Marker = TrackBeatgrid.NonTerminalBeatgridMarker
Last = TrackBeatgrid.TerminalBeatgridMarker

# 4 beats at 60 BPM, 8 at 240, then 120 to the end
GRID = (Marker(0.0, 4), Marker(4.0, 8), Last(6.0, 120.0))


def grid_bytes(markers: tuple[Marker | Last, ...]) -> bytes:
    """The tag's bytes for a grid of `markers`."""
    data = b"\x01\x00" + struct.pack(">I", len(markers))
    for marker in markers:
        data += struct.pack(">f", marker.position_s)
        data += struct.pack(">f" if isinstance(marker, Last) else ">I", marker[1])
    return data + b"\x00"


class TestCase(unittest.TestCase):
    def mp3_with_grid(self, markers: tuple[Marker | Last, ...]) -> str:
        path = temp_mp3(self)
        tagfile = MP3(path)
        set_geob(tagfile, GeobKeys.BEATGRID, grid_bytes(markers))
        tagfile.save()
        return path

    def test_get_beat_position_across_markers(self):
        beatgrid = TrackBeatgrid(grid_bytes(GRID))
        for position_ms, beats in ((0, 0), (2000, 2), (4000, 4), (5000, 8), (6000, 12), (7000, 14)):
            with self.subTest(position_ms):
                self.assertAlmostEqual(beatgrid.get_beat_position(position_ms), beats)

    def test_get_beats_across_markers(self):
        beats = TrackBeatgrid(self.mp3_with_grid(GRID)).get_beats()
        self.assertEqual(
            [(beat.position_s, beat.bpm) for beat in beats[:14]],
            [
                *((float(i), 60.0) for i in range(4)),
                *((4.0 + i / 4, 240.0) for i in range(8)),
                (6.0, 120.0),
                (6.5, 120.0),
            ],
        )
        self.assertLessEqual(beats[-1].position_s, MP3(TEST_MP3).info.length, "to the end of the track")

    def test_analyze_and_write_replaces_the_beats_found(self):
        beatgrid = TrackBeatgrid(self.mp3_with_grid(GRID))
        beatgrid.get_beats()
        analyzed = BeatGridInfo(100.0, [], 1.0, 0.0, 1.0, downbeats=[0.5, 2.9])
        with mock.patch("serato_tools.utils.beatgrid_analyze.analyze_beatgrid", return_value=analyzed):
            beatgrid.analyze_and_write()
        self.assertEqual(beatgrid.find_nearest_beat(520, 0.1), 500.0, "the new grid's first beat")

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
        cases = {
            "a marker with 0 beats": (Marker(1.0, 0), Last(2.0, 120.0)),
            "a marker at the same position as the one before": (Marker(1.0, 4), Last(1.0, 120.0)),
            "a marker before the one before": (Marker(1.0, 4), Marker(3.0, 4), Last(2.0, 120.0)),
            "a BPM of 0": (Marker(1.0, 4), Last(2.0, 0.0)),
            "a NaN BPM": (Last(2.0, float("nan")),),
        }
        for name, markers in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError, msg="parsing"):
                    TrackBeatgrid(grid_bytes(markers))

                tags = TrackBeatgrid(read_bytes("test/data/track_beatgrid.bin"))
                tags.entries = (*markers, TrackBeatgrid.Footer(0))
                with self.assertRaises(ValueError, msg="saving"):
                    tags._serialize()

    def no_beatgrid_mp3(self) -> str:
        path = temp_mp3(self)
        beatgrid = TrackBeatgrid(path)
        beatgrid.delete()
        beatgrid.save()
        return path

    def test_without_a_beatgrid_finding_beats_raises(self):
        # rather than returning None, which reads as "don't move the cue"
        path = self.no_beatgrid_mp3()
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
