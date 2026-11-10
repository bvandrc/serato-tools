import dataclasses
import unittest
from unittest import mock

from serato_tools.track import Track
from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain

from test.helpers import temp_mp3


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


if __name__ == "__main__":
    unittest.main()
