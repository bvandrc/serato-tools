import unittest
from unittest import mock

from mutagen.id3 import COMM, ID3, Encoding

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

    def test_set_empty_removes_the_frame(self):
        # as Serato does when a tag is cleared, rather than keeping it empty
        frames = TrackTextFrames(self.path)
        frames.set("TIT2", "")
        self.assertIsNone(frames.get("TIT2"), "unsaved")
        self.assertTrue(frames.has_changed)
        frames.save()
        self.assertNotIn("TIT2", ID3(self.path))

        frames = TrackTextFrames(self.path)
        frames.set("TIT2", "")
        self.assertFalse(frames.has_changed, "already removed")

    def comments(self) -> dict[str, tuple[int, list[str]]]:
        """The file's COMM frames, by key, with their encoding and text."""
        tags = ID3(self.path)
        return {key: (tags[key].encoding, list(tags[key].text)) for key in tags.keys() if key.startswith("COMM")}

    def test_set_comment_writes_the_frames_serato_does(self):
        # Serato writes a Latin-1 comment to both of these, each Latin-1
        frames = TrackTextFrames(self.path)
        frames.set_comment("A Comment")
        self.assertEqual(frames.get_comment(), "A Comment", "unsaved value read back")
        frames.save()
        self.assertEqual(
            self.comments(),
            {
                "COMM::eng": (Encoding.LATIN1, ["A Comment"]),
                "COMM:ID3v1 Comment:eng": (Encoding.LATIN1, ["A Comment"]),
            },
        )
        self.assertEqual(TrackTextFrames(self.path).get_comment(), "A Comment")

    def test_set_comment_beyond_latin1_is_utf16_without_the_id3v1_copy(self):
        frames = TrackTextFrames(self.path)
        frames.set_comment("A Comment")
        frames.save()
        frames.set_comment("TEST ★")
        frames.save()
        # all of it, unlike Serato, which cuts it off by sizing the frame for UTF-16 by its character count
        self.assertEqual(self.comments(), {"COMM::eng": (Encoding.UTF16, ["TEST ★"])}, "ID3v1 copy removed")

    def test_set_comment_empty_removes_both_frames(self):
        frames = TrackTextFrames(self.path)
        frames.set_comment("A Comment")
        frames.save()
        frames.set_comment("")
        self.assertTrue(frames.has_changed)
        frames.save()
        self.assertEqual(self.comments(), {})
        self.assertIsNone(TrackTextFrames(self.path).get_comment())

    def test_set_comment_has_changed(self):
        frames = TrackTextFrames(self.path)
        frames.set_comment("")
        self.assertFalse(frames.has_changed, "no comment to remove")
        frames.set_comment("A Comment")
        self.assertTrue(frames.has_changed)
        frames.save()
        frames.set_comment("A Comment")
        self.assertFalse(frames.has_changed, "set to what the file has")

    def add_comments(self, *frames: tuple[str, str, str]):
        """Adds COMM frames to the file, each (description, language, text)."""
        tags = ID3(self.path)
        for desc, lang, text in frames:
            tags.add(COMM(encoding=Encoding.LATIN1, lang=lang, desc=desc, text=[text]))
        tags.save(self.path)

    def test_get_comment_is_the_first_comment_frame(self):
        # Serato shows the file's first COMM frame, whatever its description or language; mutagen saves the smaller first
        self.add_comments(("", "eng", "A comment longer than the other frame"), ("Songs-DB_Custom1", "eng", "Short"))
        self.assertEqual(TrackTextFrames(self.path).get_comment(), "Short")

    def test_get_comment_skips_itunes_frames(self):
        self.add_comments(("iTunNORM", "eng", " 00000A2B 00000B1C"))
        self.assertIsNone(TrackTextFrames(self.path).get_comment(), "iTunes data, not a comment")

    def test_set_comment_removes_every_other_comment_frame_but_itunes(self):
        self.add_comments(
            ("", "\0\0\0", "No language"),
            ("", "deu", "German"),
            ("Songs-DB_Custom1", "eng", "Custom"),
            ("iTunNORM", "eng", " 00000A2B"),
        )
        frames = TrackTextFrames(self.path)
        frames.set_comment("A Comment")
        frames.save()
        self.assertEqual(
            {key: text for key, (_, text) in self.comments().items()},
            {
                "COMM::eng": ["A Comment"],
                "COMM:ID3v1 Comment:eng": ["A Comment"],
                "COMM:iTunNORM:eng": [" 00000A2B"],
            },
            "iTunes' data kept",
        )
        self.assertEqual(TrackTextFrames(self.path).get_comment(), "A Comment", "now first")

    def test_set_comment_has_changed_with_another_comment_frame(self):
        frames = TrackTextFrames(self.path)
        frames.set_comment("A Comment")
        frames.save()
        self.add_comments(("Songs-DB_Custom1", "eng", "A Label"))
        frames = TrackTextFrames(self.path)
        frames.set_comment("A Comment")
        self.assertTrue(frames.has_changed, "the other frame would be removed")


if __name__ == "__main__":
    unittest.main()
