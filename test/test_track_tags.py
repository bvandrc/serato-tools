# pylint: disable=protected-access
import unittest
from unittest import mock

from mutagen.mp3 import MP3

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain
from serato_tools.track_tagdump import get_serato_tagdata
from serato_tools.track_text_frames import TrackTextFrames
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import ID3FileTag, get_geob, open_tag_file_or_data

from test.helpers import TEST_MP3, read_bytes, temp_mp3

# each GEOB tag class, with a fixture of its tag's bytes
GEOB_FIXTURES = {
    TrackCuesV2: "test/data/track_cues_v2.bin",
    TrackCuesV1: "test/data/track_cues_v1.bin",
    TrackBeatgrid: "test/data/track_beatgrid.bin",
    TrackAutotags: "test/data/track_autotags.bin",
    TrackWaveform: "test/data/track_waveform.bin",
}
GEOB_TAG_CLASSES = tuple(GEOB_FIXTURES)
TAG_CLASSES = (*GEOB_TAG_CLASSES, TrackGain, TrackTextFrames)


class TestCase(unittest.TestCase):
    def test_delete_then_save_persists_deletion(self):
        for tag_class in GEOB_TAG_CLASSES:
            with self.subTest(tag_class.__name__):
                path = temp_mp3(self)
                self.assertIsNotNone(get_geob(MP3(path), tag_class.GEOB_KEY), "fixture has the tag")
                tags = tag_class(path)
                tags.delete()
                self.assertTrue(tags.save(), "returns that it wrote")
                self.assertIsNone(get_geob(MP3(path), tag_class.GEOB_KEY), "deletion saved")

    def test_save_writes_only_a_changed_tag_unless_forced(self):
        for tag_class in TAG_CLASSES:
            with self.subTest(tag_class.__name__):
                tags = tag_class(temp_mp3(self))
                assert tags.tagfile is not None
                with mock.patch.object(tags.tagfile, "save") as save:
                    self.assertIs(tags.save(), False, "unchanged")
                    save.assert_not_called()
                    self.assertIs(tags.save(force=True), True, "forced")
                    save.assert_called_once()

    def test_untested_version_raises_at_construction(self):
        for tag_class in GEOB_TAG_CLASSES:
            with self.subTest(tag_class.__name__), self.assertRaisesRegex(ValueError, "Untested Serato tag version"):
                tag_class(bytes([0x99, 0x99]))

    def test_tagdump_reads_each_geob(self):
        dumped = dict(get_serato_tagdata(MP3(TEST_MP3)))
        self.assertEqual(dumped["Serato Autotags"], TrackAutotags(TEST_MP3)._raw_data)
        self.assertEqual(dumped["Serato Markers2"], TrackCuesV2(TEST_MP3)._raw_data)

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

        tags = TrackAutotags(read_bytes(GEOB_FIXTURES[TrackAutotags]))
        self.assertFalse(tags.has_changed, "as given in bytes")
        tags.set(bpm=128)
        self.assertTrue(tags.has_changed, "differs from the bytes given")

    def test_saving_a_change_to_a_tag_read_from_bytes_raises(self):
        for tag_class in (TrackCuesV2, TrackAutotags):  # TrackCuesV2 has its own save()
            with self.subTest(tag_class.__name__):
                tags = tag_class(read_bytes(GEOB_FIXTURES[tag_class]))
                tags.delete()
                with self.assertRaisesRegex(ValueError, "read from bytes"):
                    tags.save()

    def test_serialize_reproduces_the_bytes_parsed(self):
        for tag_class in (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags):  # TrackWaveform is read-only
            with self.subTest(tag_class.__name__):
                data = read_bytes(GEOB_FIXTURES[tag_class])
                tags = tag_class(data)
                tags._serialize()
                self.assertEqual(tags._raw_data, data)

    def test_open_tag_file_or_data_reads_an_audio_file_or_the_tags_own_bytes(self):
        for tag_class, data_file in GEOB_FIXTURES.items():
            with self.subTest(tag_class.__name__):
                tags = open_tag_file_or_data(tag_class, data_file)
                self.assertIsNone(tags.tagfile, "read as bytes")
                self.assertEqual(tags._raw_data, read_bytes(data_file))
                self.assertIsNotNone(open_tag_file_or_data(tag_class, TEST_MP3).tagfile, "read as audio")


if __name__ == "__main__":
    unittest.main()
