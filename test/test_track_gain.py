# pylint: disable=protected-access
import unittest
import os
import shutil
import tempfile

from src.serato_tools.track_gain import TrackGain


class TestCase(unittest.TestCase):
    def test_read(self):
        tags = TrackGain(os.path.abspath("test/data/test_mp3.mp3"))
        self.assertEqual(tags.gain, 0.0, "gain read from RVA2:SeratoGain frame")
        self.assertEqual(tags.peak, 0.0, "peak read from RVA2:SeratoGain frame")

    def test_set_and_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_file = os.path.join(tmp_dir, "test.mp3")
            shutil.copy(os.path.abspath("test/data/test_mp3.mp3"), tmp_file)

            tags = TrackGain(tmp_file)
            tags.set_and_save(gain=-3.5)

            tags_readback = TrackGain(tmp_file)
            self.assertAlmostEqual(tags_readback.gain or 0.0, -3.5, places=2, msg="gain saved and read back")
            self.assertEqual(tags_readback.peak, 0.0, "unset peak keeps its previous value")

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_file = os.path.join(tmp_dir, "test.mp3")
            shutil.copy(os.path.abspath("test/data/test_mp3.mp3"), tmp_file)

            tags = TrackGain(tmp_file)
            self.assertTrue(tags.delete())
            tags.save()

            tags_readback = TrackGain(tmp_file)
            self.assertIsNone(tags_readback.gain)
            self.assertIsNone(tags_readback.peak)
