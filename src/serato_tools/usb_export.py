"""Exports crates to a USB drive for Serato.

The crates' tracks are copied to one folder on the drive, with a library that points there.

Also the `serato_usb_export` CLI.
"""

import filecmp
import fnmatch
import os
import platform
import re
import shutil
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils import (
    SERATO_DIR as LOCAL_SERATO_DIR,
    SERATO_DIR_NAME,
    logger,
)
from serato_tools.utils.bin_file_base import SeratoBinFile

# TODO: put in folders if there are different locations locally for the same basename

# the extension of the file Serato keeps a track's stems in, beside the track
STEMS_EXTENSION = ".serato-stems"


def _uniq_by_basename(paths: list[str]):
    """`paths` without any whose filename an earlier one already has."""
    basenames: set[str] = set()
    return_paths: list[str] = []
    for path in paths:
        if (basename := os.path.basename(path)) not in basenames:
            basenames.add(basename)
            return_paths.append(path)
    return return_paths


def copy_crates_to_usb(
    crate_files: Iterable[str],
    dest_drive_dir: str,
    dest_tracks_dir: str,
    root_crate: Optional[str] = None,
    source_serato_dir: str = LOCAL_SERATO_DIR,
):
    """Copies the crates in `crate_files`, and their tracks, to the drive at `dest_drive_dir`.

    - Every track goes in `dest_tracks_dir` on the drive, a path relative to it or absolute, and only the first of tracks that share a filename is kept.
    - The drive's `_Serato_` folder is replaced by one holding these crates and a database of just their tracks, all
      pointed at the new paths. Smart crates become regular crates of the tracks they hold, keeping their sort and
      columns but not their rules, since Serato can't use a smart crate on a drive.
    - A track whose file is already on the drive, unchanged, isn't copied again. Its stems file is copied too.
    - Given `root_crate`, every crate goes inside a crate of that name.
    - `source_serato_dir` is the `_Serato_` folder of the library the crates belong to, which is the home library
      unless exporting from a library on another drive. Its database, crate order, and stems crate are copied too.
    """
    if not os.path.isdir(dest_drive_dir):
        raise FileNotFoundError(f"destination drive directory does not exist: {dest_drive_dir}")

    dest_serato_dir = os.path.join(dest_drive_dir, SERATO_DIR_NAME)
    # TODO: merge with existing, instead of replacing
    if os.path.isdir(dest_serato_dir):
        shutil.rmtree(dest_serato_dir)

    dest_crate_dir = os.path.join(dest_serato_dir, Crate.DIR)
    os.makedirs(dest_crate_dir, exist_ok=True)
    dest_tracks_path = os.path.join(dest_drive_dir, dest_tracks_dir)
    # as the drive's library stores it, relative to the drive, which `dest_tracks_dir` may already be absolute on
    dest_tracks_dir = Crate.get_relative_path(dest_tracks_path, dest_drive_dir)
    track_paths: list[str] = []
    for crate_file in crate_files:
        if not os.path.isdir(crate_file):
            track_paths += _export_crate(crate_file, dest_crate_dir, root_crate, dest_tracks_dir)
    # of tracks that share a filename, the first in the crates is the one copied, so it's the one whose entries are kept
    track_paths = _uniq_by_basename(track_paths)
    # a set: each library file's tracks are checked against it
    track_paths_set = set(track_paths)

    dest_db_file = os.path.join(dest_serato_dir, DatabaseV2.FILENAME)
    _export_library_file(
        DatabaseV2(os.path.join(source_serato_dir, DatabaseV2.FILENAME)),
        dest_db_file,
        dest_tracks_dir,
        track_paths_set,
        edit_track=lambda track: track.set_value(DatabaseV2.Fields.PLAYED, False),
    )
    logger.info(f"created database file {dest_db_file}")
    _copy_order_file(source_serato_dir, dest_serato_dir, root_crate)
    if os.path.exists(local_stems_crate := os.path.join(source_serato_dir, Crate.SERATO_STEMS_CRATE_PATH)):
        dest_stems_crate = os.path.join(dest_serato_dir, Crate.SERATO_STEMS_CRATE_PATH)
        os.makedirs(os.path.dirname(dest_stems_crate), exist_ok=True)
        _export_library_file(Crate(local_stems_crate), dest_stems_crate, dest_tracks_dir, track_paths_set)
        logger.info(f"copied crate {dest_stems_crate}")
    _copy_tracks(track_paths, dest_tracks_path)


def _export_crate(crate_file: str, dest_crate_dir: str, root_crate: Optional[str], dest_tracks_dir: str) -> list[str]:
    """Writes the crate to the drive's crate folder, pointed at its tracks' paths there, and returns the paths it held.

    The paths returned are absolute, found from the drive the crate's library is on, in the crate's order and with any
    duplicates.

    A smart crate is written as a regular crate of the tracks it holds, keeping its sort and columns but not its
    rules, since Serato can't use one on a drive.
    """
    crate: Crate | SmartCrate
    if crate_file.endswith(Crate.EXTENSION):
        crate = Crate(crate_file)
    elif crate_file.endswith(SmartCrate.EXTENSION):
        crate = SmartCrate(crate_file)
    else:
        raise ValueError(f"not a crate file, should end with {Crate.EXTENSION} or {SmartCrate.EXTENSION}: {crate_file}")

    # absolute, since the stored paths are relative to the drive the source library is on, which may not be the home
    # library's
    track_paths = crate.get_track_paths(include_drive=True)

    crate_filename = os.path.basename(crate_file)
    if isinstance(crate, SmartCrate):
        # a smart crate's subcrate separator in its filename is ≫≫, a regular crate's %%
        crate_filename = os.path.splitext(crate_filename.replace("≫≫", "%%"))[0] + Crate.EXTENSION
    if root_crate is not None:
        crate_filename = root_crate + "%%" + crate_filename
    dest_crate_file = os.path.join(dest_crate_dir, crate_filename)
    if isinstance(crate, SmartCrate):
        crate = crate.to_regular_crate(dest_crate_file)
    _export_library_file(crate, dest_crate_file, dest_tracks_dir)
    logger.info(f"copied crate {dest_crate_file}")
    return track_paths


def _export_library_file(
    file: SeratoBinFile,
    dest_file: str,
    dest_tracks_dir: str,
    track_paths: Optional[set[str]] = None,
    edit_track: Optional[Callable[[SeratoBinFile.Track], None]] = None,
):
    """Writes the database or crate to `dest_file`, its tracks pointed at their paths in `dest_tracks_dir` on the drive.

    Given `track_paths`, absolute paths, only those tracks are kept. `edit_track` makes any other change to each track
    kept.
    `dest_file`'s folder must already exist.
    """
    if track_paths is not None:
        file.filter_tracks(lambda track: track.full_path in track_paths)

    def move_track(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
        # relative to the destination drive, where its library is: set_path keeps a relative path as it is, rather than
        # making it relative to the source library's drive
        track.set_path(_dest_track_path(track.relpath, dest_tracks_dir))
        if edit_track is not None:
            edit_track(track)
        return track

    file.modify_tracks(move_track)
    file.remove_duplicates()
    file.save(dest_file)


def _dest_track_path(track_path: str, dest_tracks_dir: str) -> str:
    """Where the track at `track_path` goes on the drive, in `dest_tracks_dir`, as Serato stores a path."""
    return Crate.get_relative_path(os.path.join(dest_tracks_dir, os.path.basename(track_path)))


def _copy_order_file(source_serato_dir: str, dest_serato_dir: str, root_crate: Optional[str]):
    """Copies the source library's crate order file to the drive, with each crate in `root_crate` if given."""
    ORDER_FILE = "neworder.pref"
    LOCAL_ORDER_FILE = os.path.join(source_serato_dir, ORDER_FILE)
    if not os.path.isfile(LOCAL_ORDER_FILE):
        logger.warning(f"no order file to copy: {LOCAL_ORDER_FILE}")
        return
    with open(LOCAL_ORDER_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if root_crate:
        CRATE_KEY = "[crate]"
        for i, line in enumerate(lines):
            if line.startswith(CRATE_KEY) and (crate := line[len(CRATE_KEY) :]) != "Stems":
                lines[i] = f"{CRATE_KEY}{root_crate}%%{crate}"

    dest_order_file = os.path.join(dest_serato_dir, ORDER_FILE)
    with open(dest_order_file, "w", encoding="utf-8") as f:
        # splitlines() strips the newlines, so they must be re-added on write
        f.write("\n".join(lines) + "\n")
    logger.info(f"copied order file {dest_order_file}")


def _copy_tracks(src_paths: list[str], dest_dir: str):
    """Copies each track, by its absolute path, and its stems file, to `dest_dir`, unless it's there unchanged.

    Raises for a track with more than one stems file.
    """
    logger.info("copying files over...")

    not_found: list[str] = []
    stem_files_by_dir: dict[str, list[str]] = {}

    def find_stem_files(src_path: str) -> list[str]:
        dirname, basename = os.path.split(src_path)
        if dirname not in stem_files_by_dir:
            try:
                dir_filenames = os.listdir(dirname)
            except OSError:
                dir_filenames = []
            stem_files_by_dir[dirname] = [f for f in dir_filenames if f.endswith(STEMS_EXTENSION)]
        # named after the track, with or without its extension: matching by prefix would also find another track's,
        # such as "B Extended.serato-stems" for "B.mp3"
        stem_names = {os.path.splitext(basename)[0] + STEMS_EXTENSION, basename + STEMS_EXTENSION}
        return [os.path.join(dirname, f) for f in stem_files_by_dir[dirname] if f in stem_names]

    def maybe_copy(src_path: str):
        if not os.path.exists(src_path):
            not_found.append(src_path)
            return
        dst_path = os.path.join(dest_dir, os.path.basename(src_path))
        if not os.path.exists(dst_path) or not filecmp.cmp(src_path, dst_path, shallow=True):
            os.makedirs(dest_dir, exist_ok=True)
            logger.info(f"copying {src_path}")
            shutil.copy2(src_path, dst_path)

    for index, src_path in enumerate(src_paths):
        print(f"{index / len(src_paths) * 100:.1f}%", end="\r", flush=True)
        maybe_copy(src_path)

        stem_files = find_stem_files(src_path)
        if len(stem_files) > 1:
            raise ValueError(f"more than 1 stems file for {src_path}: {', '.join(stem_files)}")
        if stem_files:
            maybe_copy(stem_files[0])
    print("\n")

    if src_paths and len(not_found) == len(src_paths):
        logger.error("No source files found.")
        uniq_dirs = list(set(os.path.dirname(d) for d in src_paths))
        logger.error(f"Directories: \n{"\n    ".join(uniq_dirs)}")
        return

    for n in not_found:
        logger.warning(f"ERROR: does not exist - {n}")


def get_crate_files(pattern: str, serato_dir: str = LOCAL_SERATO_DIR):
    """The crate and smart crate files in `serato_dir`, the home library's by default, whose filename matches `pattern`.

    `pattern` is tried as a glob, and if nothing matches it, as a regex.
    """
    # the classes' get_crate_files check the crate extension, so stray files in the folders
    # (e.g. .DS_Store) are never matched; a missing folder just means no crates of that kind
    filepaths: list[str] = []
    for crate_class in (Crate, SmartCrate):
        if os.path.isdir(crates_dir := os.path.join(serato_dir, crate_class.DIR)):
            filepaths += crate_class.get_crate_files(crates_dir)

    # try the pattern as a glob first: most globs (e.g. "house*") are also valid regexes, so
    # checking re.compile first would silently give glob-looking patterns regex semantics
    files = [f for f in filepaths if fnmatch.fnmatch(os.path.basename(f), pattern)]
    if not files:
        try:
            regex = re.compile(pattern)
        except re.error:
            return []
        files = [f for f in filepaths if regex.search(os.path.basename(f))]
    return files


def main():
    """The `serato_usb_export` CLI: exports the crates matching the patterns given to a drive, under `Tracks`."""
    import argparse

    @dataclass
    class Args:
        dest_dir: str
        source_dir: str
        crate_matcher: list[str]
        root_crate: str | None

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--drive",
        "--drive_dir",
        dest="dest_dir",
        type=str,
        required=True,
        help='Directory of the destination drive. Example: "E" on Windows, "/Volumes/USB" on macOS',
    )
    parser.add_argument(
        "-s",
        "--source",
        "--source_dir",
        dest="source_dir",
        type=str,
        required=False,
        default=LOCAL_SERATO_DIR,
        help="The _Serato_ folder of the library to export from. Defaults to the home library, ~/Music/_Serato_",
    )
    parser.add_argument(
        "-c",
        "--crates",
        "--crate_matcher",
        dest="crate_matcher",
        nargs="+",
        type=str,
        required=True,
        help='Glob or Regex matcher for crate and smartcrate filenames. Example: "*house*". Can pass multiple to OR them. To copy all, pass "*"',
    )
    parser.add_argument(
        "-r",
        "--root_crate",
        type=str,
        required=False,
        default=None,
        help="Not required, but is very nice when plugging your drive into another DJ's laptop. Sets all crates to be within this crate on the destination drive",
    )
    args = Args(**vars(parser.parse_args()))

    crate_files: list[str] = []
    for cm in args.crate_matcher:
        crate_files += get_crate_files(cm, args.source_dir)

    if platform.system() == "Windows" and len(args.dest_dir) == 1:
        args.dest_dir += ":\\"

    copy_crates_to_usb(
        crate_files=crate_files,
        dest_drive_dir=args.dest_dir,
        dest_tracks_dir="Tracks",
        root_crate=args.root_crate,
        source_serato_dir=args.source_dir,
    )


if __name__ == "__main__":
    main()
