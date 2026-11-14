# pylint: disable=protected-access
import base64
import dataclasses
import struct
from typing import Callable

import pytest

from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v2 import TrackCuesV2, main
from serato_tools.utils.track_tags import NoBeatgridError, NoCuesError

from test.helpers.cli import cli_args
from test.helpers.files import read_bytes
from test.helpers.track_tags import SNAPPED_CUE_POSITIONS, TEST_MP3, copy_mp3_without, cue_positions, has_tags_v1

Colors = TrackCuesV2.TrackColors


def fixture(name: str = "") -> bytes:
    """The bytes of the Serato Markers2 tag fixture test/data/track_cues_v2{name}.bin."""
    return read_bytes(f"test/data/track_cues_v2{name}.bin")


def snap_cues_cli(path: str):
    """The command line that snaps `path`'s cues to its beats."""
    return cli_args("serato_snap_cues_v2", path, "--snap_cues", "--snap_tolerance", "1/16")


@pytest.fixture
def no_beatgrid_mp3(tmp_dir: str) -> str:
    # as for a track Serato hasn't analyzed, with cues from Mixed In Key
    return copy_mp3_without(tmp_dir, TrackBeatgrid.GEOB_KEY)


def test_parse_and_modify():
    tags = TrackCuesV2(fixture())
    assert [str(e) for e in tags.entries] == [
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
    ]
    assert tags.get_track_color_name() == "LIMEGREEN3", "the 99ff99 color"

    def rule(track: "TrackCuesV2.TrackCuesInfo") -> "TrackCuesV2.TrackCuesInfo | None":
        new_color = None
        if track.color is not None:
            new_color = dataclasses.replace(track.color, color=Colors.ORANGE.value)
        new_cues = [
            dataclasses.replace(c, color=TrackCuesV2.CueColors.RED.value, name="NEW" if c.name == "" else c.name)
            for c in track.cues
        ]
        return dataclasses.replace(track, color=new_color, cues=new_cues)

    tags.modify_entries(rule)

    assert [str(e) for e in tags.entries] == [
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
    ]
    assert tags._raw_data == fixture("_modified")


def edit_and_save(tags: TrackCuesV2, **save_kwargs: bool):
    tags.set_track_color(Colors.RED)
    tags.save(**save_kwargs)


def deprecated_keep(tags: TrackCuesV2):
    with pytest.warns(DeprecationWarning) as caught:
        tags.set_track_color(Colors.RED, delete_tags_v1=False)
    assert caught.pop(DeprecationWarning).filename == __file__, "points at the caller"
    tags.save()


def deprecated_keep_after_another_edit(tags: TrackCuesV2):
    tags.set_beatgrid_locked(True)
    with pytest.warns(DeprecationWarning):
        tags.set_track_color(Colors.RED, delete_tags_v1=False)
    tags.save()


@pytest.mark.parametrize(
    "edit, kept",
    [
        pytest.param(edit_and_save, False, id="saving deletes it by default"),
        pytest.param(lambda tags: edit_and_save(tags, delete_tags_v1=False), True, id="delete_tags_v1=False keeps it"),
        pytest.param(lambda tags: tags.save(force=True), False, id="a forced save deletes it too"),
        pytest.param(deprecated_keep, True, id="the deprecated False on an edit still keeps it"),
        # as when the earlier edit asked to delete it
        pytest.param(deprecated_keep_after_another_edit, False, id="the deprecated False loses to another edit"),
    ],
)
def test_tags_v1_after(mp3: str, edit: Callable[[TrackCuesV2], object], kept: bool):
    assert has_tags_v1(mp3), "fixture has the v1 tag"
    edit(TrackCuesV2(mp3))
    assert has_tags_v1(mp3) == kept


def test_a_callback_may_edit_in_place():
    tags = TrackCuesV2(TEST_MP3)
    position = tags._from_entries().cues[0].position

    def rule(info: TrackCuesV2.TrackCuesInfo) -> TrackCuesV2.TrackCuesInfo:
        info.cues[0].position += 1000
        return info

    tags.modify_entries(rule)
    assert tags.has_changed
    data = tags._raw_data
    assert data is not None
    assert TrackCuesV2(data)._from_entries().cues[0].position == position + 1000


def test_has_changed(mp3: str):
    tags = TrackCuesV2(mp3)
    original_color = Colors(tags.get_track_color())
    assert not tags.has_changed, "as read"
    tags.set_track_color(Colors.RED)
    assert tags.has_changed, "color changed"
    tags.modify_entries(dataclasses.replace)
    assert tags.has_changed, "an edit that changed nothing doesn't reset it"
    tags.set_track_color(original_color)
    assert not tags.has_changed, "color changed back"

    tags.set_track_color(Colors.RED)
    tags.modify_entries(dataclasses.replace)
    tags.save()
    assert not tags.has_changed, "saved"
    assert TrackCuesV2(mp3).get_track_color() == Colors.RED.value, "a change then an edit that changes nothing, written"


def test_set_beatgrid_locked():
    tags = TrackCuesV2(TEST_MP3)
    original_data = tags._raw_data
    assert not tags.is_beatgrid_locked()
    tags.set_beatgrid_locked(False)
    assert tags._raw_data == original_data, "already unlocked, so no change"
    assert tags.tagfile is not None
    assert "GEOB:Serato Markers_" in tags.tagfile, "v1 tag kept, since nothing changed"
    tags.set_beatgrid_locked(True)
    data = tags._raw_data
    assert data is not None
    assert TrackCuesV2(data).is_beatgrid_locked(), "serialized"


def test_setting_a_missing_color_or_lock_adds_it(untagged_mp3: str):
    tags = TrackCuesV2(untagged_mp3)
    assert tags.get_track_color_name() is None, "no color entry yet"
    tags.set_track_color(Colors.WHITE)
    tags.set_beatgrid_locked(False)
    assert tags.get_track_color() == Colors.WHITE.value
    assert not tags.is_beatgrid_locked()
    # track_cues_v2_analyzed.bin is the tag Serato wrote for a newly analyzed track: white, unlocked
    assert tags._raw_data == fixture("_analyzed"), "the tag Serato writes"
    tags.set_beatgrid_locked(True)
    assert tags.is_beatgrid_locked()


# tags Serato wrote: saved_loops's base64 ends in a character Serato drops, 514_bytes is longer than 470 bytes, flips
# has cues, a BPM lock, and then flips, in that order, full_last_line's base64 ends in a full line, and 982_bytes and
# 1494_bytes are 512-byte steps past 470
@pytest.mark.parametrize(
    "name", ["_saved_loops", "_514_bytes", "_flips", "_full_last_line", "_982_bytes", "_1494_bytes"]
)
def test_rewriting_keeps_seratos_bytes(name: str):
    data = fixture(name)
    tags = TrackCuesV2(data)
    tags.modify_entries(dataclasses.replace)
    assert tags._raw_data == data


def test_shrinking_keeps_the_tags_size():
    tags = TrackCuesV2(fixture("_514_bytes"))
    # track_cues_v2_514_bytes.bin has cues and loops: without them, it needs well under 470 bytes
    tags.modify_entries(lambda info: dataclasses.replace(info, cues=[], loops=[]))
    rewritten = tags._raw_data
    assert rewritten is not None
    assert len(rewritten) == 514
    assert TrackCuesV2(rewritten).entries == tags.entries


# Serato grew a 470-byte tag to track_cues_v2_982_bytes.bin, one 512-byte step. 1494_bytes is two steps, and its
# entries need both. Giving a 470-byte tag either's entries should give the same bytes
@pytest.mark.parametrize("name", ["_982_bytes", "_1494_bytes"])
def test_outgrowing_the_tags_size_grows_it_as_serato_does(name: str):
    grown = fixture(name)
    tags = TrackCuesV2(fixture("_analyzed"))
    tags.modify_entries(lambda _: TrackCuesV2.TrackCuesInfo.from_entries(TrackCuesV2(grown).entries))
    assert tags._raw_data == grown


def test_a_cue_past_8_raises():
    # cue 11 as found in a real tag, which Serato ignored: field4 cc and color cccccc
    cue_11 = bytes.fromhex("00 0a 00 02 14 98 cc cc cc cc 00 00 00")
    payload = b"\x01\x01" + b"CUE\x00" + struct.pack(">I", len(cue_11)) + cue_11 + b"\x00"
    with pytest.raises(ValueError, match="cue 11 is past Serato's 8 cue pads"):
        TrackCuesV2(b"\x01\x01" + base64.b64encode(payload))

    tags = TrackCuesV2(fixture("_analyzed"))
    cue_9 = TrackCuesV2.CueEntry(b"\x00", 8, 1000, b"\x00", TrackCuesV2.CueColors.RED.value, b"\x00\x00", "")
    with pytest.raises(ValueError, match="cue 9 is past Serato's 8 cue pads"):
        tags.modify_entries(lambda info: dataclasses.replace(info, cues=[cue_9]))


def test_snap_cues_to_beats():
    tags, beatgrid = TrackCuesV2(TEST_MP3), TrackBeatgrid(TEST_MP3)
    snapped = tags.snap_cues_to_beats(beatgrid, 1 / 16)
    # cues 3, 5, and 6 are 1 ms off their beats, which the default min_ms_change leaves alone
    SnappedCue = TrackCuesV2.SnappedCue
    assert snapped == [SnappedCue(0, 45104, 45146), SnappedCue(1, 67474, 67472), SnappedCue(3, 134451, 134449)]
    positions = cue_positions(tags)
    assert positions == SNAPPED_CUE_POSITIONS
    for position in positions:
        beat_position = beatgrid.get_beat_position(position)
        assert beat_position == pytest.approx(round(beat_position), abs=0.01), "on a beat"
    assert tags.has_changed


def test_snap_cues_to_beats_doesnt_count_a_cue_already_on_its_beat():
    tags, beatgrid = TrackCuesV2(TEST_MP3), TrackBeatgrid(TEST_MP3)
    beat = beatgrid.find_nearest_beat(45104, 1)  # the first cue's beat, 42 ms after it
    assert beat is not None

    def first_cue_on_beat(info: TrackCuesV2.TrackCuesInfo) -> TrackCuesV2.TrackCuesInfo:
        return dataclasses.replace(info, cues=[dataclasses.replace(info.cues[0], position=round(beat)), *info.cues[1:]])

    tags.modify_entries(first_cue_on_beat)
    with pytest.warns(UserWarning):
        snapped = tags.snap_cues_to_beats(beatgrid, 1 / 16, min_ms_change=0)  # 0 lets it snap to where it is
    assert 0 not in [s.index for s in snapped]
    assert all(s.new_position != s.old_position for s in snapped), "only real moves"


def test_snap_cues_to_beats_outside_tolerance_leaves_cues():
    tags = TrackCuesV2(TEST_MP3)
    positions = cue_positions(tags)
    assert tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 1000) == []
    assert cue_positions(tags) == positions
    assert not tags.has_changed


def test_snap_cues_to_beats_without_a_cues_tag_raises(untagged_mp3: str):
    tags = TrackCuesV2(untagged_mp3)
    with pytest.raises(NoCuesError) as caught:
        tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 8)
    assert caught.value.filename == untagged_mp3
    assert str(caught.value) == f"no Serato Markers2 tag: {untagged_mp3}"
    assert not tags.has_changed


def test_snap_cues_to_beats_with_no_cues_in_the_tag_moves_nothing():
    tags = TrackCuesV2(TEST_MP3)
    tags.modify_entries(lambda info: dataclasses.replace(info, cues=[]))
    assert tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 8) == []


def test_snap_cues_to_beats_without_a_beatgrid_raises(no_beatgrid_mp3: str):
    tags = TrackCuesV2(no_beatgrid_mp3)
    positions = cue_positions(tags)
    with pytest.raises(NoBeatgridError) as caught:
        tags.snap_cues_to_beats(TrackBeatgrid(no_beatgrid_mp3), 1 / 8)
    assert caught.value.filename == no_beatgrid_mp3
    assert cue_positions(tags) == positions
    assert not tags.has_changed


def test_snap_cues_to_beats_warns_below_min_ms_change_2():
    tags = TrackCuesV2(TEST_MP3)
    with pytest.warns(UserWarning, match="min_ms_change=1") as caught:
        tags.snap_cues_to_beats(TrackBeatgrid(TEST_MP3), 1 / 8, min_ms_change=1)
    assert caught.pop(UserWarning).filename == __file__


def test_cli_snap_cues(mp3: str):
    with snap_cues_cli(mp3) as out, pytest.raises(SystemExit):
        main()

    assert out.getvalue().splitlines() == ["Snapped cue 1 by 42 ms", "Snapped cue 2 by -2 ms", "Snapped cue 4 by -2 ms"]
    assert cue_positions(TrackCuesV2(mp3)) == SNAPPED_CUE_POSITIONS
    assert not has_tags_v1(mp3), "the CLI's save deletes the v1 tag, as before"


def test_cli_snap_cues_without_a_beatgrid_exits_with_the_error(no_beatgrid_mp3: str):
    before = read_bytes(no_beatgrid_mp3)
    with snap_cues_cli(no_beatgrid_mp3), pytest.raises(SystemExit) as caught:
        main()
    assert str(caught.value.code) == f"Can't snap the cues: no Serato BeatGrid tag: {no_beatgrid_mp3}"
    assert read_bytes(no_beatgrid_mp3) == before, "unchanged"


def test_loop_fields():
    # track_cues_v2_saved_loops.bin is a tag Serato wrote with 4 loops, the second one locked
    loops = TrackCuesV2(fixture("_saved_loops"))._from_entries().loops
    assert [loop.color for loop in loops] == [b"\x27\xaa\xe1"] * 4
    assert [loop.locked for loop in loops] == [False, True, False, False]

    # a loop's color is bytes 15-17, after 4 bytes of ff and one 00
    serialized = dataclasses.replace(loops[0], color=b"\xcc\x00\x00")._serialize()
    assert serialized[10:20] == b"\xff\xff\xff\xff\x00\xcc\x00\x00\x00\x00"


def test_cue_colors_are_seratos_18():
    # Serato DJ Intro's palette, which it displays as stored (docs/colors.md)
    palette = "CC0000 CC4400 CC8800 CCCC00 88CC00 44CC00 00CC00 00CC44 00CC88 00CCCC 0088CC 0044CC 0000CC 4400CC 8800CC CC00CC CC0088 CC0044"
    assert [color.value.hex().upper() for color in TrackCuesV2.CueColors] == palette.split()


def _entries_unlike_seratos() -> dict[str, tuple[type, bytes]]:
    """Serialized entries each changed in one way Serato never writes, by name, with the class to parse them with."""
    loop = TrackCuesV2(fixture("_saved_loops"))._from_entries().loops[0]._serialize()
    info = TrackCuesV2(fixture())._from_entries()
    assert info.color is not None and info.bpm_lock is not None
    color, cue, bpm_lock = info.color._serialize(), info.cues[0]._serialize(), info.bpm_lock._serialize()

    def changed(data: bytes, index: int, value: bytes) -> bytes:
        return data[:index] + value + data[index + len(value) :]

    return {
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


ENTRIES_UNLIKE_SERATOS = _entries_unlike_seratos()


@pytest.mark.parametrize("entry_class, data", ENTRIES_UNLIKE_SERATOS.values(), ids=ENTRIES_UNLIKE_SERATOS.keys())
def test_an_entry_unlike_seratos_raises(entry_class, data: bytes):
    with pytest.raises(ValueError):
        entry_class._parse(data)
