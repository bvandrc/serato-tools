# pylint: disable=protected-access
import pytest

from serato_tools.track_cues_v1 import TrackCuesV1

from test.helpers.files import read_bytes
from test.helpers.track_tags import CUES_V1_DATA

DATA = read_bytes(CUES_V1_DATA)


def test_parse():
    tags = TrackCuesV1(DATA)
    unset = "start_position_set=False, start_position=None, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\x00\\x00\\x00'"
    # 3 cues, 2 unset cues, 9 unset loops, and the track color
    assert [str(e) for e in tags.entries] == [
        "Entry(start_position_set=True, start_position=0, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\xcc\\x00\\x00', type=<EntryType.CUE: 1>, is_locked=0)",
        "Entry(start_position_set=True, start_position=218456, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\xcc\\x88\\x00', type=<EntryType.CUE: 1>, is_locked=0)",
        "Entry(start_position_set=True, start_position=60004, end_position_set=False, end_position=None, field5=b'\\x00\\x7f\\x7f\\x7f\\x7f\\x7f', color=b'\\x00\\x00\\xcc', type=<EntryType.CUE: 1>, is_locked=0)",
        *[f"Entry({unset}, type=<EntryType.INVALID: 0>, is_locked=0)"] * 2,
        *[f"Entry({unset}, type=<EntryType.LOOP: 3>, is_locked=0)"] * 9,
        "Color(color=b'\\xff\\xff\\xff')",
    ]


@pytest.mark.parametrize(
    "keep",
    [
        pytest.param(lambda entry: False, id="no entries"),
        pytest.param(lambda entry: not isinstance(entry, TrackCuesV1.Color), id="no trailing Color"),
    ],
)
def test_serialize_without_trailing_color_raises(keep):
    tags = TrackCuesV1(DATA)
    tags.entries = [e for e in tags.entries if keep(e)]
    with pytest.raises(ValueError):
        tags._serialize()


@pytest.mark.parametrize(
    "data, message",
    [
        pytest.param(
            DATA[:6] + b"\x01" + DATA[7:],  # the first entry's start_position_set
            "start_position_set is 00 or 7f, not 01",
            id="a set flag that isn't 00 or 7f",
        ),
        pytest.param(DATA[:20], "partway through an entry", id="cut off partway through an entry"),
    ],
)
def test_malformed_tag_raises(data: bytes, message: str):
    with pytest.raises(ValueError, match=message):
        TrackCuesV1(data)
