# pylint: disable=protected-access
import pytest

from serato_tools.track_cues_v1 import TrackCuesV1

from test.helpers.files import read_bytes
from test.helpers.track_tags import DATA_FILES

DATA = read_bytes(DATA_FILES.CUES_V1)


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
    with pytest.raises(ValueError, match="last entry must be a Color entry"):
        tags._serialize()

    def test_a_tag_unlike_seratos_raises(self):
        # track_cues_v1.bin's entries: 0-2 are set cues, 3-4 unset cues, and 5-13 unset loops
        def entry_byte(entry: int, offset: int) -> int:
            return 6 + 0x16 * entry + offset

        def changed(index: int, value: bytes) -> bytes:
            return self.file_data[:index] + value + self.file_data[index + len(value) :]

        cases = {
            "13 entries": changed(2, b"\x00\x00\x00\x0d")[: -0x16 - 4] + self.file_data[-4:],
            "a loop in a cue's place": changed(entry_byte(0, 20), b"\x03"),
            "a cue in a loop's place": changed(entry_byte(5, 20), b"\x01"),
            "a locked cue": changed(entry_byte(0, 21), b"\x01"),
            "an unset position that isn't 7f7f7f7f": changed(entry_byte(3, 1), b"\x00"),
            "an unexpected field5": changed(entry_byte(0, 10), b"\x01"),
            "trailing bytes": self.file_data + b"\x00",
        }
        for name, data in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                TrackCuesV1(data)


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
