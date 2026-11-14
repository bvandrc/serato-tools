"""Copies of fixtures, and reading files back."""

import os
import shutil


def copy_into(folder: str, src: str, name: str | None = None) -> str:
    """A copy of `src` in `folder`, as `name` (its own name by default)."""
    path = os.path.join(folder, name or os.path.basename(src))
    shutil.copy(src, path)
    return path


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str, encoding: str = "utf-8") -> str:
    with open(path, "r", encoding=encoding) as f:
        return f.read()
