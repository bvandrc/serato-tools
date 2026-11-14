"""Fixtures shared by the test modules."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from typing import TYPE_CHECKING, Iterator
from unittest import mock

if TYPE_CHECKING:
    from serato_tools.track_cues_v2 import TrackCuesV2

TEST_MP3 = "test/data/test_mp3.mp3"
TEST_DATABASE = "test/data/database_v2_test.bin"
TEST_CRATE = "test/data/TestCrate.crate"
TEST_SMART_CRATE = "test/data/TestSmartCrate.scrate"

# where the test mp3's cues end up once snapped to its beats with a 1/16 tolerance
SNAPPED_CUE_POSITIONS = [45146, 67472, 112125, 134449, 156776, 201428]


def temp_dir(testcase: unittest.TestCase) -> str:
    """A new temporary folder, removed when `testcase`'s test ends."""
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return tmp.name


def temp_copy(testcase: unittest.TestCase, src: str, name: str | None = None, folder: str | None = None) -> str:
    """A copy of `src` as `name` (its own name by default) in `folder` (a new temporary folder by default)."""
    path = os.path.join(folder or temp_dir(testcase), name or os.path.basename(src))
    shutil.copy(src, path)
    return path


def temp_mp3(testcase: unittest.TestCase, name: str = "test.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3, which has every Serato tag, as `name` in `folder` (a new temporary folder by default)."""
    return temp_copy(testcase, TEST_MP3, name, folder)


def untagged_mp3(testcase: unittest.TestCase, name: str = "untagged.mp3", folder: str | None = None) -> str:
    """A copy of the test mp3 with no Serato Markers2 tag, as for a track Serato hasn't analyzed."""
    # imported here so the tests that don't touch track tags don't need the track_tags extra (mutagen)
    from serato_tools.track_cues_v2 import TrackCuesV2  # pylint: disable=import-outside-toplevel

    path = temp_mp3(testcase, name, folder)
    tags = TrackCuesV2(path)
    tags.delete()
    tags.save()
    return path


def bin_file_writes(testcase: unittest.TestCase) -> list[str]:
    """The name of each Serato bin file (database or crate) written from now until `testcase`'s test ends, in order.

    The returned list fills in as files are written.
    """
    written: list[str] = []

    def record_write(file, *args, **kwargs):
        if "w" in (args[0] if args else kwargs.get("mode", "r")):
            written.append(os.path.basename(file))
        return open(file, *args, **kwargs)  # pylint: disable=unspecified-encoding

    # every way of saving a bin file opens it for writing in its module
    patcher = mock.patch("serato_tools.utils.bin_file_base.open", side_effect=record_write, create=True)
    patcher.start()
    testcase.addCleanup(patcher.stop)
    return written


def mp3_without(testcase: unittest.TestCase, geob_key: str) -> str:
    """A copy of the test mp3 without its `geob_key` GEOB tag, and with every other."""
    from serato_tools.utils.track_tags import del_geob, open_tagfile  # pylint: disable=import-outside-toplevel

    path = temp_mp3(testcase)
    tagfile = open_tagfile(path)
    del_geob(tagfile, geob_key)
    tagfile.save()
    return path


def has_tags_v1(path: str) -> bool:
    """Whether the audio file at `path` has a Serato Markers_ tag."""
    from serato_tools.track_cues_v1 import TrackCuesV1  # pylint: disable=import-outside-toplevel
    from serato_tools.utils.track_tags import open_tagfile  # pylint: disable=import-outside-toplevel

    return f"GEOB:{TrackCuesV1.GEOB_KEY}" in open_tagfile(path)


def cue_positions(tags: "TrackCuesV2") -> list[int]:
    """The position of each of `tags`' cues, in order."""
    return [cue.position for cue in tags._from_entries().cues]  # pylint: disable=protected-access


@contextlib.contextmanager
def cli_args(*argv: str) -> Iterator[io.StringIO]:
    """Runs the block with `argv` as the command line, collecting what it prints to stdout in the given StringIO.

    What it prints to stderr, such as argparse's errors, is dropped.
    """
    stdout = io.StringIO()
    with (
        mock.patch("sys.argv", list(argv)),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        yield stdout


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str, encoding: str = "utf-8") -> str:
    with open(path, "r", encoding=encoding) as f:
        return f.read()
