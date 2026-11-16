"""The test mp3 and the GEOB tag fixtures, and copies of the mp3.

Needs the track_tags extra (mutagen), so only tests of track tags import it.
"""

import os
import shutil
import unittest

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import SeratoGeobTag

from test.helpers.files import copy_into, temp_dir

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


def copy_mp3(folder: str, name: str = "test.mp3") -> str:
    """A copy of the test mp3, which has every Serato tag, as `name` in `folder`."""
    return copy_into(folder, TEST_MP3, name)


# for the modules still on unittest.TestCase; the pytest ones take the mp3 fixture


def temp_mp3(testcase: unittest.TestCase, name: str = "test.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3, which has every Serato tag, as `name` in `folder` (a new temporary folder by default)."""
    path = os.path.join(folder or temp_dir(testcase), name)
    shutil.copy(TEST_MP3, path)
    return path


def untagged_mp3(testcase: unittest.TestCase, name: str = "untagged.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3 with no Serato Markers2 tag, as for a track Serato hasn't analyzed."""
    path = temp_mp3(testcase, name, folder)
    tags = TrackCuesV2(path)
    tags.delete()
    tags.save()
    return path
