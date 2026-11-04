import unittest
from unittest import mock
import os
import shutil
import tempfile

from serato_tools.track import Track
from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain


class TestCase(unittest.TestCase):
    def setUp(self):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        self.path = os.path.join(tmp_dir.name, "test.mp3")
        shutil.copy("test/data/test_mp3.mp3", self.path)

    def count_writes(self, track: Track) -> mock.MagicMock:
        """Patches `track`'s file save to also count its calls, in the returned mock."""
        patcher = mock.patch.object(track.tagfile, "save", wraps=track.tagfile.save)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def read_all_tags(self, track: Track):
        return [track.cues_v2, track.cues_v1, track.beatgrid, track.autotags, track.waveform, track.gain]

    def test_reads_each_tag_from_one_open_file(self):
        track = Track(self.path)

        for tag in self.read_all_tags(track):
            self.assertIs(tag.tagfile, track.tagfile, f"{type(tag).__name__} shares the open file")
        self.assertIs(track.cues_v2, track.cues_v2, "each tag read once")
        self.assertEqual(track.cues_v2.get_track_color(), TrackCuesV2(self.path).get_track_color())
        self.assertEqual(track.autotags.bpm, TrackAutotags(self.path).bpm)
        self.assertEqual(track.gain.gain, TrackGain(self.path).gain)

    def test_save_without_changes_doesnt_write(self):
        track = Track(self.path)
        self.read_all_tags(track)
        writes = self.count_writes(track)

        self.assertFalse(track.save())
        writes.assert_not_called()

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

    def test_set_track_color(self):
        track = Track(self.path)
        track.set_track_color(TrackCuesV2.TrackColors.RED)
        track.save()

        self.assertEqual(Track(self.path).cues_v2.get_track_color(), TrackCuesV2.TrackColors.RED.value)

    def test_save_keeps_a_deleted_tags_v1_deleted(self):
        track = Track(self.path)
        self.assertIsNotNone(track.cues_v1.entries, "fixture has the v1 tag, read before it's deleted")
        track.cues_v2.set_track_color(TrackCuesV2.TrackColors.RED)  # deletes the v1 tag, by default
        track.save()

        self.assertNotIn(f"GEOB:{TrackCuesV1.GEOB_KEY}", Track(self.path).tagfile, "unchanged v1 tag not restored")

    def test_save_writes_deletions(self):
        for name, key in (("autotags", f"GEOB:{TrackAutotags.GEOB_KEY}"), ("gain", TrackGain.RVA2_KEY)):
            with self.subTest(name):
                shutil.copy("test/data/test_mp3.mp3", self.path)
                track = Track(self.path)
                getattr(track, name).delete()

                self.assertTrue(track.save(), "deletion alone is a change")
                self.assertNotIn(key, Track(self.path).tagfile)


if __name__ == "__main__":
    unittest.main()
