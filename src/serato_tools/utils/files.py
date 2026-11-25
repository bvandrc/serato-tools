"""Copying files to a drive only when they've changed, and finding and clearing out the ones a folder no longer needs.

Internal to the package, not part of its API: these names can change in any release, as `_`-prefixed ones can.
"""

import filecmp
import os
import shutil
import unicodedata
from collections.abc import Iterable

from serato_tools.utils import logger

# how far apart, in seconds, a file's and its copy's modification times can be: FAT32 stores them to 2 seconds
_COPY_MTIME_TOLERANCE = 2


def copy_if_changed(src_path: str, dst_path: str) -> bool:
    """Copies `src_path` to `dst_path`, unless it's there unchanged, and returns False if `src_path` doesn't exist."""
    if not os.path.exists(src_path):
        return False
    if not os.path.exists(dst_path) or _is_changed_copy(src_path, dst_path):
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        logger.info(f"copying {src_path}")
        shutil.copy2(src_path, dst_path)
    return True


def _is_changed_copy(src_path: str, dst_path: str) -> bool:
    """Whether the file at `dst_path` differs from `src_path`, so has to be copied again.

    Reads neither file when they're the same size and were modified within 2 seconds of each other, as a copy made
    since `src_path` last changed is; otherwise compares their contents.
    """
    src, dst = os.stat(src_path), os.stat(dst_path)
    if src.st_size != dst.st_size:
        return True
    # copy2 gives the copy src's modification time, but FAT32 stores it to 2 seconds (exFAT to 10 ms), so it rarely
    # matches exactly, which made filecmp's quick check fail and read both files in full on every copy
    if abs(src.st_mtime - dst.st_mtime) <= _COPY_MTIME_TOLERANCE:
        return False
    return not filecmp.cmp(src_path, dst_path, shallow=False)


def _path_key(path: str) -> str:
    """`path` as a drive compares paths: ignoring case and Unicode normalization."""
    # a FAT32 or exFAT drive keeps a file's old name when it's overwritten under one differing in case, and macOS lists
    # an HFS+ drive's filenames decomposed (NFD), while paths from elsewhere are usually composed
    return unicodedata.normalize("NFC", path).casefold()


def files_not_in(folder: str, keep: Iterable[str]) -> list[str]:
    """The paths of the files under `folder` that aren't in `keep`.

    Paths are compared as a drive compares them, ignoring case and Unicode normalization, so a file in `keep` under a
    name differing only in those isn't listed.
    """
    keep_keys = {_path_key(path) for path in keep}
    return [
        path
        for dirpath, _, filenames in os.walk(folder)
        for filename in filenames
        if _path_key(path := os.path.join(dirpath, filename)) not in keep_keys
    ]


def remove_empty_folders(folder: str):
    """Removes every empty folder under `folder`, and any left empty by that, but not `folder` itself.

    A folder it can't remove is logged as an error and left, and the rest are still removed.
    """
    # bottom-up, so a folder holding only empty folders is empty by the time it's reached
    for dirpath, _, _ in os.walk(folder, topdown=False):
        if dirpath != folder and not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
            except OSError as e:
                logger.error(f"couldn't delete {dirpath}: {e}")


def is_inside_dir(path: str, folder: str) -> bool:
    """Whether `path` is inside `folder`, and not `folder` itself, once both are resolved to real paths."""
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    # commonpath raises for paths on different Windows drives
    try:
        return path != folder and os.path.commonpath([folder, path]) == folder
    except ValueError:
        return False
