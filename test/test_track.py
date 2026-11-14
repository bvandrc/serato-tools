import dataclasses
from unittest import mock

import pytest

from serato_tools.track import Track
from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain

from test.helpers.track_tags import SNAPPED_CUE_POSITIONS, cue_positions, has_tags_v1


def counting_writes(track: Track):
    """Patches `track`'s file save, within the block, to also count its calls in the mock it gives."""
    return mock.patch.object(track.tagfile, "save", wraps=track.tagfile.save)


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

    with counting_writes(track) as writes:
        assert not track.has_changed, "as read"
        assert not track.save()
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
    with counting_writes(track) as writes:
        assert not track.save(), "no tags, nothing to save"
    writes.assert_not_called()


def test_save_writes_every_change_at_once(mp3: str):
    track = Track(mp3)
    assert not track.is_beatgrid_locked(), "fixture is unlocked"
    track.set_track_color(TrackCuesV2.TrackColors.RED)
    track.set_beatgrid_locked(True)
    assert track.is_beatgrid_locked(), "before saving"
    track.autotags.set(bpm=128)
    track.gain.set(gain=-2.5)
    track.text_frames.set("TIT2", "New Title")
    assert track.has_changed

    with counting_writes(track) as writes:
        assert track.save()
    writes.assert_called_once()
    assert not track.has_changed, "saved"
    saved = Track(mp3)
    assert saved.get_track_color() == TrackCuesV2.TrackColors.RED.value
    assert saved.is_beatgrid_locked()
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
    track.set_track_color(TrackCuesV2.TrackColors.RED)
    track.save(**save_kwargs)

    assert has_tags_v1(mp3) == kept, "an unchanged v1 tag isn't restored"


def test_delete_tags_v1_on_an_edit_is_deprecated(mp3: str):
    track = Track(mp3)
    with pytest.warns(DeprecationWarning) as caught:
        track.set_track_color(TrackCuesV2.TrackColors.RED, delete_tags_v1=False)
    assert caught.pop(DeprecationWarning).filename == __file__, "points at the caller, not at Track"
    track.save()

    assert has_tags_v1(mp3), "False still keeps the v1 tag"


def _changed_back(cues: TrackCuesV2):
    color = TrackCuesV2.TrackColors(cues.get_track_color())
    cues.set_track_color(TrackCuesV2.TrackColors.RED)
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
    "tag, key", [("autotags", f"GEOB:{TrackAutotags.GEOB_KEY}"), ("gain", TrackGain.RVA2_KEY)], ids=["autotags", "gain"]
)
def test_save_writes_deletions(mp3: str, tag: str, key: str):
    track = Track(mp3)
    getattr(track, tag).delete()

    assert track.save(), "deletion alone is a change"
    assert key not in Track(mp3).tagfile


def test_snap_cues_to_beats_with_its_own_beatgrid(mp3: str):
    # what moves, and where to, is TrackCuesV2.snap_cues_to_beats', tested in test_track_cues_v2
    track = Track(mp3)
    with mock.patch.object(track.cues_v2, "snap_cues_to_beats", wraps=track.cues_v2.snap_cues_to_beats) as snap:
        snapped = track.snap_cues_to_beats(1 / 16)
    snap.assert_called_once_with(track.beatgrid, 1 / 16, 2)
    assert len(snapped) == 3

    assert track.save()
    assert cue_positions(Track(mp3).cues_v2) == SNAPPED_CUE_POSITIONS, "saved"


def test_snap_cues_to_beats_needs_only_cues_v2_and_beatgrid(mp3: str, untagged_mp3: str):
    track = Track(mp3, cues_v1=False, autotags=False, gain=False)
    assert track.snap_cues_to_beats(1 / 16)
    for name in ("cues_v2", "beatgrid"):
        with pytest.raises(ValueError, match=f"{name}=True"):
            Track(mp3, **{name: False}).snap_cues_to_beats(1 / 16)
    with pytest.raises(ValueError, match="beatgrid=True"):
        Track(untagged_mp3, beatgrid=False).snap_cues_to_beats(1 / 16)  # even with no cues to move


def test_snap_cues_to_beats_warns_at_the_caller(mp3: str):
    track = Track(mp3)
    with pytest.warns(UserWarning, match="min_ms_change=1") as caught:
        track.snap_cues_to_beats(1 / 8, min_ms_change=1)
    assert caught.pop(UserWarning).filename == __file__, "past Track, not at it"
