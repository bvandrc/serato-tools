# pylint: disable=protected-access
import dataclasses
import unittest
import os
import io
from contextlib import redirect_stdout

from src.serato_tools.track_cues_v2 import TrackCuesV2


class TestCase(unittest.TestCase):
    def test_parse_and_dump(self):
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
        tags._dump()
        self.assertEqual(tags.raw_data, file_data, "dump")

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
        tags._dump()

        with open(os.path.abspath("test/data/track_cues_v2_modified.bin"), mode="rb") as fp:
            expected_modified_data = fp.read()
        self.assertEqual(tags.raw_data, expected_modified_data, "modified data dump")

    def test_snap_position_to_beat(self):
        tags = TrackCuesV2("test/data/test_mp3.mp3")
        buf = io.StringIO()
        with redirect_stdout(buf):
            tags.snap_positions_to_beat(1 / 16, 2)
        output = buf.getvalue()
        self.assertIn("Snapped by 42 ms", output)

    def test_snap_positions_to_beat_no_entries_raises(self):
        tags = TrackCuesV2("test/data/test_mp3.mp3")
        tags.entries = []
        with self.assertRaises(ValueError):
            tags.snap_positions_to_beat(1 / 8)

    def test_untested_version_raises_at_construction(self):
        with self.assertRaises(ValueError):
            TrackCuesV2(bytes([0x99, 0x99]))
