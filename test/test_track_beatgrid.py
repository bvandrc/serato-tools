import struct
from unittest import mock

import pytest
from mutagen.mp3 import MP3

from serato_tools.track_beatgrid import TrackBeatgrid, main
from serato_tools.utils.beatgrid_analyze import BeatGridInfo
from serato_tools.utils.track_tags import GeobKeys, NoBeatgridError, set_geob

from test.helpers.cli import cli_args
from test.helpers.files import read_bytes
from test.helpers.track_tags import DATA_FILES, FIRST_CUE_POSITION, TEST_MP3

Marker = TrackBeatgrid.NonTerminalBeatgridMarker
Last = TrackBeatgrid.TerminalBeatgridMarker
Footer = TrackBeatgrid.Footer

# 4 beats at 60 BPM, 8 at 240, then 120 to the end
GRID = (Marker(0.0, 4), Marker(4.0, 8), Last(6.0, 120.0))


def grid_bytes(markers: tuple[Marker | Last, ...]) -> bytes:
    """The tag's bytes for a grid of `markers`."""
    data = b"\x01\x00" + struct.pack(">I", len(markers))
    for marker in markers:
        data += struct.pack(">f", marker.position_s)
        data += struct.pack(">f" if isinstance(marker, Last) else ">I", marker[1])
    return data + b"\x00"


def test_parse():
    tags = TrackBeatgrid(read_bytes(DATA_FILES.BEATGRID))
    assert tags.entries == (Last(position_s=0.029895611107349396, bpm=75.0), Footer(unknown=0))


@pytest.mark.parametrize("position_ms, beats", [(0, 0), (2000, 2), (4000, 4), (5000, 8), (6000, 12), (7000, 14)])
def test_get_beat_position_across_markers(position_ms: int, beats: int):
    assert TrackBeatgrid(grid_bytes(GRID)).get_beat_position(position_ms) == pytest.approx(beats)


def test_get_beats_across_markers(mp3: str):
    tagfile = MP3(mp3)
    set_geob(tagfile, GeobKeys.BEATGRID, grid_bytes(GRID))
    tagfile.save()

    beats = TrackBeatgrid(mp3).get_beats()
    assert [(beat.position_s, beat.bpm) for beat in beats[:14]] == [
        *((float(i), 60.0) for i in range(4)),
        *((4.0 + i / 4, 240.0) for i in range(8)),
        (6.0, 120.0),
        (6.5, 120.0),
    ]
    assert beats[-1].position_s <= MP3(TEST_MP3).info.length, "to the end of the track"


def test_get_snapped_position_ignores_1ms_by_default():
    beatgrid = TrackBeatgrid(TEST_MP3)
    beat = beatgrid.find_nearest_beat(FIRST_CUE_POSITION, 1)
    assert beat is not None
    beat_ms = round(beat)
    assert beatgrid.get_snapped_position(beat_ms + 1, 1 / 8) is None
    assert beatgrid.get_snapped_position(beat_ms - 1, 1 / 8) is None
    assert beatgrid.get_snapped_position(beat_ms + 2, 1 / 8) == beat_ms
    assert beatgrid.get_snapped_position(beat_ms + 1, 1 / 8, min_ms_change=1) == beat_ms
    assert beatgrid.get_snapped_position(beat_ms + 60, 1 / 1000) is None, "outside tolerance"


@pytest.mark.parametrize(
    "markers, message",
    [
        pytest.param((Marker(1.0, 0), Last(2.0, 120.0)), "has 0 beats", id="a marker with 0 beats"),
        pytest.param(
            (Marker(1.0, 4), Last(1.0, 120.0)),
            "doesn't come after",
            id="a marker at the same position as the one before",
        ),
        pytest.param(
            (Marker(1.0, 4), Marker(3.0, 4), Last(2.0, 120.0)),
            "doesn't come after",
            id="a marker before the one before",
        ),
        pytest.param((Marker(1.0, 4), Last(2.0, 0.0)), "a BPM of 0", id="a BPM of 0"),
        pytest.param((Last(2.0, float("nan")),), "a BPM of nan", id="a NaN BPM"),
    ],
)
def test_a_grid_serato_wouldnt_write_raises(markers: tuple[Marker | Last, ...], message: str):
    with pytest.raises(ValueError, match=message):  # parsing
        TrackBeatgrid(grid_bytes(markers))

    tags = TrackBeatgrid(read_bytes(DATA_FILES.BEATGRID))
    tags.entries = (*markers, Footer(0))  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValueError, match=message):  # saving
        tags._serialize()
    with pytest.raises(ValueError, match=message):  # at a position before any bad segment, too
        tags.get_beat_position(0)


NOT_LAST = "last entry must be its footer"
NO_TERMINAL = "footer must come right after its terminal marker"
NOT_MARKERS = "entries before its terminal marker must be non-terminal markers"


@pytest.mark.parametrize(
    "entries, message",
    [
        pytest.param((Marker(1.0, 4), Footer(0)), NO_TERMINAL, id="no terminal marker"),
        pytest.param((Footer(0),), NO_TERMINAL, id="only a footer"),
        pytest.param((Footer(0), Last(2.0, 120.0)), NOT_LAST, id="the footer first"),
        pytest.param((Last(1.0, 120.0), Last(2.0, 120.0), Footer(0)), NOT_MARKERS, id="two terminal markers"),
        pytest.param(
            (Marker(1.0, 4), "not an entry", Last(2.0, 120.0), Footer(0)), NOT_MARKERS, id="a value that isn't an entry"
        ),
    ],
)
def test_entries_out_of_order_raise_on_saving(entries: tuple, message: str):
    tags = TrackBeatgrid(read_bytes(DATA_FILES.BEATGRID))
    tags.entries = entries  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValueError, match=message):
        tags._serialize()


def test_str_prints_an_invalid_grid():
    # for debugging a grid set in memory, which saving would reject
    tags = TrackBeatgrid(read_bytes(DATA_FILES.BEATGRID))
    markers = (TrackBeatgrid.NonTerminalBeatgridMarkerEnhanced(1.0, 0, 120.0), Last(2.0, 120.0))
    tags.enhanced_entries = (*markers, Footer(0))
    assert str(tags) == "\n".join(str(marker) for marker in markers)


def test_bytes_after_the_footer_raise():
    with pytest.raises(ValueError, match="1 bytes after its footer"):
        TrackBeatgrid(read_bytes(DATA_FILES.BEATGRID) + b"\x00")


@pytest.mark.parametrize(
    "find",
    [
        pytest.param(
            lambda beatgrid: beatgrid.get_snapped_position(FIRST_CUE_POSITION, 1 / 8), id="get_snapped_position"
        ),
        pytest.param(lambda beatgrid: beatgrid.find_nearest_beat(FIRST_CUE_POSITION, 1 / 8), id="find_nearest_beat"),
        pytest.param(lambda beatgrid: beatgrid.get_beat_position(FIRST_CUE_POSITION), id="get_beat_position"),
    ],
)
def test_without_a_beatgrid_finding_beats_raises(no_beatgrid_mp3: str, find):
    # rather than returning None, which reads as "don't move the cue"
    with pytest.raises(NoBeatgridError) as caught:
        find(TrackBeatgrid(no_beatgrid_mp3))
    assert caught.value.filename == no_beatgrid_mp3


def test_a_footer_only_tag_has_no_beatgrid():
    # a version, a marker count of 0, and the footer
    tags = TrackBeatgrid(b"\x01\x00" + struct.pack(">I", 0) + b"\x00")
    assert tags.entries is None
    with pytest.raises(NoBeatgridError):
        tags.find_nearest_beat(FIRST_CUE_POSITION, 1 / 8)


@pytest.mark.parametrize(
    "markers, dynamic",
    [
        pytest.param(GRID, True, id="several markers"),
        pytest.param((Last(0.5, 120.0),), False, id="terminal marker only"),
    ],
)
def test_is_dynamic(markers: tuple[Marker | Last, ...], dynamic: bool):
    assert TrackBeatgrid(grid_bytes(markers)).is_dynamic is dynamic


def test_without_a_beatgrid_isnt_dynamic(no_beatgrid_mp3: str):
    assert TrackBeatgrid(no_beatgrid_mp3).is_dynamic is False


def test_analyze_and_write_replaces_the_beats_found(mp3: str):
    beatgrid = TrackBeatgrid(mp3)
    beatgrid.get_beats()
    analyzed = BeatGridInfo(100.0, [], 1.0, 0.0, 1.0, downbeats=[0.5, 2.9])
    with mock.patch("serato_tools.utils.beatgrid_analyze.analyze_beatgrid", return_value=analyzed):
        beatgrid.analyze_and_write()
    assert beatgrid.find_nearest_beat(520, 0.1) == 500.0, "the new grid's first beat"


def test_analyze_and_write_giving_an_invalid_grid_keeps_the_old_one(mp3: str):
    beatgrid = TrackBeatgrid(mp3)
    entries, raw_data = beatgrid.entries, beatgrid._raw_data
    analyzed = BeatGridInfo(100.0, [], 1.0, 0.0, 1.0, downbeats=[2.9, 0.5])  # out of order
    with (
        mock.patch("serato_tools.utils.beatgrid_analyze.analyze_beatgrid", return_value=analyzed),
        pytest.raises(ValueError, match="doesn't come after"),
    ):
        beatgrid.analyze_and_write()
    assert (beatgrid.entries, beatgrid._raw_data) == (entries, raw_data)


def test_cli_without_a_beatgrid_exits_with_the_error(no_beatgrid_mp3: str):
    with cli_args("serato_beatgrid", no_beatgrid_mp3), pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == f"no Serato BeatGrid tag: {no_beatgrid_mp3}"
