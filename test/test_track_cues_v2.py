# pylint: disable=protected-access
import base64
import dataclasses
import struct
import unittest
from typing import Callable

from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v2 import TrackCuesV2, main
from serato_tools.utils.track_tags import NoBeatgridError, NoCuesError

from test.helpers import (
    SNAPPED_CUE_POSITIONS,
    TEST_MP3,
    cli_args,
    cue_positions,
    has_tags_v1,
    mp3_without,
    read_bytes,
    temp_mp3,
    untagged_mp3,
)


def fixture(name: str = "") -> bytes:
    """The bytes of the Serato Markers2 tag fixture test/data/track_cues_v2{name}.bin."""
    return read_bytes(f"test/data/track_cues_v2{name}.bin")


def snap_cues_cli(path: str):
    """The command line that snaps `path`'s cues to its beats."""
    return cli_args("serato_snap_cues_v2", path, "--snap_cues", "--snap_tolerance", "1/16")


class TestCase(unittest.TestCase):
    def test_parse_and_modify(self):
        tags = TrackCuesV2(fixture())
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
        self.assertEqual(tags.get_track_color_name(), "LIMEGREEN3", "the 99ff99 color")

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
        self.assertEqual(tags._raw_data, fixture("_modified"), "modified data serialize")

    def has_tags_v1_after(self, edit: Callable[[TrackCuesV2], object]) -> bool:
        """Whether a copy of the test mp3, which has a Serato Markers_ tag, still has it once `edit` has run on it."""
        tmp_file = temp_mp3(self)
        self.assertTrue(has_tags_v1(tmp_file), "fixture has the v1 tag")
        edit(TrackCuesV2(tmp_file))
        return has_tags_v1(tmp_file)

    def test_saving_deletes_tags_v1_unless_told_not_to(self):
        def edit_and_save(tags: TrackCuesV2, **save_kwargs: bool):
            tags.set_track_color(TrackCuesV2.TrackColors.RED)
            tags.save(**save_kwargs)

        self.assertFalse(self.has_tags_v1_after(edit_and_save), "deleted by default")
        self.assertTrue(self.has_tags_v1_after(lambda tags: edit_and_save(tags, delete_tags_v1=False)))
        self.assertFalse(self.has_tags_v1_after(lambda tags: tags.save(force=True)), "by a forced save too")

    def test_delete_tags_v1_on_an_edit_is_deprecated(self):
        def edit(tags: TrackCuesV2):
            with self.assertWarns(DeprecationWarning) as caught:
                tags.set_track_color(TrackCuesV2.TrackColors.RED, delete_tags_v1=False)
            self.assertEqual(caught.filename, __file__, "points at the caller")
            tags.save()

        self.assertTrue(self.has_tags_v1_after(edit), "False still keeps the v1 tag")

    def test_deprecated_delete_tags_v1_false_loses_to_another_edit(self):
        def edit(tags: TrackCuesV2):
            tags.set_beatgrid_locked(True)
            with self.assertWarns(DeprecationWarning):
                tags.set_track_color(TrackCuesV2.TrackColors.RED, delete_tags_v1=False)
            tags.save()

        self.assertFalse(self.has_tags_v1_after(edit), "deleted, as when the earlier edit asked to delete it")

    def test_a_callback_may_edit_in_place(self):
        tags = TrackCuesV2(TEST_MP3)
        position = tags._from_entries().cues[0].position

        def rule(info: TrackCuesV2.TrackCuesInfo) -> TrackCuesV2.TrackCuesInfo:
            info.cues[0].position += 1000
            return info

        tags.modify_entries(rule)
        self.assertTrue(tags.has_changed)
        data = tags._raw_data
        assert data is not None
        self.assertEqual(TrackCuesV2(data)._from_entries().cues[0].position, position + 1000)

    def test_has_changed(self):
        tmp_file = temp_mp3(self)
        tags = TrackCuesV2(tmp_file)
        original_color = TrackCuesV2.TrackColors(tags.get_track_color())
        self.assertFalse(tags.has_changed, "as read")
        tags.set_track_color(TrackCuesV2.TrackColors.RED)
        self.assertTrue(tags.has_changed, "color changed")
        tags.modify_entries(dataclasses.replace)
        self.assertTrue(tags.has_changed, "an edit that changed nothing doesn't reset it")
        tags.set_track_color(original_color)
        self.assertFalse(tags.has_changed, "color changed back")

        tags.set_track_color(TrackCuesV2.TrackColors.RED)
        tags.modify_entries(dataclasses.replace)
        tags.save()
        self.assertFalse(tags.has_changed, "saved")
        self.assertEqual(
            TrackCuesV2(tmp_file).get_track_color(),
            TrackCuesV2.TrackColors.RED.value,
            "a change followed by an edit that changes nothing is written",
        )

    def test_set_beatgrid_locked(self):
        tags = TrackCuesV2(TEST_MP3)
        original_data = tags._raw_data
        self.assertFalse(tags.is_beatgrid_locked())
        tags.set_beatgrid_locked(False)
        data = tags._raw_data
        self.assertEqual(data, original_data, "already unlocked, so no change")
        assert tags.tagfile is not None
        self.assertIn("GEOB:Serato Markers_", tags.tagfile, "v1 tag kept, since nothing changed")
        tags.set_beatgrid_locked(True)
        data = tags._raw_data
        assert data is not None
        self.assertTrue(TrackCuesV2(data).is_beatgrid_locked(), "serialized")

    def test_setting_a_missing_color_or_lock_adds_it(self):
        tags = TrackCuesV2(untagged_mp3(self))
        self.assertIsNone(tags.get_track_color_name(), "no color entry yet")
        tags.set_track_color(TrackCuesV2.TrackColors.WHITE)
        tags.set_beatgrid_locked(False)
        self.assertEqual(tags.get_track_color(), TrackCuesV2.TrackColors.WHITE.value)
        self.assertFalse(tags.is_beatgrid_locked())
        # track_cues_v2_analyzed.bin is the tag Serato wrote for a newly analyzed track: white, unlocked
        self.assertEqual(tags._raw_data, fixture("_analyzed"), "the tag Serato writes")
        tags.set_beatgrid_locked(True)
        self.assertTrue(tags.is_beatgrid_locked())

    def test_rewriting_keeps_seratos_bytes(self):
        # tags Serato wrote: saved_loops's base64 ends in a character Serato drops, 514_bytes is longer than 470 bytes,
        # flips has cues, a BPM lock, and then flips, in that order, full_last_line's base64 ends in a full line, and
        # 982_bytes and 1494_bytes are 512-byte steps past 470
        for name in ("_saved_loops", "_514_bytes", "_flips", "_full_last_line", "_982_bytes", "_1494_bytes"):
            with self.subTest(name):
                data = fixture(name)
                tags = TrackCuesV2(data)
                tags.modify_entries(dataclasses.replace)
                self.assertEqual(tags._raw_data, data)

    def test_shrinking_keeps_the_tags_size(self):
        tags = TrackCuesV2(fixture("_514_bytes"))
        # track_cues_v2_514_bytes.bin has cues and loops: without them, it needs well under 470 bytes
        tags.modify_entries(lambda info: dataclasses.replace(info, cues=[], loops=[]))
        rewritten = tags._raw_data
        assert rewritten is not None
        self.assertEqual(len(rewritten), 514)
        self.assertEqual(TrackCuesV2(rewritten).entries, tags.entries)

    def test_outgrowing_the_tags_size_grows_it_as_serato_does(self):
        # Serato grew a 470-byte tag to track_cues_v2_982_bytes.bin, one 512-byte step. 1494_bytes is two steps, and
        # its entries need both. Giving a 470-byte tag either's entries should give the same bytes
        for name in ("_982_bytes", "_1494_bytes"):
            with self.subTest(name):
                grown = fixture(name)
                tags = TrackCuesV2(fixture("_analyzed"))
                tags.modify_entries(lambda _, g=grown: TrackCuesV2.TrackCuesInfo.from_entries(TrackCuesV2(g).entries))
                self.assertEqual(tags._raw_data, grown)

    def test_a_cue_past_8_raises(self):
        # cue 11 as found in a real tag, which Serato ignored: field4 cc and color cccccc
        cue_11 = bytes.fromhex("00 0a 00 02 14 98 cc cc cc cc 00 00 00")
        payload = b"\x01\x01" + b"CUE\x00" + struct.pack(">I", len(cue_11)) + cue_11 + b"\x00"
        with self.assertRaisesRegex(ValueError, "cue 11 is past Serato's 8 cue pads"):
            TrackCuesV2(b"\x01\x01" + base64.b64encode(payload))

        tags = TrackCuesV2(fixture("_analyzed"))
        cue_9 = TrackCuesV2.CueEntry(b"\x00", 8, 1000, b"\x00", TrackCuesV2.CueColors.RED.value, b"\x00\x00", "")
        with self.assertRaisesRegex(ValueError, "cue 9 is past Serato's 8 cue pads"):
            tags.modify_entries(lambda info: dataclasses.replace(info, cues=[cue_9]))

    def test_snap_cues_to_beats(self):
        tags, beatgrid = TrackCuesV2(TEST_MP3), TrackBeatgrid(TEST_MP3)
        snapped = tags.snap_cues_to_beats(beatgrid, 1 / 16)
        # cues 3, 5, and 6 are 1 ms off their beats, which the default min_ms_change leaves alone
        SnappedCue = TrackCuesV2.SnappedCue
        self.assertEqual(
            snapped, [SnappedCue(0, 45104, 45146), SnappedCue(1, 67474, 67472), SnappedCue(3, 134451, 134449)]
        )
        positions = cue_positions(tags)
        self.assertEqual(positions, SNAPPED_CUE_POSITIONS)
        for position in positions:
            beat_position = beatgrid.get_beat_position(position)
            self.assertAlmostEqual(beat_position, round(beat_position), delta=0.01, msg="on a beat")
        self.assertTrue(tags.has_changed)

    def test_snap_cues_to_beats_doesnt_count_a_cue_already_on_its_beat(self):
        tags, beatgrid = TrackCuesV2(TEST_MP3), TrackBeatgrid(TEST_MP3)
        beat = beatgrid.find_nearest_beat(45104, 1)  # the first cue's beat, 42 ms after it
        assert beat is not None

        def first_cue_on_beat(info: TrackCuesV2.TrackCuesInfo) -> TrackCuesV2.TrackCuesInfo:
            return dataclasses.replace(
                info, cues=[dataclasses.replace(info.cues[0], position=round(beat)), *info.cues[1:]]
            )

        tags.modify_entries(first_cue_on_beat)
        with self.assertWarns(UserWarning):
            snapped = tags.snap_cues_to_beats(beatgrid, 1 / 16, min_ms_change=0)  # 0 lets it snap to where it is
        self.assertNotIn(0, [s.index for s in snapped])
        self.assertTrue(all(s.new_position != s.old_position for s in snapped), "only real moves")

    def test_snap_cues_to_beats_outside_tolerance_leaves_cues(self):
        tags = TrackCuesV2(TEST_MP3)
        positions = cue_positions(tags)
        self.assertEqual(tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 1000), [])
        self.assertEqual(cue_positions(tags), positions)
        self.assertFalse(tags.has_changed)

    def test_snap_cues_to_beats_without_a_cues_tag_raises(self):
        path = untagged_mp3(self)
        tags = TrackCuesV2(path)
        with self.assertRaises(NoCuesError) as caught:
            tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 8)
        self.assertEqual(caught.exception.filename, path)
        self.assertEqual(str(caught.exception), f"no Serato Markers2 tag: {path}")
        self.assertFalse(tags.has_changed)

    def test_snap_cues_to_beats_with_no_cues_in_the_tag_moves_nothing(self):
        tags = TrackCuesV2(TEST_MP3)
        tags.modify_entries(lambda info: dataclasses.replace(info, cues=[]))
        self.assertEqual(tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 8), [])

    def test_snap_cues_to_beats_without_a_beatgrid_raises(self):
        # as for a track Serato hasn't analyzed, with cues from Mixed In Key
        path = mp3_without(self, TrackBeatgrid.GEOB_KEY)
        tags = TrackCuesV2(path)
        positions = cue_positions(tags)
        with self.assertRaises(NoBeatgridError) as caught:
            tags.snap_cues_to_beats(TrackBeatgrid(path), 1 / 8)
        self.assertEqual(caught.exception.filename, path)
        self.assertEqual(cue_positions(tags), positions)
        self.assertFalse(tags.has_changed)

    def test_snap_cues_to_beats_warns_below_min_ms_change_2(self):
        tags = TrackCuesV2(TEST_MP3)
        with self.assertWarnsRegex(UserWarning, "min_ms_change=1") as caught:
            tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 8, min_ms_change=1)
        self.assertEqual(caught.filename, __file__)

    def test_cli_snap_cues(self):
        path = temp_mp3(self)
        with snap_cues_cli(path) as out, self.assertRaises(SystemExit):
            main()

        self.assertEqual(
            out.getvalue().splitlines(), ["Snapped cue 1 by 42 ms", "Snapped cue 2 by -2 ms", "Snapped cue 4 by -2 ms"]
        )
        self.assertEqual(cue_positions(TrackCuesV2(path)), SNAPPED_CUE_POSITIONS)
        self.assertFalse(has_tags_v1(path), "the CLI's save deletes the v1 tag, as before")

    def test_cli_snap_cues_without_a_beatgrid_exits_with_the_error(self):
        path = mp3_without(self, TrackBeatgrid.GEOB_KEY)
        before = read_bytes(path)
        with snap_cues_cli(path), self.assertRaises(SystemExit) as caught:
            main()
        self.assertEqual(str(caught.exception.code), f"Can't snap the cues: no Serato BeatGrid tag: {path}")
        self.assertEqual(read_bytes(path), before, "unchanged")

    def test_loop_fields(self):
        # track_cues_v2_saved_loops.bin is a tag Serato wrote with 4 loops, the second one locked
        tags = TrackCuesV2(fixture("_saved_loops"))
        loops = tags._from_entries().loops
        self.assertEqual([loop.color for loop in loops], [b"\x27\xaa\xe1"] * 4)
        self.assertEqual([loop.locked for loop in loops], [False, True, False, False])

        # a loop's color is bytes 15-17, after 4 bytes of ff and one 00
        serialized = dataclasses.replace(loops[0], color=b"\xcc\x00\x00")._serialize()
        self.assertEqual(serialized[10:20], b"\xff\xff\xff\xff\x00\xcc\x00\x00\x00\x00")

    def test_cue_colors_are_seratos_18(self):
        # Serato DJ Intro's palette, which it displays as stored (docs/colors.md)
        palette = "CC0000 CC4400 CC8800 CCCC00 88CC00 44CC00 00CC00 00CC44 00CC88 00CCCC 0088CC 0044CC 0000CC 4400CC 8800CC CC00CC CC0088 CC0044"
        self.assertEqual([color.value.hex().upper() for color in TrackCuesV2.CueColors], palette.split())

    def test_an_entry_unlike_seratos_raises(self):
        loop = TrackCuesV2(fixture("_saved_loops"))._from_entries().loops[0]._serialize()
        info = TrackCuesV2(fixture())._from_entries()
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


if __name__ == "__main__":
    unittest.main()
