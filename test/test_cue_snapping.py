import dataclasses
import unittest

from serato_tools.cue_snapping import SnappedCue, get_snapped_position, snap_cues, snap_cues_rule
from serato_tools.track import Track
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v2 import TrackCuesV2

from test.helpers import TEST_MP3, temp_mp3


class TestCase(unittest.TestCase):
    def setUp(self):
        self.cues = TrackCuesV2(TEST_MP3)
        self.beatgrid = TrackBeatgrid(TEST_MP3)

    def first_cue_position(self) -> int:
        return self.cues._from_entries().cues[0].position  # pylint: disable=protected-access

    def nearest_beat_ms(self, position_ms: int) -> int:
        beat = self.beatgrid.find_nearest_beat(position_ms, 1)
        assert beat is not None
        return round(beat)

    def test_snap_cues(self):
        snapped = snap_cues(self.cues, self.beatgrid, 1 / 16)
        # cues 3, 5, and 6 are 1 ms off their beats, which the default min_ms_change leaves alone
        expected = [SnappedCue(0, 45104, 45146), SnappedCue(1, 67474, 67472), SnappedCue(3, 134451, 134449)]
        self.assertEqual(snapped, expected)
        positions = [cue.position for cue in self.cues._from_entries().cues]  # pylint: disable=protected-access
        self.assertEqual(positions, [45146, 67472, 112125, 134449, 156776, 201428])
        self.assertTrue(self.cues.has_changed)

    def test_snap_cues_lands_on_a_beat(self):
        snap_cues(self.cues, self.beatgrid, 1 / 16)
        for cue in self.cues._from_entries().cues:  # pylint: disable=protected-access
            beat_position = self.beatgrid.get_beat_position(cue.position)
            self.assertAlmostEqual(beat_position, round(beat_position), delta=0.01)

    def test_snap_cues_outside_tolerance_leaves_cues(self):
        position = self.first_cue_position()
        self.assertEqual(snap_cues(self.cues, self.beatgrid, 1 / 1000), [])
        self.assertEqual(self.first_cue_position(), position)
        self.assertFalse(self.cues.has_changed)

    def test_snap_ignores_1ms_by_default(self):
        beat_ms = self.nearest_beat_ms(self.first_cue_position())
        self.assertIsNone(get_snapped_position(self.beatgrid, beat_ms + 1, 1 / 8))
        self.assertIsNone(get_snapped_position(self.beatgrid, beat_ms - 1, 1 / 8))
        self.assertEqual(get_snapped_position(self.beatgrid, beat_ms + 2, 1 / 8), beat_ms)

    def test_min_ms_change_below_2_warns_at_the_caller(self):
        beat_ms = self.nearest_beat_ms(self.first_cue_position())
        with self.assertWarnsRegex(UserWarning, "min_ms_change=1") as cm:
            self.assertEqual(get_snapped_position(self.beatgrid, beat_ms + 1, 1 / 8, min_ms_change=1), beat_ms)
        self.assertEqual(cm.filename, __file__)
        with self.assertWarnsRegex(UserWarning, "min_ms_change=1") as cm:
            snap_cues(self.cues, self.beatgrid, 1 / 8, min_ms_change=1)
        self.assertEqual(cm.filename, __file__)

    def test_snap_cues_no_entries_raises(self):
        self.cues.entries = []
        with self.assertRaises(ValueError):
            snap_cues(self.cues, self.beatgrid, 1 / 8)

    def test_snap_cues_rule_combines_with_other_edits(self):
        position = self.first_cue_position()
        rule = snap_cues_rule(self.beatgrid, 1 / 16)

        def snap_and_color(track: TrackCuesV2.TrackCuesInfo) -> TrackCuesV2.TrackCuesInfo:
            snapped = rule(track) or track
            assert snapped.color is not None
            return dataclasses.replace(snapped, color=dataclasses.replace(snapped.color, color=b"\xff\x99\x99"))

        self.cues.modify_entries(snap_and_color)
        self.assertEqual(self.first_cue_position(), position + 42)
        self.assertEqual(self.cues.get_track_color(), b"\xff\x99\x99")

    def test_snap_cues_rule_returns_none_without_a_move(self):
        rule = snap_cues_rule(self.beatgrid, 1 / 1000)
        self.assertIsNone(rule(self.cues._from_entries()))  # pylint: disable=protected-access

    def test_snap_a_tracks_cues_and_save(self):
        path = temp_mp3(self)
        track = Track(path)
        position = track.cues_v2._from_entries().cues[0].position  # pylint: disable=protected-access
        snap_cues(track.cues_v2, track.beatgrid, 1 / 16)
        self.assertTrue(track.save())
        saved = TrackCuesV2(path)._from_entries().cues[0].position  # pylint: disable=protected-access
        self.assertEqual(saved, position + 42)


if __name__ == "__main__":
    unittest.main()
