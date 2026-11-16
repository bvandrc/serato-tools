"""Temporary folders, copies of fixtures, and reading files back."""

import os
import shutil
import tempfile
import unittest


def temp_dir(testcase: unittest.TestCase) -> str:
    """A new temporary folder, removed when `testcase`'s test ends."""
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return tmp.name


def copy_into(folder: str, src: str, name: str | None = None) -> str:
    """A copy of `src` in `folder`, as `name` (its own name by default)."""
    path = os.path.join(folder, name or os.path.basename(src))
    shutil.copy(src, path)
    return path


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
