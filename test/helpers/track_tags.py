"""The test mp3 and the GEOB tag fixtures, copies of the mp3 with tags removed, and reading its tags.

Needs the track_tags extra (mutagen), so only tests of track tags import it.
"""

import contextlib
import os
import shutil
import unittest
from typing import Iterator
from unittest import mock

from mutagen.mp3 import MP3

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import ID3File, SeratoGeobTag, del_geob, open_tagfile

from test.helpers.files import copy_into, read_bytes, temp_dir

TEST_MP3 = "test/data/test_mp3.mp3"


class DATA_FILES:
    """The fixtures holding the bytes of one tag each, as Serato wrote them."""

    CUES_V2 = "test/data/track_cues_v2.bin"
    CUES_V1 = "test/data/track_cues_v1.bin"
    BEATGRID = "test/data/track_beatgrid.bin"
    AUTOTAGS = "test/data/track_autotags.bin"
    WAVEFORM = "test/data/track_waveform.bin"


# each GEOB tag class, with the fixture of its tag's bytes
GEOB_DATA: dict[type[SeratoGeobTag], str] = {
    TrackCuesV2: DATA_FILES.CUES_V2,
    TrackCuesV1: DATA_FILES.CUES_V1,
    TrackBeatgrid: DATA_FILES.BEATGRID,
    TrackAutotags: DATA_FILES.AUTOTAGS,
    TrackWaveform: DATA_FILES.WAVEFORM,
}

# the test mp3's first cue, 42 ms before its nearest beat
FIRST_CUE_POSITION = 45104
# where the test mp3's cues end up once snapped to its beats with a 1/16 tolerance
SNAPPED_CUE_POSITIONS = [45146, 67472, 112125, 134449, 156776, 201428]


def cues_v2_data(variant: str = "") -> bytes:
    """The bytes of the Serato Markers2 tag in test/data/track_cues_v2{variant}.bin, such as "_analyzed"."""
    return read_bytes(f"test/data/track_cues_v2{variant}.bin")


def copy_mp3(folder: str, name: str = "test.mp3") -> str:
    """A copy of the test mp3, which has every Serato tag, as `name` in `folder`."""
    return copy_into(folder, TEST_MP3, name)


def copy_mp3_without_cues(folder: str, name: str = "no_cues.mp3") -> str:
    """A copy of the test mp3 without its Serato Markers2 and Serato Markers_ tags, as `name` in `folder`."""
    return copy_mp3_without(folder, TrackCuesV2.GEOB_KEY, TrackCuesV1.GEOB_KEY, name=name)


def copy_mp3_without_id3(folder: str, name: str = "no_id3.mp3") -> str:
    """A copy of the test mp3 without an ID3 tag, as `name` in `folder`."""
    path = copy_mp3(folder, name)
    MP3(path).delete()
    return path


def copy_mp3_with_empty_id3(folder: str, name: str = "empty.mp3") -> str:
    """A copy of the test mp3 whose ID3 tag has no frames, as for one whose tags were cleared, as `name` in `folder`."""
    path = copy_mp3_without_id3(folder, name)
    mp3 = MP3(path)
    mp3.add_tags()
    mp3.save()
    return path


def copy_mp3_without(folder: str, *geob_keys: str, name: str = "stripped.mp3") -> str:
    """A copy of the test mp3 without its `geob_keys` GEOB tags, and with every other, as `name` in `folder`."""
    path = copy_mp3(folder, name)
    tagfile = open_tagfile(path)
    for geob_key in geob_keys:
        del_geob(tagfile, geob_key)
    tagfile.save()
    return path


def has_tags_v1(path: str) -> bool:
    """Whether the audio file at `path` has a Serato Markers_ tag."""
    return f"GEOB:{TrackCuesV1.GEOB_KEY}" in open_tagfile(path)


def cue_positions(tags: TrackCuesV2) -> list[int]:
    """The position of each of `tags`' cues, in order."""
    return [cue.position for cue in tags._from_entries().cues]  # pylint: disable=protected-access


@contextlib.contextmanager
def tagfile_saves(tagfile: ID3File | None) -> Iterator[mock.MagicMock]:
    """Counts the saves of `tagfile` during the block, in the mock it gives, while still saving it."""
    assert tagfile is not None, "a tag read from bytes has no file to save"
    with mock.patch.object(tagfile, "save", wraps=tagfile.save) as save:
        yield save


# for the modules still on unittest.TestCase; the pytest ones take the mp3 fixture


def temp_mp3(testcase: unittest.TestCase, name: str = "test.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3, which has every Serato tag, as `name` in `folder` (a new temporary folder by default)."""
    path = os.path.join(folder or temp_dir(testcase), name)
    shutil.copy(TEST_MP3, path)
    return path


def untagged_mp3(testcase: unittest.TestCase, name: str = "untagged.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3 with no Serato Markers2 or Serato Markers_ tag, as for a track Serato hasn't analyzed."""
    return copy_mp3_without_cues(folder or temp_dir(testcase), name)
