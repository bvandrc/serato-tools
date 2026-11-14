import pytest

from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import NoWaveformError

from test.helpers.files import read_bytes
from test.helpers.track_tags import copy_mp3_without

WAVEFORM = "test/data/track_waveform.bin"


def test_parse():
    tags = TrackWaveform(read_bytes(WAVEFORM))
    assert b"".join(bytes(x) for x in tags.data) == read_bytes("test/data/track_waveform_parsed.bin")


def test_without_a_waveform_raises(tmp_dir: str):
    path = copy_mp3_without(tmp_dir, TrackWaveform.GEOB_KEY)
    with pytest.raises(NoWaveformError) as caught:
        TrackWaveform(path)
    assert caught.value.filename == path


def test_a_partial_row_raises():
    with pytest.raises(ValueError, match="row of 5 bytes"):
        TrackWaveform(read_bytes(WAVEFORM) + b"\x00" * 5)
