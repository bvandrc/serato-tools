"""Exports crates to a USB drive for Serato.

The crates' tracks are copied to one folder on the drive, with a library that points there.

Also the `serato_usb_export` CLI.
"""

import filecmp
import fnmatch
import itertools
import os
import platform
import re
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from tqdm import tqdm

from serato_tools.crate import Crate
from serato_tools.crate_order import CrateOrder
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

# the local library's files the export reads, besides its crates
LOCAL_SERATO_STEMS_CRATE_PATH = os.path.join(LOCAL_SERATO_DIR, Crate.SERATO_STEMS_CRATE_PATH)
# the extension of the file Serato keeps a track's stems in, beside the track
STEMS_EXTENSION = ".serato-stems"
# the folder on the drive the tracks go in, unless the caller names another
_DRIVE_TRACKS_DIR = "Tracks"
# the crate Serato keeps tracks with stems in, named so in the crate order, never inside a root crate
_STEMS_CRATE_NAME = "Stems"


def copy_crates_to_usb(
    crate_files: Iterable[str],
    dest_drive_dir: str,
    dest_tracks_dir: str = _DRIVE_TRACKS_DIR,
    root_crate: str | None = None,
):
    """Copies the crates in `crate_files`, and their tracks, to the drive at `dest_drive_dir`.

    - Every track goes in `dest_tracks_dir` on the drive, `Tracks` by default. Of tracks that share a filename, a later
      one goes in a subfolder named after its own folder.
    - The drive's `_Serato_` folder is replaced by one holding these crates and a database of just their tracks, all
      pointed at the new paths. Smart crates become regular crates of the tracks they hold, keeping their sort,
      columns, and place in the crate order but not their rules, since Serato can't use a smart crate on a drive.
    - A track whose file is already on the drive, unchanged, isn't copied again. Its stems file is copied too.
    - Given `root_crate`, every crate goes inside a crate of that name.
    - A track whose file is missing is skipped, logging an error. Raises FileNotFoundError if every one is missing, such
      as when the library's music is on a drive that isn't plugged in.
    """
    if not os.path.isdir(dest_drive_dir):
        raise FileNotFoundError(f"destination drive directory does not exist: {dest_drive_dir}")

    crates = [_load_crate(f, root_crate) for f in crate_files if not os.path.isdir(f)]
    dest_paths = _dest_track_paths(
        [os.path.normpath(p) for crate, _ in crates for p in crate.get_track_paths()], dest_tracks_dir
    )

    dest_serato_dir = os.path.join(dest_drive_dir, SERATO_DIR_NAME)
    # TODO: merge with existing, instead of replacing
    if os.path.isdir(dest_serato_dir):
        shutil.rmtree(dest_serato_dir)
    # each crate to write to the drive, with its path in the drive's _Serato_ folder
    drive_crates = [(crate, os.path.join(Crate.DIR, name + Crate.EXTENSION)) for crate, name in crates]
    if os.path.exists(LOCAL_SERATO_STEMS_CRATE_PATH):
        drive_crates.append((Crate(LOCAL_SERATO_STEMS_CRATE_PATH), Crate.SERATO_STEMS_CRATE_PATH))
    # Subcrates even with no crates, and the stems crate's own folder
    for folder in {Crate.DIR, *(os.path.dirname(path) for _, path in drive_crates)}:
        os.makedirs(os.path.join(dest_serato_dir, folder), exist_ok=True)
    for crate, path in drive_crates:
        dest_crate_file = os.path.join(dest_serato_dir, path)
        regular_crate = crate.to_regular_crate(dest_crate_file) if isinstance(crate, SmartCrate) else crate
        _export_library_file(regular_crate, dest_crate_file, dest_paths)
        logger.info(f"copied crate file {dest_crate_file}")

    dest_db_file = os.path.join(dest_serato_dir, DatabaseV2.FILENAME)
    _export_library_file(
        DatabaseV2(os.path.join(LOCAL_SERATO_DIR, DatabaseV2.FILENAME)),
        dest_db_file,
        dest_paths,
        edit_track=lambda track: track.set_value(DatabaseV2.Fields.PLAYED, False),
    )
    logger.info(f"created database file {dest_db_file}")
    _export_crate_order(
        os.path.join(dest_serato_dir, CrateOrder.FILENAME), root_crate, _with_parents(name for _, name in crates)
    )
    _copy_tracks(dest_paths, dest_drive_dir)


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
    """The name on the drive of the crate named `name` in the local library, as its filename and Serato's files say it.

    A smart crate's is the regular crate's it's exported as.
    """
    # a smart crate's subcrate separator is ≫≫, a regular crate's %%
    name = name.replace("≫≫", "%%")
    return f"{root_crate}%%{name}" if root_crate else name


def _dest_track_paths(track_paths: list[str], dest_tracks_dir: str) -> dict[str, str]:
    """Where on the drive each of `track_paths` goes, relative to its root, by its path as Serato stores it.

    Each goes in `dest_tracks_dir`, unless an earlier one has its filename, when it goes in a subfolder named after
    its own folder. Filenames are compared ignoring case, as a drive formatted FAT32 or exFAT does.
    """
    dest_paths: dict[str, str] = {}
    taken: set[str] = set()
    for path in track_paths:
        if path in dest_paths:
            continue
        basename = os.path.basename(path)
        dest = os.path.join(dest_tracks_dir, basename)
        folder = os.path.basename(os.path.dirname(path)) or "_"
        subfolders = itertools.chain([folder], (f"{folder} ({n})" for n in itertools.count(2)))
        while dest.casefold() in taken:
            dest = os.path.join(dest_tracks_dir, next(subfolders), basename)
        taken.add(dest.casefold())
        dest_paths[path] = dest
    return dest_paths


def _export_library_file(
    file: SeratoBinFile,
    dest_file: str,
    dest_paths: Mapping[str, str],
    edit_track: Callable[[SeratoBinFile.Track], None] | None = None,
):
    """Writes the database or crate to `dest_file`, keeping only the tracks in `dest_paths`, pointed at their paths.

    `edit_track` makes any other change to each track kept. `dest_file`'s folder must already exist.
    """
    file.filter_tracks(lambda track: os.path.normpath(track.relpath) in dest_paths)

    def move_track(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
        track.set_path(Crate.get_relative_path(dest_paths[os.path.normpath(track.relpath)]))
        if edit_track is not None:
            edit_track(track)
        return track

    file.modify_tracks(move_track)
    file.remove_duplicates()
    file.save(dest_file)


def _export_crate_order(dest_file: str, root_crate: str | None, crate_names: set[str]):
    """Copies the local library's crate order file to `dest_file`, with only the crates in `crate_names`, each named
    as it is on the drive.

    Given `root_crate`, it also gets that crate, first.
    """
    local_file = os.path.join(LOCAL_SERATO_DIR, CrateOrder.FILENAME)
    if not os.path.isfile(local_file):
        logger.warning(f"no order file to copy: {local_file}")
        return
    order = CrateOrder(local_file)
    crates: list[str] = []
    for crate in order.crates:
        if crate == _STEMS_CRATE_NAME:
            crates.append(crate)
        elif (name := _drive_crate_name(crate, root_crate)) in crate_names:
            crates.append(name)
    # first, where Serato puts it when it rewrites the drive's order file
    order.crates = [root_crate, *crates] if root_crate else crates
    order.save(dest_file)
    logger.info(f"copied order file {dest_file}")


def _with_parents(names: Iterable[str]) -> set[str]:
    """`names`, and the names of every crate they're subcrates of."""
    result: set[str] = set()
    for name in names:
        parts = name.split("%%")
        result.update("%%".join(parts[:i]) for i in range(1, len(parts) + 1))
    return result


def _copy_tracks(dest_paths: Mapping[str, str], dest_drive_dir: str):
    """Copies each track, and its stems file, to its path in `dest_paths` on the drive, unless it's there unchanged.

    Raises for a track with more than one stems file.
    """
    logger.info("copying files over...")

    root = LOCAL_SERATO_DRIVE + os.sep if LOCAL_SERATO_DRIVE else os.sep
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

    def maybe_copy(src_path: str, dst_path: str):
        if not os.path.exists(src_path):
            not_found.append(src_path)
            return
        if not os.path.exists(dst_path) or not filecmp.cmp(src_path, dst_path, shallow=True):
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            logger.info(f"copying {src_path}")
            shutil.copy2(src_path, dst_path)

    for track_path, dest_path in tqdm(dest_paths.items(), desc="Copying tracks", unit="track"):
        src_path = os.path.join(root, track_path)
        dst_path = os.path.join(dest_drive_dir, dest_path)
        maybe_copy(src_path, dst_path)

        stem_files = find_stem_files(src_path)
        if len(stem_files) > 1:
            raise ValueError(f"more than 1 stems file for {src_path}: {', '.join(stem_files)}")
        if stem_files:
            maybe_copy(stem_files[0], os.path.join(os.path.dirname(dst_path), os.path.basename(stem_files[0])))

    if dest_paths and len(not_found) == len(dest_paths):
        uniq_dirs = sorted({os.path.dirname(os.path.join(root, d)) for d in dest_paths})
        raise FileNotFoundError("none of the tracks were found, in these folders:\n    " + "\n    ".join(uniq_dirs))

    for n in not_found:
        logger.error(f"does not exist - {n}")


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
        root_crate=args.root_crate,
    )
    # ruff: enable[PLC0415]


if __name__ == "__main__":
    main()
