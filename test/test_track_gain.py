import unittest

from serato_tools.track_gain import TrackGain

from test.helpers.track_tags import TEST_MP3, temp_mp3


class TestCase(unittest.TestCase):
    def test_read(self):
        tags = TrackGain(TEST_MP3)
        self.assertEqual(tags.gain, 0.0, "gain read from RVA2:SeratoGain frame")
        self.assertEqual(tags.peak, 0.0, "peak read from RVA2:SeratoGain frame")

    def test_set_waits_for_save(self):
        path = temp_mp3(self)
        tags = TrackGain(path)
        tags.set(gain=-3.5)
        self.assertEqual(TrackGain(path).gain, 0.0, "not written until saved")
        tags.save()

        saved = TrackGain(path)
        self.assertAlmostEqual(saved.gain or 0.0, -3.5, places=2, msg="written on save")
        self.assertEqual(saved.peak, 0.0, "unset peak keeps its previous value")

        saved.set_and_save(gain=-1.5)
        self.assertAlmostEqual(TrackGain(path).gain or 0.0, -1.5, places=2, msg="set_and_save writes at once")

    def test_delete(self):
        path = temp_mp3(self)
        tags = TrackGain(path)
        self.assertTrue(tags.delete(), "returns that it had the frame")
        tags.save()

        saved = TrackGain(path)
        self.assertIsNone(saved.gain, "no frame reads as no gain")
        self.assertIsNone(saved.peak, "no frame reads as no peak")
        with self.assertRaises(ValueError, msg="needs both values to create the frame"):
            saved.set_and_save(gain=-3.5)

    def test_has_changed(self):
        tags = TrackGain(TEST_MP3)
        self.assertFalse(tags.has_changed, "as read")
        tags.set(gain=-3.5)
        self.assertTrue(tags.has_changed, "set")
        tags.set(gain=0.0)
        self.assertFalse(tags.has_changed, "set back")
        tags.delete()
        self.assertTrue(tags.has_changed, "deleted")


if __name__ == "__main__":
    unittest.main()
