"""The test mp3, and copies of it.

Needs the track_tags extra (mutagen), so only tests of track tags import it.
"""

import os
import shutil
import unittest

from serato_tools.track_cues_v2 import TrackCuesV2

from test.helpers.files import temp_dir

TEST_MP3 = "test/data/test_mp3.mp3"


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
