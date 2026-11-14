"""Temporary copies of fixtures, and reading files back."""

import os
import shutil
import tempfile
import unittest


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


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str, encoding: str = "utf-8") -> str:
    with open(path, "r", encoding=encoding) as f:
        return f.read()
