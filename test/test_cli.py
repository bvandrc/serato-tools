# pylint: disable=protected-access

import pytest

from serato_tools.track_autotags import TrackAutotags
from serato_tools.utils.cli import open_tag_file_or_data, save_tag_file_or_data

from test.helpers.files import copy_into, read_bytes
from test.helpers.track_tags import DATA_FILES, GEOB_DATA, TEST_MP3


@pytest.mark.parametrize("tag_class", GEOB_DATA, ids=lambda cls: cls.__name__)
def test_open_tag_file_or_data_reads_an_audio_file_or_the_tags_own_bytes(tag_class):
    data_file = GEOB_DATA[tag_class]
    tags = open_tag_file_or_data(tag_class, data_file)
    assert tags.tagfile is None, "read as bytes"
    assert tags._raw_data == read_bytes(data_file)
    assert open_tag_file_or_data(tag_class, TEST_MP3).tagfile is not None, "read as audio"


def test_save_tag_file_or_data_writes_a_changed_data_file_back(tmp_dir: str):
    data_file = copy_into(tmp_dir, DATA_FILES.AUTOTAGS, "Serato Autotags.octet-stream")
    tags = open_tag_file_or_data(TrackAutotags, data_file)
    assert save_tag_file_or_data(tags, data_file) is False, "unchanged"
    tags.set(bpm=128)
    assert save_tag_file_or_data(tags, data_file) is True
    assert TrackAutotags(read_bytes(data_file)).bpm == 128


def test_save_tag_file_or_data_saves_an_audio_file(mp3: str):
    tags = open_tag_file_or_data(TrackAutotags, mp3)
    tags.set(bpm=128)
    assert save_tag_file_or_data(tags, mp3) is True
    assert TrackAutotags(mp3).bpm == 128
