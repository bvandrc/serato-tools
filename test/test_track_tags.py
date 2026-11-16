import importlib
import os
import pkgutil
import runpy
from collections.abc import Iterator

import pytest
from mutagen.mp3 import MP3

import serato_tools
from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain
from serato_tools.track_tagdump import get_serato_tagdata
from serato_tools.track_text_frames import TrackTextFrames
from serato_tools.utils.track_tags import ID3FileTag, get_geob

from test.helpers.cli import cli_args
from test.helpers.files import read_bytes
from test.helpers.track_tags import GEOB_DATA, TEST_MP3, copy_mp3_with_empty_id3, copy_mp3_without_id3, tagfile_saves

GEOB_TAG_CLASSES = tuple(GEOB_DATA)
# all but TrackWaveform, which is read-only
WRITABLE_GEOB_TAG_CLASSES = (TrackCuesV2, TrackCuesV1, TrackBeatgrid, TrackAutotags)
TAG_CLASSES = (*GEOB_TAG_CLASSES, TrackGain, TrackTextFrames)


@pytest.mark.parametrize("tag_class", GEOB_TAG_CLASSES, ids=lambda cls: cls.__name__)
def test_delete_then_save_persists_deletion(mp3: str, tag_class):
    assert get_geob(MP3(mp3), tag_class.GEOB_KEY) is not None, "fixture has the tag"
    tags = tag_class(mp3)
    tags.delete()
    assert tags.save() is True, "returns that it wrote"
    assert get_geob(MP3(mp3), tag_class.GEOB_KEY) is None, "deletion saved"


@pytest.mark.parametrize("tag_class", TAG_CLASSES, ids=lambda cls: cls.__name__)
def test_save_writes_only_a_changed_tag_unless_forced(mp3: str, tag_class):
    tags = tag_class(mp3)
    with tagfile_saves(tags.tagfile) as saves:
        assert tags.save() is False, "unchanged"
        saves.assert_not_called()
        assert tags.save(force=True) is True, "forced"
        saves.assert_called_once()


def test_every_tag_class_is_tested():
    # ID3FileTag isn't an ABC: a subclass that doesn't implement has_changed or _write_to_tagfile only raises
    # NotImplementedError when they're called, as the test above does for each of TAG_CLASSES
    for module in pkgutil.iter_modules(serato_tools.__path__):
        importlib.import_module(f"serato_tools.{module.name}")

    def subclasses(cls: type) -> Iterator[type]:
        for subclass in cls.__subclasses__():
            yield subclass
            yield from subclasses(subclass)

    # the concrete ones: nothing subclasses them, as SeratoGeobTag is subclassed
    tag_classes = {cls for cls in subclasses(ID3FileTag) if not cls.__subclasses__()}
    assert tag_classes == set(TAG_CLASSES), "a tag class missing from TAG_CLASSES skips the tests run over it"


@pytest.mark.parametrize("tag_class", GEOB_TAG_CLASSES, ids=lambda cls: cls.__name__)
def test_untested_version_raises_at_construction(tag_class):
    with pytest.raises(ValueError, match="Untested Serato tag version"):
        tag_class(bytes([0x99, 0x99]))


@pytest.mark.parametrize("tag_class", GEOB_TAG_CLASSES, ids=lambda cls: cls.__name__)
def test_tagdump_reads_each_geob(tag_class):
    dumped = dict(get_serato_tagdata(MP3(TEST_MP3)))
    assert dumped[tag_class.GEOB_KEY] == tag_class(TEST_MP3)._raw_data


def test_unsupported_file_type_raises():
    with pytest.raises(ValueError, match="unsupported file type"):
        ID3FileTag("some_file.flac")


def test_geob_tag_has_changed(mp3: str):
    tags = TrackAutotags(mp3)
    assert not tags.has_changed, "as read"
    tags.set(bpm=128)
    assert tags.has_changed, "set"
    tags.save()
    assert not tags.has_changed, "saved"
    tags.delete()
    assert tags.has_changed, "deleted"

    tags = TrackAutotags(read_bytes(GEOB_DATA[TrackAutotags]))
    assert not tags.has_changed, "as given in bytes"
    tags.set(bpm=128)
    assert tags.has_changed, "differs from the bytes given"


# TrackCuesV2 has its own save()
@pytest.mark.parametrize("tag_class", [TrackCuesV2, TrackAutotags], ids=lambda cls: cls.__name__)
def test_saving_a_change_to_a_tag_read_from_bytes_raises(tag_class):
    tags = tag_class(read_bytes(GEOB_DATA[tag_class]))
    tags.delete()
    with pytest.raises(ValueError, match="read from bytes"):
        tags.save()


@pytest.mark.parametrize("tag_class", WRITABLE_GEOB_TAG_CLASSES, ids=lambda cls: cls.__name__)
def test_serialize_reproduces_the_bytes_parsed(tag_class):
    data = read_bytes(GEOB_DATA[tag_class])
    tags = tag_class(data)
    tags._raw_data = None  # so only _serialize can put the bytes back
    tags._serialize()
    assert tags._raw_data == data


# a file whose ID3 tags have no frames is falsy to mutagen, which once read as "no file"
@pytest.mark.parametrize("tag_class", WRITABLE_GEOB_TAG_CLASSES, ids=lambda cls: cls.__name__)
def test_a_tag_in_a_file_with_no_frames_has_the_file(tmp_dir: str, tag_class):
    path = copy_mp3_with_empty_id3(tmp_dir)
    tags = tag_class(path)
    assert tags.tagfile is not None
    assert tags.filename == path


@pytest.mark.parametrize(
    "make_file",
    [
        pytest.param(copy_mp3_without_id3, id="no ID3 tag"),
        pytest.param(copy_mp3_with_empty_id3, id="an ID3 tag with no frames"),
    ],
)
def test_tagdump_of_a_file_without_tags_says_so(tmp_dir: str, make_file):
    with pytest.raises(ValueError, match="no tags"):
        list(get_serato_tagdata(MP3(make_file(tmp_dir))))


def _not_audio_file(folder: str) -> str:
    path = os.path.join(folder, "notes.txt")
    with open(path, "wb") as f:
        f.write(b"not audio")
    return path


# this module imports serato_tools.track_tagdump, which run_module warns of, though it runs a fresh copy
@pytest.mark.filterwarnings("ignore:'serato_tools.track_tagdump' found in sys.modules:RuntimeWarning")
@pytest.mark.parametrize(
    "make_file, message",
    [
        pytest.param(copy_mp3_without_id3, "file has no tags", id="no ID3 tag"),
        pytest.param(copy_mp3_with_empty_id3, "file has no tags", id="an ID3 tag with no frames"),
        pytest.param(_not_audio_file, "not an audio file mutagen can read", id="not audio"),
    ],
)
def test_tagdump_cli_says_why_it_cant_dump_a_file(tmp_dir: str, make_file, message: str):
    path = make_file(tmp_dir)
    # serato_tagdump isn't a console script, so it runs as python -m runs it
    with cli_args("serato_tagdump", path), pytest.raises(SystemExit) as caught:
        runpy.run_module("serato_tools.track_tagdump", run_name="__main__")
    assert caught.value.code == f"{message}: {path}"
