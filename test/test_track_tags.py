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
from serato_tools.utils.track_tags import ID3FileTag, SeratoGeobTag, get_geob, open_tag_file_or_data

from test.helpers import TEST_MP3, read_bytes, temp_mp3


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
        for tag_class in (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags, TrackWaveform):
            with self.subTest(tag_class.__name__), self.assertRaisesRegex(ValueError, "Untested Serato tag version"):
                tag_class(bytes([0x99, 0x99]))

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

    def test_a_file_whose_id3_tags_have_no_frames_reads_and_saves(self):
        for tag_class in (TrackCuesV2, TrackAutotags):  # TrackCuesV2 has its own save()
            with self.subTest(tag_class.__name__):
                path = temp_mp3(self)
                tagfile = MP3(path)
                assert tagfile.tags is not None
                tagfile.tags.clear()
                tagfile.save()
                tagfile = MP3(path)
                # so a check for the file mustn't test its truth
                self.assertFalse(tagfile, "falsy, as an MP3 with no ID3 frames is")
                tags = tag_class(tagfile)
                self.assertIsNone(tags._raw_data, "no tag yet")
                tags._raw_data = tag_class(TEST_MP3)._raw_data
                tags.save()
                self.assertEqual(get_geob(MP3(path), tag_class.GEOB_KEY), tags._raw_data)

    def test_open_tag_file_or_data_reads_an_audio_file_or_the_tags_own_bytes(self):
        fixtures = {
            TrackCuesV2: "track_cues_v2",
            TrackCuesV1: "track_cues_v1",
            TrackBeatgrid: "track_beatgrid",
            TrackAutotags: "track_autotags",
            TrackWaveform: "track_waveform",
        }
        for tag_class, name in fixtures.items():
            with self.subTest(tag_class.__name__):
                data_file = f"test/data/{name}.bin"
                tags = open_tag_file_or_data(tag_class, data_file)
                self.assertIsNone(tags.tagfile, "read as bytes")
                self.assertEqual(tags._raw_data, read_bytes(data_file))
                self.assertIsNotNone(open_tag_file_or_data(tag_class, TEST_MP3).tagfile, "read as audio")


if __name__ == "__main__":
    unittest.main()
