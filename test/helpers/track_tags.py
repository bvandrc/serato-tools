"""The test mp3 and the GEOB tag fixtures, copies of the mp3 with tags removed, and reading its tags.

Needs the track_tags extra (mutagen), so only tests of track tags import it.
"""

import contextlib
import os
import struct
from typing import Iterator
from unittest import mock

from mutagen.aiff import AIFF
from mutagen.mp3 import MP3

from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.utils.track_tags import ID3File, del_geob, open_tagfile

from test.helpers.files import copy_into, read_bytes

TEST_MP3 = "test/data/test_mp3.mp3"

# the bytes of one tag each, as Serato wrote them
CUES_V2_DATA = "test/data/track_cues_v2.bin"
CUES_V1_DATA = "test/data/track_cues_v1.bin"
BEATGRID_DATA = "test/data/track_beatgrid.bin"
AUTOTAGS_DATA = "test/data/track_autotags.bin"
WAVEFORM_DATA = "test/data/track_waveform.bin"

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
    path = copy_mp3(folder, name)
    tags = TrackCuesV2(path)
    tags.delete()
    tags.save()  # which deletes Serato Markers_ too
    return path


def aiff_with_the_mp3s_tags(folder: str, name: str = "test.aif") -> str:
    """A short silent AIFF, as `name` in `folder`, with every ID3 frame the test mp3 has."""
    frames = 100
    # 1 channel, `frames` sample frames, 16 bits, at 44100 Hz (an 80-bit float)
    comm = struct.pack(">hIh", 1, frames, 16) + bytes.fromhex("400eac44000000000000")
    ssnd = struct.pack(">II", 0, 0) + b"\x00" * (frames * 2)
    body = b"AIFF" + b"COMM" + struct.pack(">I", len(comm)) + comm + b"SSND" + struct.pack(">I", len(ssnd)) + ssnd
    path = os.path.join(folder, name)
    with open(path, "wb") as f:
        f.write(b"FORM" + struct.pack(">I", len(body)) + body)

    aiff = AIFF(path)
    aiff.add_tags()
    mp3_tags = MP3(TEST_MP3).tags
    assert aiff.tags is not None and mp3_tags is not None
    for frame in mp3_tags.values():
        aiff.tags.add(frame)
    aiff.save()
    return path


def copy_mp3_without(folder: str, geob_key: str, name: str = "test.mp3") -> str:
    """A copy of the test mp3 without its `geob_key` GEOB tag, and with every other, as `name` in `folder`."""
    path = copy_mp3(folder, name)
    tagfile = open_tagfile(path)
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
