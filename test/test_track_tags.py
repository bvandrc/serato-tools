# pylint: disable=protected-access
from unittest import mock

import pytest
from mutagen.mp3 import MP3

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain
from serato_tools.track_tagdump import get_serato_tagdata
from serato_tools.track_text_frames import TrackTextFrames
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import ID3FileTag, get_geob, open_tag_file_or_data

from test.helpers.files import read_bytes
from test.helpers.track_tags import TEST_MP3

# each GEOB tag class, with a fixture of its tag's bytes
GEOB_FIXTURES = {
    TrackCuesV2: "test/data/track_cues_v2.bin",
    TrackCuesV1: "test/data/track_cues_v1.bin",
    TrackBeatgrid: "test/data/track_beatgrid.bin",
    TrackAutotags: "test/data/track_autotags.bin",
    TrackWaveform: "test/data/track_waveform.bin",
}
GEOB_TAG_CLASSES = tuple(GEOB_FIXTURES)
TAG_CLASSES = (*GEOB_TAG_CLASSES, TrackGain, TrackTextFrames)


def class_name(tag_class: type) -> str:
    return tag_class.__name__


@pytest.mark.parametrize("tag_class", GEOB_TAG_CLASSES, ids=class_name)
def test_delete_then_save_persists_deletion(mp3: str, tag_class):
    assert get_geob(MP3(mp3), tag_class.GEOB_KEY) is not None, "fixture has the tag"
    tags = tag_class(mp3)
    tags.delete()
    assert tags.save(), "returns that it wrote"
    assert get_geob(MP3(mp3), tag_class.GEOB_KEY) is None, "deletion saved"


@pytest.mark.parametrize("tag_class", TAG_CLASSES, ids=class_name)
def test_save_writes_only_a_changed_tag_unless_forced(mp3: str, tag_class):
    tags = tag_class(mp3)
    assert tags.tagfile is not None
    with mock.patch.object(tags.tagfile, "save") as save:
        assert tags.save() is False, "unchanged"
        save.assert_not_called()
        assert tags.save(force=True) is True, "forced"
        save.assert_called_once()


@pytest.mark.parametrize("tag_class", GEOB_TAG_CLASSES, ids=class_name)
def test_untested_version_raises_at_construction(tag_class):
    with pytest.raises(ValueError, match="Untested Serato tag version"):
        tag_class(bytes([0x99, 0x99]))


def test_tagdump_reads_each_geob():
    dumped = dict(get_serato_tagdata(MP3(TEST_MP3)))
    assert dumped["Serato Autotags"] == TrackAutotags(TEST_MP3)._raw_data
    assert dumped["Serato Markers2"] == TrackCuesV2(TEST_MP3)._raw_data


def test_unsupported_file_type_raises():
    with pytest.raises(ValueError):
        ID3FileTag("some_file.flac")


def test_has_changed(mp3: str):
    tags = TrackAutotags(mp3)
    assert not tags.has_changed, "as read"
    tags.set(bpm=128)
    assert tags.has_changed, "set"
    tags.save()
    assert not tags.has_changed, "saved"
    tags.delete()
    assert tags.has_changed, "deleted"

    tags = TrackAutotags(read_bytes(GEOB_FIXTURES[TrackAutotags]))
    assert not tags.has_changed, "as given in bytes"
    tags.set(bpm=128)
    assert tags.has_changed, "differs from the bytes given"


@pytest.mark.parametrize("tag_class", (TrackCuesV2, TrackAutotags), ids=class_name)  # TrackCuesV2 has its own save()
def test_saving_a_change_to_a_tag_read_from_bytes_raises(tag_class):
    tags = tag_class(read_bytes(GEOB_FIXTURES[tag_class]))
    tags.delete()
    with pytest.raises(ValueError, match="read from bytes"):
        tags.save()


# TrackWaveform is read-only
@pytest.mark.parametrize("tag_class", (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags), ids=class_name)
def test_serialize_reproduces_the_bytes_parsed(tag_class):
    data = read_bytes(GEOB_FIXTURES[tag_class])
    tags = tag_class(data)
    tags._serialize()
    assert tags._raw_data == data


@pytest.mark.parametrize("tag_class", GEOB_TAG_CLASSES, ids=class_name)
def test_open_tag_file_or_data_reads_an_audio_file_or_the_tags_own_bytes(tag_class):
    data_file = GEOB_FIXTURES[tag_class]
    tags = open_tag_file_or_data(tag_class, data_file)
    assert tags.tagfile is None, "read as bytes"
    assert tags._raw_data == read_bytes(data_file)
    assert open_tag_file_or_data(tag_class, TEST_MP3).tagfile is not None, "read as audio"
