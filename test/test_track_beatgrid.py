# pylint: disable=protected-access
import struct

import pytest

from serato_tools.track_beatgrid import TrackBeatgrid, main
from serato_tools.utils.track_tags import NoBeatgridError

from test.helpers.cli import cli_args
from test.helpers.files import read_bytes
from test.helpers.track_tags import TEST_MP3, copy_mp3_without

BEATGRID = "test/data/track_beatgrid.bin"
Marker = TrackBeatgrid.NonTerminalBeatgridMarker
Last = TrackBeatgrid.TerminalBeatgridMarker
Footer = TrackBeatgrid.Footer


@pytest.fixture
def no_beatgrid_mp3(tmp_dir: str) -> str:
    return copy_mp3_without(tmp_dir, TrackBeatgrid.GEOB_KEY)


def test_parse():
    tags = TrackBeatgrid(read_bytes(BEATGRID))
    assert tags.entries == (Last(position_s=0.029895611107349396, bpm=75.0), Footer(unknown=0))


def test_get_snapped_position_ignores_1ms_by_default():
    beatgrid = TrackBeatgrid(TEST_MP3)
    beat = beatgrid.find_nearest_beat(45104, 1)  # the test mp3's first cue, 42 ms before a beat
    assert beat is not None
    beat_ms = round(beat)
    assert beatgrid.get_snapped_position(beat_ms + 1, 1 / 8) is None
    assert beatgrid.get_snapped_position(beat_ms - 1, 1 / 8) is None
    assert beatgrid.get_snapped_position(beat_ms + 2, 1 / 8) == beat_ms
    assert beatgrid.get_snapped_position(beat_ms + 1, 1 / 8, min_ms_change=1) == beat_ms
    assert beatgrid.get_snapped_position(beat_ms + 60, 1 / 1000) is None, "outside tolerance"


@pytest.mark.parametrize(
    "markers",
    [
        pytest.param((Marker(1.0, 0), Last(2.0, 120.0)), id="a marker with 0 beats"),
        pytest.param((Marker(1.0, 4), Last(1.0, 120.0)), id="a marker at the same position as the one before"),
        pytest.param((Marker(1.0, 4), Marker(3.0, 4), Last(2.0, 120.0)), id="a marker before the one before"),
        pytest.param((Marker(1.0, 4), Last(2.0, 0.0)), id="a BPM of 0"),
        pytest.param((Last(2.0, float("nan")),), id="a NaN BPM"),
    ],
)
def test_a_grid_serato_wouldnt_write_raises(markers: tuple[Marker | Last, ...]):
    data = b"\x01\x00" + struct.pack(">I", len(markers))
    for marker in markers:
        data += struct.pack(">f", marker.position_s)
        data += struct.pack(">f" if isinstance(marker, Last) else ">I", marker[1])
    with pytest.raises(ValueError):  # parsing
        TrackBeatgrid(data + b"\x00")

    tags = TrackBeatgrid(read_bytes(BEATGRID))
    tags.entries = (*markers, Footer(0))  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValueError):  # saving
        tags._serialize()


@pytest.mark.parametrize(
    "entries",
    [
        pytest.param((Marker(1.0, 4), Footer(0)), id="no terminal marker"),
        pytest.param((Footer(0), Last(2.0, 120.0)), id="the footer first"),
    ],
)
def test_entries_out_of_order_raise_on_saving(entries: tuple):
    tags = TrackBeatgrid(read_bytes(BEATGRID))
    tags.entries = entries  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValueError):
        tags._serialize()


def test_bytes_after_the_footer_raise():
    with pytest.raises(ValueError, match="1 bytes after its footer"):
        TrackBeatgrid(read_bytes(BEATGRID) + b"\x00")


@pytest.mark.parametrize(
    "find",
    [
        pytest.param(lambda beatgrid: beatgrid.get_snapped_position(45104, 1 / 8), id="get_snapped_position"),
        pytest.param(lambda beatgrid: beatgrid.find_nearest_beat(45104, 1 / 8), id="find_nearest_beat"),
        pytest.param(lambda beatgrid: beatgrid.get_beat_position(45104), id="get_beat_position"),
    ],
)
def test_without_a_beatgrid_finding_beats_raises(no_beatgrid_mp3: str, find):
    # rather than returning None, which reads as "don't move the cue"
    with pytest.raises(NoBeatgridError) as caught:
        find(TrackBeatgrid(no_beatgrid_mp3))
    assert caught.value.filename == no_beatgrid_mp3


def test_no_beatgrid_error_from_bytes_has_no_filename():
    assert str(NoBeatgridError()) == "no Serato BeatGrid tag"


def test_cli_without_a_beatgrid_exits_with_the_error(no_beatgrid_mp3: str):
    with cli_args("serato_beatgrid", no_beatgrid_mp3), pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == f"no Serato BeatGrid tag: {no_beatgrid_mp3}"
