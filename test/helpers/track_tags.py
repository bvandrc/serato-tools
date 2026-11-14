"""The test mp3, copies of it with tags removed, and reading its tags.

Needs the track_tags extra (mutagen), so only tests of track tags import it.
"""

import unittest

from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.utils.track_tags import del_geob, open_tagfile

from test.helpers.files import copy_into, temp_copy

TEST_MP3 = "test/data/test_mp3.mp3"

# where the test mp3's cues end up once snapped to its beats with a 1/16 tolerance
SNAPPED_CUE_POSITIONS = [45146, 67472, 112125, 134449, 156776, 201428]


def temp_mp3(testcase: unittest.TestCase, name: str = "test.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3, which has every Serato tag, as `name` in `folder` (a new temporary folder by default)."""
    return temp_copy(testcase, TEST_MP3, name, folder)


def untagged_mp3(testcase: unittest.TestCase, name: str = "untagged.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3 with no Serato Markers2 tag, as for a track Serato hasn't analyzed."""
    path = temp_mp3(testcase, name, folder)
    tags = TrackCuesV2(path)
    tags.delete()
    tags.save()
    return path


def mp3_without(testcase: unittest.TestCase, geob_key: str) -> str:
    """A copy of the test mp3 without its `geob_key` GEOB tag, and with every other."""
    path = temp_mp3(testcase)
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


def copy_mp3(folder: str, name: str = "test.mp3") -> str:
    """A copy of the test mp3, which has every Serato tag, as `name` in `folder`."""
    return copy_into(folder, TEST_MP3, name)


def copy_untagged_mp3(folder: str, name: str = "untagged.mp3") -> str:
    """A copy of the test mp3 with no Serato Markers2 tag, as for a track Serato hasn't analyzed, as `name` in `folder`."""
    path = copy_mp3(folder, name)
    tags = TrackCuesV2(path)
    tags.delete()
    tags.save()
    return path


def copy_mp3_without(folder: str, geob_key: str, name: str = "test.mp3") -> str:
    """A copy of the test mp3 without its `geob_key` GEOB tag, and with every other, as `name` in `folder`."""
    path = copy_mp3(folder, name)
    tagfile = open_tagfile(path)
    del_geob(tagfile, geob_key)
    tagfile.save()
    return path
