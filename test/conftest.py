"""The fixtures every test module can ask for. Helpers that aren't fixtures are in test/helpers/."""

import os
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


@pytest.fixture
def untagged_mp3(tmp_dir: str) -> str:
    """A copy of the test mp3 with no Serato Markers2 tag, as for a track Serato hasn't analyzed."""
    from test.helpers.track_tags import copy_untagged_mp3

    return copy_untagged_mp3(tmp_dir)


@pytest.fixture
def bin_file_writes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The name of each Serato bin file (database or crate) the test writes, in order, filled in as they're written."""
    written: list[str] = []

    def record_write(file, *args, **kwargs):
        if "w" in (args[0] if args else kwargs.get("mode", "r")):
            written.append(os.path.basename(file))
        return open(file, *args, **kwargs)  # pylint: disable=unspecified-encoding

    # every way of saving a bin file opens it for writing in its module, which has no open of its own to replace
    monkeypatch.setattr("serato_tools.utils.bin_file_base.open", record_write, raising=False)
    return written
