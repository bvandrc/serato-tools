import unittest
from unittest import mock

from serato_tools.track_text_frames import TrackTextFrames

from test.helpers import temp_mp3


class TestCase(unittest.TestCase):
    def setUp(self):
        self.path = temp_mp3(self)

    def test_get(self):
        frames = TrackTextFrames(self.path)
        self.assertEqual(frames.get("TIT2"), "Frequency Shift")
        self.assertEqual(frames.get("TDRC"), "2019", "a timestamp frame read as text")
        self.assertIsNone(frames.get("TPE4"), "no such frame")

    def test_set_writes_on_save(self):
        frames = TrackTextFrames(self.path)
        frames.set("TIT2", "New Title")
        frames.set("TPE4", "A Remixer")
        self.assertEqual(frames.get("TIT2"), "New Title", "unsaved value read back")
        self.assertEqual(TrackTextFrames(self.path).get("TIT2"), "Frequency Shift", "not written until saved")

        frames.save()
        saved = TrackTextFrames(self.path)
        self.assertEqual(saved.get("TIT2"), "New Title")
        self.assertEqual(saved.get("TPE4"), "A Remixer", "missing frame added")

    def test_save_skips_writing_when_unchanged(self):
        frames = TrackTextFrames(self.path)
        frames.set("TIT2", "Frequency Shift")
        with mock.patch.object(frames.tagfile, "save") as write:
            frames.save()
            write.assert_not_called()
            frames.save(force=True)
            write.assert_called_once()

    def test_set_unknown_frame_raises(self):
        with self.assertRaises(ValueError):
            TrackTextFrames(self.path).set("XXXX", "x")

    def test_has_changed(self):
        frames = TrackTextFrames(self.path)
        self.assertFalse(frames.has_changed, "as read")
        frames.set("TIT2", "Frequency Shift")
        self.assertFalse(frames.has_changed, "set to what the file has")
        frames.set("TIT2", "New Title")
        self.assertTrue(frames.has_changed, "set")
        frames.save()
        self.assertFalse(frames.has_changed, "saved")


if __name__ == "__main__":
    unittest.main()
