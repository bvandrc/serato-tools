"""The fixtures every test module can ask for. Helpers that aren't fixtures are in test/helpers/."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path: Path) -> str:
    """A new temporary folder, removed after the test, as the str path serato_tools takes."""
    return str(tmp_path)


@pytest.fixture
def mp3(tmp_dir: str) -> str:
    """A copy of the test mp3, which has every Serato tag, in a new temporary folder."""
    # imported here so the tests that don't touch track tags don't need the track_tags extra (mutagen)
    from test.helpers.track_tags import copy_mp3

    return copy_mp3(tmp_dir)
