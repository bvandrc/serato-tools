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
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tqdm import tqdm

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.library import Library
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils import (
    SERATO_DIR as LOCAL_SERATO_DIR,
    SERATO_DIR_NAME,
    SERATO_DRIVE as LOCAL_SERATO_DRIVE,
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
    crate_files: Iterable[str], dest_drive_dir: str, dest_tracks_dir: str, root_crate: str | None = None
):
    """Copies the crates in `crate_files`, and their tracks, to the drive at `dest_drive_dir`.

    - Every track goes in `dest_tracks_dir` on the drive, and only the first of tracks that share a filename is kept.
    - The drive's `_Serato_` folder is replaced by one holding these crates and a database of just their tracks, all
      pointed at the new paths. Smart crates become regular crates of the tracks they hold, keeping their sort and
      columns but not their rules, since Serato can't use a smart crate on a drive.
    - A track whose file is already on the drive, unchanged, isn't copied again. Its stems file is copied too.
    - Given `root_crate`, every crate goes inside a crate of that name.
    - A track whose file is missing is skipped, logging an error. Raises FileNotFoundError if every one is missing, such
      as when the library's music is on a drive that isn't plugged in.
    """
    if not os.path.isdir(dest_drive_dir):
        raise FileNotFoundError(f"destination drive directory does not exist: {dest_drive_dir}")

    crates = [_load_crate(f, root_crate) for f in crate_files if not os.path.isdir(f)]
    # of tracks that share a filename, the first in the crates is the one copied, so it's the one whose entries are kept
    track_paths = _uniq_by_basename([os.path.normpath(p) for crate, _ in crates for p in crate.get_track_paths()])
    # a set: each library file's tracks are checked against it
    track_paths_set = set(track_paths)

    dest_serato_dir = os.path.join(dest_drive_dir, SERATO_DIR_NAME)
    if os.path.isdir(dest_serato_dir):
        shutil.rmtree(dest_serato_dir)
    dest_crate_dir = os.path.join(dest_serato_dir, Crate.DIR)
    os.makedirs(dest_crate_dir, exist_ok=True)
    for crate, name in crates:
        dest_crate_file = os.path.join(dest_crate_dir, name + Crate.EXTENSION)
        regular_crate = crate.to_regular_crate(dest_crate_file) if isinstance(crate, SmartCrate) else crate
        _export_library_file(regular_crate, dest_crate_file, dest_tracks_dir)
        logger.info(f"copied crate {dest_crate_file}")

    dest_db_file = os.path.join(dest_serato_dir, DatabaseV2.FILENAME)
    _export_library_file(
        DatabaseV2(os.path.join(LOCAL_SERATO_DIR, DatabaseV2.FILENAME)),
        dest_db_file,
        dest_tracks_dir,
        track_paths_set,
        edit_track=lambda track: track.set_value(DatabaseV2.Fields.PLAYED, False),
    )
    logger.info(f"created database file {dest_db_file}")
    _copy_order_file(dest_serato_dir, root_crate)
    if os.path.exists(local_stems_crate := os.path.join(LOCAL_SERATO_DIR, Crate.SERATO_STEMS_CRATE_PATH)):
        dest_stems_crate = os.path.join(dest_serato_dir, Crate.SERATO_STEMS_CRATE_PATH)
        os.makedirs(os.path.dirname(dest_stems_crate), exist_ok=True)
        _export_library_file(Crate(local_stems_crate), dest_stems_crate, dest_tracks_dir, track_paths_set)
        logger.info(f"copied crate {dest_stems_crate}")
    _copy_tracks(track_paths, os.path.join(dest_drive_dir, dest_tracks_dir))


def _load_crate(crate_file: str, root_crate: str | None) -> tuple[Crate | SmartCrate, str]:
    """The crate or smart crate in `crate_file`, and its name on the drive."""
    crate: Crate | SmartCrate
    if crate_file.endswith(Crate.EXTENSION):
        crate = Crate(crate_file)
    elif crate_file.endswith(SmartCrate.EXTENSION):
        crate = SmartCrate(crate_file)
    else:
        raise ValueError(f"not a crate file, should end with {Crate.EXTENSION} or {SmartCrate.EXTENSION}: {crate_file}")
    return crate, _drive_crate_name(os.path.splitext(os.path.basename(crate_file))[0], root_crate)


def _drive_crate_name(name: str, root_crate: str | None) -> str:
    """The name on the drive of the crate named `name` in the local library: a smart crate's is the regular crate's
    it's exported as.
    """
    # a smart crate's subcrate separator is ≫≫, a regular crate's %%
    name = name.replace("≫≫", "%%")
    return f"{root_crate}%%{name}" if root_crate else name


def _export_library_file(
    file: SeratoBinFile,
    dest_file: str,
    dest_tracks_dir: str,
    track_paths: set[str] | None = None,
    edit_track: Callable[[SeratoBinFile.Track], None] | None = None,
):
    """Writes the database or crate to `dest_file`, its tracks pointed at their paths in `dest_tracks_dir` on the drive.

    Given `track_paths`, only those tracks are kept. `edit_track` makes any other change to each track kept.
    `dest_file`'s folder must already exist.
    """
    if track_paths is not None:
        file.filter_tracks(lambda track: os.path.normpath(track.relpath) in track_paths)

    def move_track(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
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


def _copy_order_file(dest_serato_dir: str, root_crate: str | None):
    """Copies Serato's crate order file to the drive, with each crate in `root_crate` if given."""
    ORDER_FILE = "neworder.pref"
    LOCAL_ORDER_FILE = os.path.join(LOCAL_SERATO_DIR, ORDER_FILE)
    if not os.path.isfile(LOCAL_ORDER_FILE):
        logger.warning(f"no order file to copy: {LOCAL_ORDER_FILE}")
        return
    with open(LOCAL_ORDER_FILE, encoding="utf-8") as f:
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

    for src_path in tqdm(src_paths, desc="Copying tracks", unit="track"):
        maybe_copy(src_path)

        stem_files = find_stem_files(src_path)
        if len(stem_files) > 1:
            raise ValueError(f"more than 1 stems file for {src_path}: {', '.join(stem_files)}")
        if stem_files:
            maybe_copy(stem_files[0])

    if src_paths and len(not_found) == len(src_paths):
        uniq_dirs = sorted({os.path.dirname(d) for d in src_paths})
        raise FileNotFoundError("none of the tracks were found, in these folders:\n    " + "\n    ".join(uniq_dirs))

    for n in not_found:
        logger.error(f"does not exist - {n}")


def get_crate_files(pattern: str):
    """The crate and smart crate files in the default Serato folder whose name matches `pattern`.

    The name is the filename without its extension, so `"*crate*"` matches only crates with "crate" in their name. A
    subcrate's name includes its parents' (`Bass%%DnB`), so `"Bass*"` matches a crate and its subcrates. `pattern` is
    tried as a glob, and if nothing matches it, as a regex.
    """
    crate_names = {f: os.path.splitext(os.path.basename(f))[0] for f in Library(LOCAL_SERATO_DIR).crate_files}

    # try the pattern as a glob first: most globs (e.g. "house*") are also valid regexes, so
    # checking re.compile first would silently give glob-looking patterns regex semantics
    files = [f for f, name in crate_names.items() if fnmatch.fnmatch(name, pattern)]
    if not files:
        try:
            regex = re.compile(pattern)
        except re.error:
            return []
        files = [f for f, name in crate_names.items() if regex.search(name)]
    return files


def main():
    """The `serato_usb_export` CLI: exports the crates matching the patterns given to a drive, under `Tracks`."""
    # ruff: disable[PLC0415]
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
        help='Glob or Regex matcher for crate and smartcrate names, without the file extension. Example: "*house*". Can pass multiple to OR them. To copy all, pass "*"',
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
    # ruff: enable[PLC0415]


if __name__ == "__main__":
    main()
