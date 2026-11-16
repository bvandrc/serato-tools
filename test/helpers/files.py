"""Temporary folders, and reading files back."""

import tempfile
import unittest


def temp_dir(testcase: unittest.TestCase) -> str:
    """A new temporary folder, removed when `testcase`'s test ends."""
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return tmp.name


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
