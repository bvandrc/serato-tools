# pylint: disable=protected-access
import unittest

from mutagen.mp3 import MP3

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_tagdump import get_serato_tagdata
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils import track_tags
from serato_tools.utils.track_tags import ID3FileTag, SeratoGeobTag, get_geob

from test.helpers import TEST_MP3, temp_mp3


class TestCase(unittest.TestCase):
    def test_delete_then_save_persists_deletion(self):
        for tag_class in (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags, TrackWaveform):
            with self.subTest(tag_class.__name__):
                path = temp_mp3(self)
                self.assertIsNotNone(get_geob(MP3(path), tag_class.GEOB_KEY), "fixture has the tag")
                tags = tag_class(path)
                tags.delete()
                tags.save()
                self.assertIsNone(get_geob(MP3(path), tag_class.GEOB_KEY), "deletion saved")

    def test_untested_version_raises_at_construction(self):
        for tag_class, data in (
            (TrackCuesV2, bytes([0x99, 0x99])),
            (TrackCuesV1, bytes([0x99, 0x99])),
            (TrackBeatgrid, bytes([0x99, 0x99])),
            (TrackAutotags, bytes([0x99, 0x99])),
            # the waveform reads rows of 16 bytes past the version, so give it some
            (TrackWaveform, bytes([0x99, 0x99]) + b"\x00" * 32),
        ):
            with self.subTest(tag_class.__name__), self.assertRaisesRegex(ValueError, "Untested Serato tag version"):
                tag_class(data)

    def test_tagdump_reads_each_geob(self):
        dumped = dict(get_serato_tagdata(MP3(TEST_MP3)))
        self.assertEqual(dumped["Serato Autotags"], TrackAutotags(TEST_MP3)._raw_data)
        self.assertEqual(dumped["Serato Markers2"], TrackCuesV2(TEST_MP3)._raw_data)

    def test_old_class_names_still_work_but_warn(self):
        for old, new in (("SeratoTrack", ID3FileTag), ("SeratoTag", SeratoGeobTag)):
            with self.subTest(old), self.assertWarns(DeprecationWarning):
                self.assertIs(getattr(track_tags, old), new)

    def test_unsupported_file_type_raises(self):
        with self.assertRaises(ValueError):
            ID3FileTag("some_file.flac")

    def test_has_changed(self):
        tags = TrackAutotags(temp_mp3(self))
        self.assertFalse(tags.has_changed, "as read")
        tags.set(bpm=128)
        self.assertTrue(tags.has_changed, "set")
        tags.save()
        self.assertFalse(tags.has_changed, "saved")
        tags.delete()
        self.assertTrue(tags.has_changed, "deleted")

    def test_has_changed_from_bytes(self):
        tags = TrackAutotags(TrackAutotags(TEST_MP3)._raw_data or b"")
        self.assertFalse(tags.has_changed, "as given")
        tags.set(bpm=128)
        self.assertTrue(tags.has_changed, "differs from the bytes given")


if __name__ == "__main__":
    unittest.main()
