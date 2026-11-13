# pylint: disable=protected-access
import os
import shutil
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
from serato_tools.utils.track_tags import ID3FileTag, get_geob, open_tag_or_dump, save_tag_or_dump

from test.helpers import TEST_MP3, read_bytes, temp_dir, temp_mp3


class TestCase(unittest.TestCase):
    def test_delete_then_save_persists_deletion(self):
        for tag_class in (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags, TrackWaveform):
            with self.subTest(tag_class.__name__):
                path = temp_mp3(self)
                self.assertIsNotNone(get_geob(MP3(path), tag_class.GEOB_KEY), "fixture has the tag")
                tags = tag_class(path)
                tags.delete()
                self.assertTrue(tags.save(), "returns that it wrote")
                self.assertIsNone(get_geob(MP3(path), tag_class.GEOB_KEY), "deletion saved")

    def test_save_writes_only_a_changed_tag_unless_forced(self):
        for tag_class in (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags, TrackWaveform):
            with self.subTest(tag_class.__name__):
                tags = tag_class(temp_mp3(self))
                assert tags.tagfile is not None
                with mock.patch.object(tags.tagfile, "save") as save:
                    tags.save()
                    save.assert_not_called()
                    tags.save(force=True)
                    save.assert_called_once()

    def test_save_returns_whether_it_wrote(self):
        for tag_class in (
            TrackCuesV2,
            TrackCuesV1,
            TrackBeatgrid,
            TrackAutotags,
            TrackWaveform,
            TrackGain,
            TrackTextFrames,
        ):
            with self.subTest(tag_class.__name__):
                tags = tag_class(temp_mp3(self))
                assert tags.tagfile is not None
                with mock.patch.object(tags.tagfile, "save"):
                    self.assertIs(tags.save(), False, "unchanged")
                    self.assertIs(tags.save(force=True), True, "forced")

    def test_untested_version_raises_at_construction(self):
        for tag_class in (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags, TrackWaveform):
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

    def test_has_changed_from_bytes(self):
        tags = TrackAutotags(TrackAutotags(TEST_MP3)._raw_data or b"")
        self.assertFalse(tags.has_changed, "as given")
        tags.set(bpm=128)
        self.assertTrue(tags.has_changed, "differs from the bytes given")

    def test_saving_a_change_to_a_tag_read_from_bytes_raises(self):
        for tag_class in (TrackCuesV2, TrackAutotags):  # TrackCuesV2 has its own save()
            with self.subTest(tag_class.__name__):
                tags = tag_class(tag_class(TEST_MP3)._raw_data or b"")
                tags.delete()
                with self.assertRaisesRegex(ValueError, "read from bytes"):
                    tags.save()

    def test_open_tag_or_dump_reads_an_audio_file_or_the_tags_own_bytes(self):
        fixtures = {
            TrackCuesV2: "track_cues_v2",
            TrackCuesV1: "track_cues_v1",
            TrackBeatgrid: "track_beatgrid",
            TrackAutotags: "track_autotags",
            TrackWaveform: "track_waveform",
        }
        for tag_class, name in fixtures.items():
            with self.subTest(tag_class.__name__):
                dump = f"test/data/{name}.bin"
                tags = open_tag_or_dump(tag_class, dump)
                self.assertIsNone(tags.tagfile, "read as bytes")
                self.assertEqual(tags._raw_data, read_bytes(dump))
                self.assertIsNotNone(open_tag_or_dump(tag_class, TEST_MP3).tagfile, "read as audio")

    def test_save_tag_or_dump_writes_a_changed_dump_back(self):
        dump = os.path.join(temp_dir(self), "Serato Autotags.octet-stream")
        shutil.copy("test/data/track_autotags.bin", dump)
        tags = open_tag_or_dump(TrackAutotags, dump)
        self.assertFalse(save_tag_or_dump(tags, dump), "unchanged")
        tags.set(bpm=128)
        self.assertTrue(save_tag_or_dump(tags, dump))
        self.assertEqual(TrackAutotags(read_bytes(dump)).bpm, 128)

    def test_save_tag_or_dump_saves_an_audio_file(self):
        path = temp_mp3(self)
        tags = open_tag_or_dump(TrackAutotags, path)
        tags.set(bpm=128)
        self.assertTrue(save_tag_or_dump(tags, path))
        self.assertEqual(TrackAutotags(path).bpm, 128)


if __name__ == "__main__":
    unittest.main()
