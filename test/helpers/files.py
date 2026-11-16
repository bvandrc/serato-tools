"""Temporary folders, copies of fixtures, mock files, and reading files back."""

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


# a folder's contents: file names and dicts of subfolders, or just a dict of subfolders, each name to its own contents
type MockTree = dict[str, MockTree] | list[str | dict[str, MockTree]]


def mock_files(tree: dict[str, MockTree]) -> list[str]:
    """Creates the folders and empty files in `tree`, and returns the files' paths, in order.

    `tree` maps each folder's path to its contents: `{music: ["A.mp3", ".DS_Store", {"Subfolder": []}]}` is a folder
    at `music` holding two files and an empty folder. The folders are created if they don't exist.
    """
    paths: list[str] = []
    for folder, contents in tree.items():
        if isinstance(contents, str):
            # a bare string would otherwise be read as a list of names, one file per character
            raise TypeError(f"{folder!r} holds {contents!r}: a folder's contents are a list or dict, not a name")
        os.makedirs(folder, exist_ok=True)
        for entry in [contents] if isinstance(contents, dict) else contents:
            if isinstance(entry, dict):
                paths += mock_files({os.path.join(folder, name): subtree for name, subtree in entry.items()})
            else:
                path = os.path.join(folder, entry)
                open(path, "wb").close()  # pylint: disable=consider-using-with
                paths.append(path)
    return paths


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
