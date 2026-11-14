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
    SERATO_DRIVE as LOCAL_SERATO_DRIVE,
    logger,
)
from serato_tools.utils.bin_file_base import SeratoBinFile

# TODO: put in folders if there are different locations locally for the same basename


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
    crate_files: Iterable[str], dest_drive_dir: str, dest_tracks_dir: str, root_crate: Optional[str] = None
):
    """Copies the crates in `crate_files`, and their tracks, to the drive at `dest_drive_dir`.

    - Every track goes in `dest_tracks_dir` on the drive, and only the first of tracks that share a filename is kept.
    - The drive's `_Serato_` folder is replaced by one holding these crates and a database of just their tracks, all
      pointed at the new paths. Smart crates become regular crates, since Serato can't use one on a drive.
    - A track whose file is already on the drive, unchanged, isn't copied again. Its stems file is copied too.
    - Given `root_crate`, every crate goes inside a crate of that name.
    """
    if not os.path.isdir(dest_drive_dir):
        raise FileNotFoundError(f"destination drive directory does not exist: {dest_drive_dir}")

    dest_serato_dir = os.path.join(dest_drive_dir, SERATO_DIR_NAME)
    # TODO: merge with existing, instead of replacing
    if os.path.isdir(dest_serato_dir):
        shutil.rmtree(dest_serato_dir)

    def dest_track_path(track_path: str) -> str:
        # where a track goes on the drive, as Serato stores a path
        return Crate.get_relative_path(os.path.join(dest_tracks_dir, os.path.basename(track_path)))

    dest_crate_dir = os.path.join(dest_serato_dir, Crate.DIR)
    os.makedirs(dest_crate_dir)
    track_paths: list[str] = []
    for crate_file in crate_files:
        if not os.path.isdir(crate_file):
            track_paths += _export_crate(crate_file, dest_crate_dir, root_crate, dest_track_path)
    track_paths = _uniq_by_basename([os.path.normpath(f) for f in track_paths])
    # a set: each library file's tracks are checked against it
    basenames = {os.path.basename(f) for f in track_paths}

    def reset_played(track: DatabaseV2.Track):
        track.set_value(DatabaseV2.Fields.PLAYED, False)

    _export_library_file(
        DatabaseV2(os.path.join(LOCAL_SERATO_DIR, DatabaseV2.FILENAME)),
        os.path.join(dest_serato_dir, DatabaseV2.FILENAME),
        basenames,
        dest_track_path,
        edit_track=reset_played,
    )
    _copy_order_file(dest_serato_dir, root_crate)
    if os.path.exists(local_stems_crate := os.path.join(LOCAL_SERATO_DIR, Crate.SERATO_STEMS_CRATE_PATH)):
        _export_library_file(
            Crate(local_stems_crate),
            os.path.join(dest_serato_dir, Crate.SERATO_STEMS_CRATE_PATH),
            basenames,
            dest_track_path,
        )
    _copy_tracks(track_paths, os.path.join(dest_drive_dir, dest_tracks_dir))


def _export_crate(
    crate_file: str, dest_crate_dir: str, root_crate: Optional[str], dest_track_path: Callable[[str], str]
) -> list[str]:
    """Writes the crate to the drive's crate folder, pointed at its tracks' paths there, and returns their paths here.

    A smart crate is written as a regular crate, with its tracks, sort, and columns, since Serato can't use one on a
    drive.
    """
    crate: Crate | SmartCrate
    if crate_file.endswith(Crate.EXTENSION):
        crate = Crate(crate_file)
    elif crate_file.endswith(SmartCrate.EXTENSION):
        crate = SmartCrate(crate_file)
    else:
        raise ValueError(f"not a crate file, should end with {Crate.EXTENSION} or {SmartCrate.EXTENSION}: {crate_file}")

    track_paths: list[str] = []

    def move_track(track: Crate.Track) -> Crate.Track:
        track_paths.append(track.relpath)
        track.set_path(dest_track_path(track.relpath))
        return track

    crate.modify_tracks(move_track)
    crate.remove_duplicates()

    crate_filename = os.path.basename(crate_file)
    if root_crate is not None:
        crate_filename = root_crate + "%%" + crate_filename
    if isinstance(crate, SmartCrate):
        # only the filename is changed, since str.replace on the full path could hit a folder's name
        crate_filename = os.path.splitext(crate_filename.replace("≫≫", "%%"))[0] + Crate.EXTENSION
    dest_crate_file = os.path.join(dest_crate_dir, crate_filename)
    (crate.to_crate(dest_crate_file) if isinstance(crate, SmartCrate) else crate).save(dest_crate_file)
    logger.info(f"copied crate {dest_crate_file}")
    return track_paths


def _export_library_file(
    file: SeratoBinFile,
    dest_file: str,
    basenames: set[str],
    dest_track_path: Callable[[str], str],
    edit_track: Optional[Callable[[SeratoBinFile.Track], None]] = None,
):
    """Writes the database or crate to `dest_file` with only the tracks named in `basenames`, at their drive paths.

    `edit_track` makes any other change to each of those tracks.
    """
    file.filter_tracks(lambda track: os.path.basename(track.relpath) in basenames)

    def move_track(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
        track.set_path(dest_track_path(track.relpath))
        if edit_track is not None:
            edit_track(track)
        return track

    file.modify_tracks(move_track)
    file.remove_duplicates()
    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
    file.save(dest_file)
    logger.info(f"copied {dest_file}")


def _copy_order_file(dest_serato_dir: str, root_crate: Optional[str]):
    """Copies Serato's crate order file to the drive, with each crate in `root_crate` if given."""
    order_file = "neworder.pref"
    local_order_file = os.path.join(LOCAL_SERATO_DIR, order_file)
    if not os.path.isfile(local_order_file):
        logger.warning(f"no order file to copy: {local_order_file}")
        return
    with open(local_order_file, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if root_crate:
        crate_key = "[crate]"
        for i, line in enumerate(lines):
            if line.startswith(crate_key) and (crate := line[len(crate_key) :]) != "Stems":
                lines[i] = f"{crate_key}{root_crate}%%{crate}"

    dest_order_file = os.path.join(dest_serato_dir, order_file)
    with open(dest_order_file, "w", encoding="utf-8") as f:
        # splitlines() strips the newlines, so they must be re-added on write
        f.write("\n".join(lines) + "\n")
    logger.info(f"copied order file {dest_order_file}")


def _copy_tracks(track_paths: list[str], dest_dir: str):
    """Copies each track, as Serato stores its path, and its stems file, to `dest_dir`, unless it's there unchanged.

    Raises for a track with more than one stems file.
    """
    logger.info("copying files over...")

    root = LOCAL_SERATO_DRIVE + os.sep if LOCAL_SERATO_DRIVE else os.sep
    src_paths = [os.path.join(root, t) for t in track_paths]

    not_found: list[str] = []
    stem_files_by_dir: dict[str, list[str]] = {}

    def find_stem_files(src_path: str) -> list[str]:
        dirname, basename = os.path.split(src_path)
        if dirname not in stem_files_by_dir:
            try:
                dir_filenames = os.listdir(dirname)
            except OSError:
                dir_filenames = []
            stem_files_by_dir[dirname] = [f for f in dir_filenames if f.endswith(".serato-stems")]
        track_name = os.path.splitext(basename)[0]
        return [os.path.join(dirname, f) for f in stem_files_by_dir[dirname] if f.startswith(track_name)]

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
            error = "should not have more than 1 stem file for: " + src_path
            print(error)
            print("Files found:")
            print("\n".join(stem_files))
            raise Exception(error)
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


def get_crate_files(pattern: str):
    """The crate and smart crate files in the default Serato folder whose filename matches `pattern`.

    `pattern` is tried as a glob, and if nothing matches it, as a regex.
    """
    # the classes' get_crate_files check the crate extension, so stray files in the folders
    # (e.g. .DS_Store) are never matched; a missing folder just means no crates of that kind
    filepaths: list[str] = []
    for crate_class in (Crate, SmartCrate):
        if os.path.isdir(crate_class.DIR_PATH):
            filepaths += crate_class.get_crate_files()

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
        crate_files += get_crate_files(cm)

    if platform.system() == "Windows" and len(args.dest_dir) == 1:
        args.dest_dir += ":\\"

    copy_crates_to_usb(
        crate_files=crate_files,
        dest_drive_dir=args.dest_dir,
        dest_tracks_dir="Tracks",
        root_crate=args.root_crate,
    )


if __name__ == "__main__":
    main()
