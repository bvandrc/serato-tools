# pylint: disable=protected-access
import unittest
import os
import shutil
import tempfile

from mutagen.mp3 import MP3


from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_waveform import TrackWaveform
from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_tagdump import get_serato_tagdata
from serato_tools.utils import track_tags
from serato_tools.utils.track_tags import ID3FileTag, SeratoGeobTag, get_geob


class TestCase(unittest.TestCase):
    def test_file_parse(self):
        tagfile = MP3(os.path.abspath("test/data/test_mp3.mp3"))
        TrackCuesV2(tagfile).delete()
        TrackCuesV1(tagfile).delete()
        TrackWaveform(tagfile).delete()
        TrackAutotags(tagfile).delete()

        self.assertIsNone(TrackCuesV2(tagfile)._get_geob())
        self.assertIsNone(TrackCuesV1(tagfile)._get_geob())
        self.assertIsNone(get_geob(tagfile, TrackWaveform.GEOB_KEY))
        self.assertIsNone(TrackAutotags(tagfile)._get_geob())

    def test_delete_then_save_persists_deletion(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_file = os.path.join(tmp_dir, "test.mp3")
            shutil.copy(os.path.abspath("test/data/test_mp3.mp3"), tmp_file)

            tags = TrackAutotags(tmp_file)
            self.assertIsNotNone(tags._raw_data, "fixture should have the tag")  # pylint: disable=protected-access
            tags.delete()
            tags.save()

            self.assertNotIn(f"GEOB:{TrackAutotags.GEOB_KEY}", MP3(tmp_file), "deletion should be saved to the file")

    def test_tagdump_reads_each_geob(self):
        path = os.path.abspath("test/data/test_mp3.mp3")
        dumped = dict(get_serato_tagdata(MP3(path)))
        self.assertEqual(dumped["Serato Autotags"], TrackAutotags(path)._raw_data)
        self.assertEqual(dumped["Serato Markers2"], TrackCuesV2(path)._raw_data)

    def test_old_class_names_still_work_but_warn(self):
        for old, new in (("SeratoTrack", ID3FileTag), ("SeratoTag", SeratoGeobTag)):
            with self.subTest(old), self.assertWarns(DeprecationWarning):
                self.assertIs(getattr(track_tags, old), new)

    def test_unsupported_file_type_raises(self):
        with self.assertRaises(ValueError):
            ID3FileTag("some_file.flac")
