import unittest
from unittest import mock

from mutagen.id3 import COMM, ID3, TPE1, Encoding

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

    def test_fields_name_the_frames_get_and_set_take(self):
        self.assertEqual(TrackTextFrames(self.path).get(TrackTextFrames.Fields.TITLE), "Frequency Shift", "TIT2")
        texts = {TrackTextFrames.Fields.YEAR: "2020", TrackTextFrames.Fields.GENRE: "Dubstep"}
        frames = TrackTextFrames(self.path)
        for field in TrackTextFrames.Fields:
            with self.subTest(field.name):
                frames.set(field, texts.get(field, "1"))
        frames.save()
        saved = TrackTextFrames(self.path)
        for field in TrackTextFrames.Fields:
            with self.subTest(field.name):
                self.assertEqual(saved.get(field), texts.get(field, "1"))
                self.assertEqual(saved.get(field.value), texts.get(field, "1"), "the same frame as its ID")

    def test_save_skips_writing_when_unchanged(self):
        frames = TrackTextFrames(self.path)
        frames.set("TIT2", "Frequency Shift")
        with mock.patch.object(frames.tagfile, "save") as write:
            frames.save()
            write.assert_not_called()
            frames.save(force=True)
            write.assert_called_once()

    def test_set_raises_for_a_frame_id_that_isnt_a_text_frame_stored_by_its_id(self):
        # COMM and TXXX are text frames stored under a key with their description; TIPL is stored by its ID but holds
        # pairs, not text; APIC, WOAR, and GEOB are neither
        for frame_id in ("XXXX", "TXXX", "TIPL", "APIC", "WOAR", "GEOB"):
            with self.subTest(frame_id), self.assertRaises(ValueError):
                TrackTextFrames(self.path).set(frame_id, "x")

    def test_set_raises_for_a_frame_loading_converts_or_drops(self):
        # loading updates tags to ID3v2.4, which converts or drops these, so what was set would never be read back
        for frame_id in ("TYER", "TDAT", "TIME", "TORY", "TRDA", "TSIZ"):
            with self.subTest(frame_id), self.assertRaisesRegex(ValueError, "loading (converts|drops)"):
                TrackTextFrames(self.path).set(frame_id, "2020")
        with self.assertRaisesRegex(ValueError, "into TDRC; set that instead"):
            TrackTextFrames(self.path).set("TYER", "2020")

    def test_set_raises_for_text_loading_rewrites(self):
        # loading turns numeric genres into names, so the genre would silently change
        for text in ("1", "128", "RX", "(1)Rock"):
            with self.subTest(text), self.assertRaisesRegex(ValueError, "loading reads TCON"):
                TrackTextFrames(self.path).set("TCON", text)
        TrackTextFrames(self.path).set("TCON", "Dubstep")
        TrackTextFrames(self.path).set("TCON", "")  # removes it, so nothing is read back

    def test_set_raises_for_text_the_frame_cant_hold(self):
        frames = TrackTextFrames(self.path)
        with self.assertRaises(ValueError):
            frames.set("TDRC", "not a date")
        self.assertFalse(frames.has_changed, "nothing set")
        frames.set("TDRC", "2020-05-01")
        frames.save()
        self.assertEqual(TrackTextFrames(self.path).get("TDRC"), "2020-05-01")

    def test_set_replaces_every_value_of_a_multi_valued_frame(self):
        tags = ID3(self.path)
        tags.add(TPE1(encoding=Encoding.UTF8, text=["A", "B"]))
        tags.save(self.path)

        frames = TrackTextFrames(self.path)
        self.assertEqual(frames.get("TPE1"), "A", "the first value")
        frames.set("TPE1", "A")
        self.assertTrue(frames.has_changed, "B would go")
        frames.save()
        self.assertEqual(ID3(self.path)["TPE1"].text, ["A"])

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
        # as Serato does when a field is cleared, rather than keeping it empty
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

    def test_set_comm_writes_the_frames_serato_does(self):
        # Serato writes a Latin-1 comment to both of these, each Latin-1
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "A Comment")
        self.assertEqual(frames.get("COMM"), "A Comment", "unsaved value read back")
        frames.save()
        self.assertEqual(
            self.comments(),
            {
                "COMM::eng": (Encoding.LATIN1, ["A Comment"]),
                "COMM:ID3v1 Comment:eng": (Encoding.LATIN1, ["A Comment"]),
            },
        )
        self.assertEqual(TrackTextFrames(self.path).get("COMM"), "A Comment")

    def test_set_comm_beyond_latin1_is_utf16_without_the_id3v1_copy(self):
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "A Comment")
        frames.save()
        frames.set("COMM", "TEST ★")
        frames.save()
        # all of it, unlike Serato, which cuts it off by sizing the frame for UTF-16 by its character count
        self.assertEqual(self.comments(), {"COMM::eng": (Encoding.UTF16, ["TEST ★"])}, "ID3v1 copy removed")

    def test_set_comm_empty_removes_both_frames(self):
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "A Comment")
        frames.save()
        frames.set("COMM", "")
        self.assertTrue(frames.has_changed)
        frames.save()
        self.assertEqual(self.comments(), {})
        self.assertIsNone(TrackTextFrames(self.path).get("COMM"))

    def test_set_comm_has_changed(self):
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "")
        self.assertFalse(frames.has_changed, "no comment to remove")
        frames.set("COMM", "A Comment")
        self.assertTrue(frames.has_changed)
        frames.save()
        frames.set("COMM", "A Comment")
        self.assertFalse(frames.has_changed, "set to what the file has")

    def add_comments(self, *frames: tuple[str, str, str]):
        """Adds COMM frames to the file, each (description, language, text)."""
        tags = ID3(self.path)
        for desc, lang, text in frames:
            tags.add(COMM(encoding=Encoding.LATIN1, lang=lang, desc=desc, text=[text]))
        tags.save(self.path)

    def test_get_comm_is_the_first_comment_frame(self):
        # Serato shows the file's first COMM frame, whatever its description or language; mutagen saves the smaller first
        self.add_comments(("", "eng", "A comment longer than the other frame"), ("Songs-DB_Custom1", "eng", "Short"))
        self.assertEqual(TrackTextFrames(self.path).get("COMM"), "Short")

    def test_get_comm_skips_itunes_frames(self):
        self.add_comments(("iTunNORM", "eng", " 00000A2B 00000B1C"))
        self.assertIsNone(TrackTextFrames(self.path).get("COMM"), "iTunes data, not a comment")

    def test_set_comm_removes_every_other_comment_frame_but_itunes(self):
        self.add_comments(
            ("", "\0\0\0", "No language"),
            ("", "deu", "German"),
            ("Songs-DB_Custom1", "eng", "Custom"),
            ("iTunNORM", "eng", " 00000A2B"),
        )
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "A Comment")
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
        self.assertEqual(TrackTextFrames(self.path).get("COMM"), "A Comment", "now first")

    def test_set_comm_has_changed_with_another_comment_frame(self):
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "A Comment")
        frames.save()
        self.add_comments(("Songs-DB_Custom1", "eng", "A Label"))
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "A Comment")
        self.assertTrue(frames.has_changed, "the other frame would be removed")

    def test_set_comm_replaces_every_value_of_the_comment_frame(self):
        tags = ID3(self.path)
        tags.add(COMM(encoding=Encoding.LATIN1, lang="eng", desc="", text=["A Comment", "Another"]))
        tags.save(self.path)
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "A Comment")
        self.assertTrue(frames.has_changed, "the second value would go")
        frames.save()
        self.assertEqual(ID3(self.path)["COMM::eng"].text, ["A Comment"])

    def test_read_and_write_comment_on_open_tags(self):
        tags = ID3(self.path)
        frames = TrackTextFrames(tags)
        self.assertTrue(frames.write_comment("A Comment"))
        self.assertEqual(frames.read_comment(), "A Comment", "in memory, before saving")
        self.assertFalse(frames.write_comment("A Comment"), "already set")
        self.assertIsNone(TrackTextFrames(self.path).get("COMM"), "not written until saved")
        tags.save(self.path)
        self.assertEqual(TrackTextFrames(ID3(self.path)).read_comment(), "A Comment")

        tags = ID3(self.path)
        TrackTextFrames(tags).write_comment("")
        tags.save(self.path)
        self.assertEqual(self.comments(), {}, "both frames removed")

    def test_write_comment_replaces_one_set_and_not_yet_saved(self):
        frames = TrackTextFrames(self.path)
        frames.set("COMM", "Set")
        frames.write_comment("Written")
        self.assertEqual(frames.get("COMM"), "Written")
        self.assertFalse(frames.has_changed, "nothing left for save() to write")
        frames.tagfile.save()
        self.assertEqual(TrackTextFrames(self.path).get("COMM"), "Written")


if __name__ == "__main__":
    unittest.main()
