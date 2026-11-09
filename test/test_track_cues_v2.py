# pylint: disable=protected-access
import base64
import dataclasses
import struct
import unittest
import os
import tempfile
import shutil
import io
from contextlib import redirect_stdout

from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v2 import TrackCuesV2


class TestCase(unittest.TestCase):
    def test_parse_and_serialize(self):
        with open(os.path.abspath("test/data/track_cues_v2.bin"), mode="rb") as fp:
            file_data = fp.read()
        tags = TrackCuesV2(file_data)
        self.assertEqual(
            [str(e) for e in tags.entries],
            [
                "TrackCuesV2.ColorEntry(field1=b'\\x00', color=b'\\x99\\xff\\x99')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=0, position=29, field4=b'\\x00', color=b'\\x88\\x00\\xcc', field6=b'\\x00\\x00', name='')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=1, position=12829, field4=b'\\x00', color=b'\\x00\\xcc\\x00', field6=b'\\x00\\x00', name='LYRICS')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=2, position=51229, field4=b'\\x00', color=b'\\xcc\\xcc\\x00', field6=b'\\x00\\x00', name='')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=3, position=64029, field4=b'\\x00', color=b'\\xcc\\x88\\x00', field6=b'\\x00\\x00', name='')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=4, position=89629, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=5, position=102429, field4=b'\\x00', color=b'\\xcc\\xcc\\x00', field6=b'\\x00\\x00', name='LYRICS')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=6, position=153629, field4=b'\\x00', color=b'\\xcc\\x88\\x00', field6=b'\\x00\\x00', name='')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=7, position=204829, field4=b'\\x00', color=b'\\x88\\x00\\xcc', field6=b'\\x00\\x00', name='')",
                "TrackCuesV2.BpmLockEntry(enabled=False)",
            ],
            "parsed entries",
        )
        tags._serialize()
        self.assertEqual(tags._raw_data, file_data, "serialize")  # pylint: disable=protected-access

        def rule(track: "TrackCuesV2.TrackCuesInfo") -> "TrackCuesV2.TrackCuesInfo | None":
            new_color = None
            if track.color is not None:
                new_color = dataclasses.replace(track.color, color=TrackCuesV2.TrackColors.ORANGE.value)
            new_cues = [
                dataclasses.replace(
                    c,
                    color=TrackCuesV2.CueColors.RED.value,
                    name="NEW" if c.name == "" else c.name,
                )
                for c in track.cues
            ]
            return dataclasses.replace(track, color=new_color, cues=new_cues)

        tags.modify_entries(rule)

        self.assertEqual(
            [str(e) for e in tags.entries],
            [
                "TrackCuesV2.ColorEntry(field1=b'\\x00', color=b'\\xff\\xbb\\x99')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=0, position=29, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='NEW')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=1, position=12829, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='LYRICS')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=2, position=51229, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='NEW')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=3, position=64029, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='NEW')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=4, position=89629, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='NEW')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=5, position=102429, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='LYRICS')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=6, position=153629, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='NEW')",
                "TrackCuesV2.CueEntry(field1=b'\\x00', index=7, position=204829, field4=b'\\x00', color=b'\\xcc\\x00\\x00', field6=b'\\x00\\x00', name='NEW')",
                "TrackCuesV2.BpmLockEntry(enabled=False)",
            ],
            "modified entries",
        )
        tags._serialize()

        with open(os.path.abspath("test/data/track_cues_v2_modified.bin"), mode="rb") as fp:
            expected_modified_data = fp.read()
        self.assertEqual(
            tags._raw_data, expected_modified_data, "modified data serialize"
        )  # pylint: disable=protected-access

    def test_changing_deletes_tags_v1_unless_told_not_to(self):
        for delete_tags_v1 in (True, False):
            with self.subTest(delete_tags_v1=delete_tags_v1):
                tags = TrackCuesV2("test/data/test_mp3.mp3")
                assert tags.tagfile is not None
                self.assertIn("GEOB:Serato Markers_", tags.tagfile, "fixture has the v1 tag")
                tags.set_track_color(TrackCuesV2.TrackColors.RED, delete_tags_v1=delete_tags_v1)
                self.assertEqual("GEOB:Serato Markers_" in tags.tagfile, not delete_tags_v1)

    def test_has_changed(self):
        tags = TrackCuesV2("test/data/test_mp3.mp3")
        original_color = TrackCuesV2.TrackColors(tags.get_track_color())
        self.assertFalse(tags.has_changed, "as read")
        tags.set_track_color(TrackCuesV2.TrackColors.RED)
        self.assertTrue(tags.has_changed, "color changed")
        tags.set_track_color(original_color)
        self.assertFalse(tags.has_changed, "color changed back")

    def test_set_beatgrid_locked(self):
        tags = TrackCuesV2("test/data/test_mp3.mp3")
        self.assertFalse(tags.is_beatgrid_locked())
        tags.set_beatgrid_locked(False)
        self.assertFalse(tags.modified, "already unlocked, so no change")
        assert tags.tagfile is not None
        self.assertIn("GEOB:Serato Markers_", tags.tagfile, "v1 tag kept, since nothing changed")
        tags.set_beatgrid_locked(True)
        self.assertTrue(tags.modified)
        data = tags._raw_data  # pylint: disable=protected-access
        assert data is not None
        self.assertTrue(TrackCuesV2(data).is_beatgrid_locked(), "serialized")

    def untagged_mp3(self) -> str:
        """A copy of the test mp3 with no Serato Markers2 tag, as for a track Serato hasn't analyzed."""
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)
        path = os.path.join(tmp_dir.name, "untagged.mp3")
        shutil.copy("test/data/test_mp3.mp3", path)
        tags = TrackCuesV2(path)
        tags.delete()
        tags.save()
        return path

    def test_setting_a_missing_color_or_lock_adds_it(self):
        tags = TrackCuesV2(self.untagged_mp3())
        tags.set_track_color(TrackCuesV2.TrackColors.RED)
        self.assertEqual(tags.get_track_color(), TrackCuesV2.TrackColors.RED.value)

        tags = TrackCuesV2(self.untagged_mp3())
        tags.set_beatgrid_locked(True)
        self.assertTrue(tags.is_beatgrid_locked())

    def test_a_tag_added_from_scratch_matches_what_serato_writes(self):
        # track_cues_v2_analyzed.bin is the tag Serato wrote for a newly analyzed track: white, unlocked
        tags = TrackCuesV2(self.untagged_mp3())
        tags.set_track_color(TrackCuesV2.TrackColors.WHITE)
        tags.set_beatgrid_locked(False)
        with open("test/data/track_cues_v2_analyzed.bin", "rb") as f:
            self.assertEqual(tags._raw_data, f.read())

    def test_rewriting_keeps_seratos_bytes(self):
        # tags Serato wrote: saved_loops's base64 ends in a character Serato drops, 514_bytes is longer than 470 bytes,
        # flips has cues, a BPM lock, and then flips, in that order, full_last_line's base64 ends in a full line, and
        # 982_bytes and 1494_bytes are 512-byte steps past 470
        for name in (
            "track_cues_v2_saved_loops.bin",
            "track_cues_v2_514_bytes.bin",
            "track_cues_v2_flips.bin",
            "track_cues_v2_full_last_line.bin",
            "track_cues_v2_982_bytes.bin",
            "track_cues_v2_1494_bytes.bin",
        ):
            with self.subTest(name), open(f"test/data/{name}", "rb") as f:
                data = f.read()
                tags = TrackCuesV2(data)
                tags.modify_entries(dataclasses.replace)
                self.assertEqual(tags._raw_data, data)

    def test_shrinking_keeps_the_tags_size(self):
        with open("test/data/track_cues_v2_514_bytes.bin", "rb") as f:
            tags = TrackCuesV2(f.read())
        # track_cues_v2_514_bytes.bin has cues and loops: without them, it needs well under 470 bytes
        tags.modify_entries(lambda info: dataclasses.replace(info, cues=[], loops=[]))
        rewritten = tags._raw_data
        assert rewritten is not None
        self.assertEqual(len(rewritten), 514)
        self.assertEqual(TrackCuesV2(rewritten).entries, tags.entries)

    def test_outgrowing_the_tags_size_grows_it_as_serato_does(self):
        # Serato grew a 470-byte tag to track_cues_v2_982_bytes.bin, one 512-byte step. 1494_bytes is two steps, and
        # its entries need both. Giving a 470-byte tag either's entries should give the same bytes
        for name in ("track_cues_v2_982_bytes.bin", "track_cues_v2_1494_bytes.bin"):
            with self.subTest(name), open(f"test/data/{name}", "rb") as f:
                grown = f.read()
                with open("test/data/track_cues_v2_analyzed.bin", "rb") as f470:
                    tags = TrackCuesV2(f470.read())
                tags.modify_entries(lambda _, g=grown: TrackCuesV2.TrackCuesInfo.from_entries(TrackCuesV2(g).entries))
                self.assertEqual(tags._raw_data, grown)

    def test_a_cue_past_8_raises(self):
        # cue 11 as found in a real tag, which Serato ignored: field4 cc and color cccccc
        cue_11 = bytes.fromhex("00 0a 00 02 14 98 cc cc cc cc 00 00 00")
        payload = b"\x01\x01" + b"CUE\x00" + struct.pack(">I", len(cue_11)) + cue_11 + b"\x00"
        with self.assertRaisesRegex(ValueError, "cue 11 is past Serato's 8 cue pads"):
            TrackCuesV2(b"\x01\x01" + base64.b64encode(payload))

        with open("test/data/track_cues_v2_analyzed.bin", "rb") as f:
            tags = TrackCuesV2(f.read())
        cue_9 = TrackCuesV2.CueEntry(b"\x00", 8, 1000, b"\x00", TrackCuesV2.CueColors.RED.value, b"\x00\x00", "")
        with self.assertRaisesRegex(ValueError, "cue 9 is past Serato's 8 cue pads"):
            tags.modify_entries(lambda info: dataclasses.replace(info, cues=[cue_9]))

    def test_snap_position_to_beat(self):
        tags = TrackCuesV2("test/data/test_mp3.mp3")
        buf = io.StringIO()
        with redirect_stdout(buf):
            tags.snap_positions_to_beat(1 / 16, 2)
        output = buf.getvalue()
        self.assertIn("Snapped by 42 ms", output)

    def test_snap_ignores_1ms_by_default(self):
        tags = TrackCuesV2("test/data/test_mp3.mp3")
        beat = TrackBeatgrid("test/data/test_mp3.mp3").find_nearest_beat(tags._from_entries().cues[0].position, 1)
        assert beat is not None
        beat_ms = round(beat)
        self.assertIsNone(tags.get_snapped_beat_ms(beat_ms + 1, 1 / 8))
        self.assertIsNone(tags.get_snapped_beat_ms(beat_ms - 1, 1 / 8))
        self.assertEqual(tags.get_snapped_beat_ms(beat_ms + 2, 1 / 8), beat_ms)

    def test_snap_positions_to_beat_no_entries_raises(self):
        tags = TrackCuesV2("test/data/test_mp3.mp3")
        tags.entries = []
        with self.assertRaises(ValueError):
            tags.snap_positions_to_beat(1 / 8)

    def test_loop_fields(self):
        # track_cues_v2_saved_loops.bin is a tag Serato wrote with 4 loops, the second one locked
        with open("test/data/track_cues_v2_saved_loops.bin", "rb") as f:
            tags = TrackCuesV2(f.read())
        loops = tags._from_entries().loops
        self.assertEqual([loop.color for loop in loops], [b"\x27\xaa\xe1"] * 4)
        self.assertEqual([loop.locked for loop in loops], [False, True, False, False])

        # a loop's color is bytes 15-17, after 4 bytes of ff and one 00
        serialized = dataclasses.replace(loops[0], color=b"\xcc\x00\x00")._serialize()
        self.assertEqual(serialized[10:20], b"\xff\xff\xff\xff\x00\xcc\x00\x00\x00\x00")

    def test_cue_colors_are_seratos_18(self):
        # Serato DJ Intro's palette, which it displays as stored (docs/colors.md)
        palette = (
            "CC0000 CC4400 CC8800 CCCC00 88CC00 44CC00 00CC00 00CC44 00CC88 "
            "00CCCC 0088CC 0044CC 0000CC 4400CC 8800CC CC00CC CC0088 CC0044"
        )
        self.assertEqual([color.value.hex().upper() for color in TrackCuesV2.CueColors], palette.split())

    def test_an_entry_unlike_seratos_raises(self):
        with open("test/data/track_cues_v2_saved_loops.bin", "rb") as f:
            loop = TrackCuesV2(f.read())._from_entries().loops[0]._serialize()
        with open("test/data/track_cues_v2.bin", "rb") as f:
            info = TrackCuesV2(f.read())._from_entries()
        assert info.color is not None and info.bpm_lock is not None
        color, cue, bpm_lock = info.color._serialize(), info.cues[0]._serialize(), info.bpm_lock._serialize()

        def changed(data: bytes, index: int, value: bytes) -> bytes:
            return data[:index] + value + data[index + len(value) :]

        cases = {
            "COLOR field1": (TrackCuesV2.ColorEntry, changed(color, 0, b"\x01")),
            "COLOR length": (TrackCuesV2.ColorEntry, color + b"\x00"),
            "BPMLOCK length": (TrackCuesV2.BpmLockEntry, bpm_lock + b"\x00"),
            "CUE field1": (TrackCuesV2.CueEntry, changed(cue, 0, b"\x01")),
            "CUE field4": (TrackCuesV2.CueEntry, changed(cue, 6, b"\x01")),
            "CUE field6": (TrackCuesV2.CueEntry, changed(cue, 10, b"\x01")),
            "CUE name without a null byte": (TrackCuesV2.CueEntry, cue[:-1]),
            "CUE bytes after the name": (TrackCuesV2.CueEntry, cue + b"\x00"),
            "LOOP field1": (TrackCuesV2.LoopEntry, changed(loop, 0, b"\x01")),
            "LOOP field5": (TrackCuesV2.LoopEntry, changed(loop, 10, b"\x00")),
            "LOOP field6": (TrackCuesV2.LoopEntry, changed(loop, 14, b"\x01")),
            "LOOP byte 18": (TrackCuesV2.LoopEntry, changed(loop, 18, b"\x01")),
            "LOOP bytes after the name": (TrackCuesV2.LoopEntry, loop + b"\x00"),
        }
        for name, (entry_class, data) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                entry_class._parse(data)

    def test_untested_version_raises_at_construction(self):
        with self.assertRaises(ValueError):
            TrackCuesV2(bytes([0x99, 0x99]))
