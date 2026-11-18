import dataclasses
from collections.abc import Callable
from unittest import mock

import pytest
from mutagen.aiff import AIFF

from serato_tools.track import Track
from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain

from test.helpers.track_tags import (
    SNAPPED_CUE_POSITIONS,
    TEST_MP3,
    aiff_with_the_mp3s_tags,
    copy_mp3_with_empty_id3,
    cue_positions,
    has_tags_v1,
    tagfile_saves,
    untagged_aiff,
)

Colors = TrackCuesV2.TrackColors


def test_reads_each_tag_from_one_open_file_and_saves_none_unchanged(mp3: str):
    track = Track(mp3, waveform=True)

    tags = (
        track.cues_v2,
        track.cues_v1,
        track.beatgrid,
        track.autotags,
        track.waveform,
        track.gain,
        track.text_frames,
    )
    for tag in tags:
        assert tag.tagfile is track.tagfile, f"{type(tag).__name__} shares the open file"
    assert track.cues_v2 is track.cues_v2, "each tag read once"
    assert track.get_track_color() == TrackCuesV2(mp3).get_track_color()
    assert track.autotags.bpm == TrackAutotags(mp3).bpm
    assert track.gain.gain == TrackGain(mp3).gain

    with tagfile_saves(track.tagfile) as writes:
        assert not track.has_changed, "as read"
        assert track.save() is False
    writes.assert_not_called()


def test_parses_every_tag_but_the_waveform_by_default(mp3: str):
    with mock.patch("serato_tools.track.TrackWaveform") as waveform:
        track = Track(mp3)
    waveform.assert_not_called()
    with pytest.raises(ValueError, match="waveform=True"):
        _ = track.waveform
    assert track.cues_v1.entries is not None, "the other tags are parsed"


def test_tag_passed_false_isnt_parsed_or_saved(mp3: str):
    with mock.patch("serato_tools.track.TrackCuesV1") as cues_v1:
        track = Track(mp3, cues_v1=False)
    cues_v1.assert_not_called()
    with pytest.raises(ValueError, match="cues_v1=True"):
        _ = track.cues_v1

    track = Track(mp3, cues_v2=False, cues_v1=False, beatgrid=False, autotags=False, gain=False, text_frames=False)
    with tagfile_saves(track.tagfile) as writes:
        assert track.save() is False, "no tags, nothing to save"
    writes.assert_not_called()


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(lambda track: track.set_track_color(Colors.RED), id="cues_v2"),
        pytest.param(lambda track: track.autotags.set(bpm=128), id="autotags"),
        pytest.param(lambda track: track.gain.set(gain=-2.5), id="gain"),
        pytest.param(lambda track: track.text_frames.set("TIT2", "New Title"), id="text_frames"),
    ],
)
def test_one_tags_change_is_a_change(mp3: str, edit: Callable[[Track], object]):
    track = Track(mp3)
    edit(track)
    assert track.has_changed


def test_save_writes_every_change_at_once(mp3: str):
    track = Track(mp3)
    assert track.is_beatgrid_locked() is False, "fixture is unlocked"
    track.set_track_color(Colors.RED)
    track.set_beatgrid_locked(True)
    assert track.is_beatgrid_locked() is True, "before saving"
    track.autotags.set(bpm=128)
    track.gain.set(gain=-2.5)
    track.text_frames.set("TIT2", "New Title")
    assert track.has_changed

    with tagfile_saves(track.tagfile) as writes:
        assert track.save() is True
    writes.assert_called_once()
    assert not track.has_changed, "saved"
    saved = Track(mp3)
    assert saved.get_track_color() == Colors.RED.value
    assert saved.is_beatgrid_locked() is True
    assert saved.autotags.bpm == 128
    assert saved.gain.gain == pytest.approx(-2.5, abs=0.005)
    assert saved.text_frames.get("TIT2") == "New Title"


@pytest.mark.parametrize(
    "save_kwargs, kept",
    [
        pytest.param({}, False, id="by default"),
        pytest.param({"delete_tags_v1": False}, True, id="delete_tags_v1=False"),
    ],
)
def test_save_deletes_tags_v1_unless_told_not_to(mp3: str, save_kwargs: dict[str, bool], kept: bool):
    track = Track(mp3)
    assert track.cues_v1.entries is not None, "fixture has the v1 tag, read before it's deleted"
    track.set_track_color(Colors.RED)
    track.save(**save_kwargs)

    assert has_tags_v1(mp3) == kept, "an unchanged v1 tag isn't restored"


def test_delete_tags_v1_on_an_edit_is_deprecated(mp3: str):
    track = Track(mp3)
    with pytest.warns(DeprecationWarning, match="passing delete_tags_v1 to an edit is deprecated") as caught:
        track.set_track_color(Colors.RED, delete_tags_v1=False)
    assert caught.pop(DeprecationWarning).filename == __file__, "points at the caller, not at Track"
    track.save()

    assert has_tags_v1(mp3), "False still keeps the v1 tag"


def _changed_back(cues: TrackCuesV2):
    color = Colors(cues.get_track_color())
    cues.set_track_color(Colors.RED)
    cues.set_track_color(color)


@pytest.mark.parametrize(
    "edit",
    [
        pytest.param(lambda cues: cues.modify_entries(dataclasses.replace), id="changed nothing"),
        pytest.param(_changed_back, id="changed back"),
    ],
)
def test_an_unwritten_cue_edit_keeps_tags_v1_when_another_tag_saves(mp3: str, edit):
    track = Track(mp3)
    edit(track.cues_v2)
    track.autotags.set(bpm=128)
    track.save()

    assert has_tags_v1(mp3)


@pytest.mark.parametrize(
    "tag, key",
    [
        pytest.param("autotags", f"GEOB:{TrackAutotags.GEOB_KEY}", id="autotags"),
        pytest.param("gain", TrackGain.RVA2_KEY, id="gain"),
    ],
)
def test_save_writes_deletions(mp3: str, tag: str, key: str):
    track = Track(mp3)
    getattr(track, tag).delete()

    assert track.save() is True, "deletion alone is a change"
    assert key not in Track(mp3).tagfile


def test_snap_cues_to_beats_with_its_own_beatgrid(mp3: str):
    # what moves, and where to, is TrackCuesV2.snap_cues_to_beats', tested in test_track_cues_v2
    track = Track(mp3)
    with mock.patch.object(track.cues_v2, "snap_cues_to_beats", wraps=track.cues_v2.snap_cues_to_beats) as snap:
        snapped = track.snap_cues_to_beats(1 / 16)
    snap.assert_called_once_with(track.beatgrid, 1 / 16, 2)
    assert len(snapped) == 3

    assert track.save() is True
    assert cue_positions(Track(mp3).cues_v2) == SNAPPED_CUE_POSITIONS, "saved"


def test_snap_cues_to_beats_needs_only_cues_v2_and_beatgrid(mp3: str):
    track = Track(mp3, cues_v1=False, autotags=False, gain=False, text_frames=False)
    assert track.snap_cues_to_beats(1 / 16)


@pytest.mark.parametrize(
    "file, flag",
    [
        pytest.param("mp3", "cues_v2", id="cues_v2"),
        pytest.param("mp3", "beatgrid", id="beatgrid"),
        pytest.param("no_cues_mp3", "beatgrid", id="beatgrid, even with no cues to move"),
    ],
)
def test_snap_cues_to_beats_without_cues_v2_or_beatgrid_raises(request: pytest.FixtureRequest, file: str, flag: str):
    with pytest.raises(ValueError, match=f"{flag}=True"):
        Track(request.getfixturevalue(file), **{flag: False}).snap_cues_to_beats(1 / 16)


@pytest.mark.parametrize("name", ["test.aif", "test.aiff", "TEST.AIF"])
def test_an_aiff_reads_and_saves_as_an_mp3_does(tmp_dir: str, name: str):
    path = aiff_with_the_mp3s_tags(tmp_dir, name)
    track, mp3 = Track(path, waveform=True), Track(TEST_MP3, waveform=True)

    assert isinstance(track.tagfile, AIFF), "opened as an AIFF, whatever its extension's case"
    assert not track.has_changed, "as read"
    assert cue_positions(track.cues_v2) == cue_positions(mp3.cues_v2)
    assert track.get_track_color() == mp3.get_track_color()
    assert track.beatgrid.entries == mp3.beatgrid.entries
    assert track.autotags.bpm == mp3.autotags.bpm
    assert track.gain.gain == mp3.gain.gain
    assert track.waveform.data == mp3.waveform.data
    assert track.text_frames.get("TIT2") == mp3.text_frames.get("TIT2")

    assert has_tags_v1(path), "the mp3's v1 tag copied"
    track.set_track_color(Colors.BLUE1)
    assert track.save() is True
    assert Track(path).get_track_color() == Colors.BLUE1.value
    assert not has_tags_v1(path), "the v1 tag deleted, as from an mp3"


# a file whose ID3 tags have no frames is falsy to mutagen, which once read as "no file"
@pytest.mark.parametrize(
    "make_file",
    [
        pytest.param(copy_mp3_with_empty_id3, id="an mp3 whose ID3 tag has no frames"),
        pytest.param(untagged_aiff, id="an AIFF with no tags"),
    ],
)
def test_a_file_with_no_tags_reads_and_saves(tmp_dir: str, make_file):
    path = make_file(tmp_dir)
    track = Track(path)
    assert track.get_track_color() is None, "no color yet"
    assert track.text_frames.get("TIT2") is None, "no title yet"

    track.set_track_color(Colors.RED)
    track.text_frames.set("TIT2", "A Title")
    assert track.save() is True
    saved = Track(path)
    assert saved.get_track_color() == Colors.RED.value
    assert saved.text_frames.get("TIT2") == "A Title"
