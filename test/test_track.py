import dataclasses
import unittest
from unittest import mock

from serato_tools.track import Track
from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain

from test.helpers import temp_mp3, untagged_mp3


class TestCase(unittest.TestCase):
    def setUp(self):
        self.path = temp_mp3(self)

    def count_writes(self, track: Track) -> mock.MagicMock:
        """Patches `track`'s file save to also count its calls, in the returned mock."""
        patcher = mock.patch.object(track.tagfile, "save", wraps=track.tagfile.save)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def read_all_tags(self, track: Track):
        return [track.cues_v2, track.cues_v1, track.beatgrid, track.autotags, track.waveform, track.gain]

    def test_reads_each_tag_from_one_open_file(self):
        track = Track(self.path, waveform=True)

        for tag in self.read_all_tags(track):
            self.assertIs(tag.tagfile, track.tagfile, f"{type(tag).__name__} shares the open file")
        self.assertIs(track.cues_v2, track.cues_v2, "each tag read once")
        self.assertEqual(track.cues_v2.get_track_color(), TrackCuesV2(self.path).get_track_color())
        self.assertEqual(track.autotags.bpm, TrackAutotags(self.path).bpm)
        self.assertEqual(track.gain.gain, TrackGain(self.path).gain)

    def test_parses_every_tag_but_the_waveform_by_default(self):
        with mock.patch("serato_tools.track.TrackWaveform") as waveform:
            track = Track(self.path)
        waveform.assert_not_called()
        with self.assertRaisesRegex(ValueError, "waveform=True"):
            _ = track.waveform
        self.assertIsNotNone(track.cues_v1.entries, "the other tags are parsed")

    def test_tag_passed_false_isnt_parsed_or_saved(self):
        with mock.patch("serato_tools.track.TrackCuesV1") as cues_v1:
            track = Track(self.path, cues_v1=False)
        cues_v1.assert_not_called()
        with self.assertRaisesRegex(ValueError, "cues_v1=True"):
            _ = track.cues_v1

        track = Track(self.path, cues_v2=False, cues_v1=False, beatgrid=False, autotags=False, gain=False)
        writes = self.count_writes(track)
        self.assertFalse(track.save(), "no tags, nothing to save")
        writes.assert_not_called()

    def test_save_without_changes_doesnt_write(self):
        track = Track(self.path, waveform=True)
        self.read_all_tags(track)
        writes = self.count_writes(track)

        self.assertFalse(track.save())
        writes.assert_not_called()

    def test_has_changed(self):
        track = Track(self.path)
        self.assertFalse(track.has_changed, "as read")
        track.autotags.set(bpm=128)
        self.assertTrue(track.has_changed, "one tag changed")
        track.save()
        self.assertFalse(track.has_changed, "saved")

    def test_save_writes_every_change_at_once(self):
        track = Track(self.path)
        track.cues_v2.set_track_color(TrackCuesV2.TrackColors.RED)
        track.autotags.set(bpm=128)
        track.gain.set(gain=-2.5)
        writes = self.count_writes(track)

        self.assertTrue(track.save())
        writes.assert_called_once()
        saved = Track(self.path)
        self.assertEqual(saved.cues_v2.get_track_color(), TrackCuesV2.TrackColors.RED.value)
        self.assertEqual(saved.autotags.bpm, 128)
        self.assertAlmostEqual(saved.gain.gain or 0.0, -2.5, places=2)

    def test_track_color(self):
        track = Track(self.path)
        self.assertEqual(track.get_track_color(), TrackCuesV2(self.path).get_track_color(), "read from cues_v2")
        track.set_track_color(TrackCuesV2.TrackColors.RED)
        track.save()

        self.assertEqual(Track(self.path).get_track_color(), TrackCuesV2.TrackColors.RED.value)

    def test_beatgrid_lock(self):
        track = Track(self.path)
        self.assertFalse(track.is_beatgrid_locked(), "fixture is unlocked")
        track.set_beatgrid_locked(True)
        self.assertTrue(track.is_beatgrid_locked())
        track.save()

        self.assertTrue(Track(self.path).is_beatgrid_locked(), "saved")

    def test_save_keeps_a_deleted_tags_v1_deleted(self):
        track = Track(self.path)
        self.assertIsNotNone(track.cues_v1.entries, "fixture has the v1 tag, read before it's deleted")
        track.cues_v2.set_track_color(TrackCuesV2.TrackColors.RED)  # deletes the v1 tag, by default
        track.save()

        self.assertNotIn(f"GEOB:{TrackCuesV1.GEOB_KEY}", Track(self.path).tagfile, "unchanged v1 tag not restored")

    def test_save_keeps_tags_v1_when_told_to(self):
        track = Track(self.path)
        track.set_track_color(TrackCuesV2.TrackColors.RED)
        track.save(delete_tags_v1=False)

        self.assertIn(f"GEOB:{TrackCuesV1.GEOB_KEY}", Track(self.path).tagfile)

    def test_delete_tags_v1_on_an_edit_is_deprecated(self):
        track = Track(self.path)
        with self.assertWarns(DeprecationWarning) as caught:
            track.set_track_color(TrackCuesV2.TrackColors.RED, delete_tags_v1=False)
        self.assertEqual(caught.filename, __file__, "points at the caller, not at Track")
        track.save()

        self.assertIn(f"GEOB:{TrackCuesV1.GEOB_KEY}", Track(self.path).tagfile, "False still keeps the v1 tag")

    def test_an_unwritten_cue_edit_keeps_tags_v1_when_another_tag_saves(self):
        def changed_back(cues: TrackCuesV2):
            color = TrackCuesV2.TrackColors(cues.get_track_color())
            cues.set_track_color(TrackCuesV2.TrackColors.RED)
            cues.set_track_color(color)

        for name, edit in (
            ("changed nothing", lambda cues: cues.modify_entries(dataclasses.replace)),
            ("changed back", changed_back),
        ):
            with self.subTest(name):
                self.path = temp_mp3(self)
                track = Track(self.path)
                edit(track.cues_v2)
                track.autotags.set(bpm=128)
                track.save()

                self.assertIn(f"GEOB:{TrackCuesV1.GEOB_KEY}", Track(self.path).tagfile)

    def test_save_writes_deletions(self):
        for name, key in (("autotags", f"GEOB:{TrackAutotags.GEOB_KEY}"), ("gain", TrackGain.RVA2_KEY)):
            with self.subTest(name):
                self.path = temp_mp3(self)
                track = Track(self.path)
                getattr(track, name).delete()

                self.assertTrue(track.save(), "deletion alone is a change")
                self.assertNotIn(key, Track(self.path).tagfile)

    def cue_positions(self, track: Track) -> list[int]:
        return [cue.position for cue in track.cues_v2._from_entries().cues]  # pylint: disable=protected-access

    def test_snap_cues(self):
        track = Track(self.path)
        snapped = track.snap_cues(1 / 16)
        # cues 3, 5, and 6 are 1 ms off their beats, which the default min_ms_change leaves alone
        self.assertEqual(
            snapped,
            [Track.SnappedCue(0, 45104, 45146), Track.SnappedCue(1, 67474, 67472), Track.SnappedCue(3, 134451, 134449)],
        )
        expected = [45146, 67472, 112125, 134449, 156776, 201428]
        self.assertEqual(self.cue_positions(track), expected)
        for position in expected:
            beat_position = track.beatgrid.get_beat_position(position)
            self.assertAlmostEqual(beat_position, round(beat_position), delta=0.01, msg="on a beat")

        self.assertTrue(track.save())
        self.assertEqual(self.cue_positions(Track(self.path)), expected, "saved")

    def test_snap_cues_outside_tolerance_leaves_cues(self):
        track = Track(self.path)
        positions = self.cue_positions(track)
        self.assertEqual(track.snap_cues(1 / 1000), [])
        self.assertEqual(self.cue_positions(track), positions)
        self.assertFalse(track.has_changed)

    def test_snap_cues_needs_only_cues_v2_and_beatgrid(self):
        track = Track(self.path, cues_v1=False, autotags=False, gain=False)
        self.assertTrue(track.snap_cues(1 / 16))
        for name in ("cues_v2", "beatgrid"):
            with self.subTest(name), self.assertRaisesRegex(ValueError, f"{name}=True"):
                Track(self.path, **{name: False}).snap_cues(1 / 16)
        with self.assertRaisesRegex(ValueError, "beatgrid=True"):
            Track(untagged_mp3(self), beatgrid=False).snap_cues(1 / 16)  # even with no cues to move

    def test_snap_cues_no_entries_raises(self):
        track = Track(untagged_mp3(self))
        with self.assertRaises(ValueError):
            track.snap_cues(1 / 8)

    def test_min_ms_change_below_2_warns_at_the_caller(self):
        track = Track(self.path)
        with self.assertWarnsRegex(UserWarning, "min_ms_change=1") as caught:
            track.snap_cues(1 / 8, min_ms_change=1)
        self.assertEqual(caught.filename, __file__)


if __name__ == "__main__":
    unittest.main()
