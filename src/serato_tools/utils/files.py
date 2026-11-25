"""Copying files to a drive and clearing out the ones it no longer needs, for the USB export."""

import filecmp
import os
import shutil
import unicodedata

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
    # matches exactly, which made filecmp's quick check fail and read both files in full on every export
    if abs(src.st_mtime - dst.st_mtime) <= _COPY_MTIME_TOLERANCE:
        return False
    return not filecmp.cmp(src_path, dst_path, shallow=False)


def path_key(path: str) -> str:
    """`path` as a drive compares paths: ignoring case and Unicode normalization."""
    # a FAT32 or exFAT drive keeps a file's old name when it's overwritten under one differing in case, and macOS lists
    # an HFS+ drive's filenames decomposed (NFD), while the library's paths are usually composed
    return unicodedata.normalize("NFC", path).casefold()


def delete_other_files(dest_dir: str, keep: set[str]):
    """Deletes every file under `dest_dir` whose path, as `path_key` gives it, isn't in `keep`, and any folder left
    empty.

    A file or folder it can't delete is logged as an error and left, and the rest are still deleted.
    """
    for dirpath, _, filenames in os.walk(dest_dir, topdown=False):
        for filename in filenames:
            if path_key(path := os.path.join(dirpath, filename)) not in keep:
                logger.info(f"deleting {path}, which no exported crate holds")
                try:
                    os.remove(path)
                except OSError as e:
                    logger.error(f"couldn't delete {path}: {e}")
        if dirpath != dest_dir and not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
            except OSError as e:
                logger.error(f"couldn't delete {dirpath}: {e}")


def is_inside(path: str, folder: str) -> bool:
    """Whether `path` is inside `folder`, and not `folder` itself, once both are resolved to real paths."""
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    # commonpath raises for paths on different Windows drives
    try:
        return path != folder and os.path.commonpath([folder, path]) == folder
    except ValueError:
        return False
