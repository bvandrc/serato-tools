import pytest

from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import NoWaveformError

from test.helpers.files import read_bytes
from test.helpers.track_tags import DATA_FILES, copy_mp3_without


def test_parse():
    tags = TrackWaveform(read_bytes(DATA_FILES.WAVEFORM))
    assert tags.data is not None
    assert b"".join(bytes(x) for x in tags.data) == read_bytes("test/data/track_waveform_parsed.bin")


def test_without_a_waveform_has_no_data(tmp_dir: str):
    path = copy_mp3_without(tmp_dir, TrackWaveform.GEOB_KEY)
    tags = TrackWaveform(path)
    assert tags.data is None, "loads, with nothing in it"
    with pytest.raises(NoWaveformError) as caught:
        tags.draw_image()
    assert caught.value.filename == path


def test_delete(mp3: str):
    tags = TrackWaveform(mp3)
    assert tags.delete() is True
    assert tags.data is None
    assert tags.save() is True
    assert TrackWaveform(mp3).data is None, "deleted from the file"
