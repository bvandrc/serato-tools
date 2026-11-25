"""Exports crates to a USB drive for Serato.

The crates' tracks are copied to one folder on the drive, with a library that points there.

Also the `serato_usb_export` CLI.
"""

import itertools
import logging
import os
import platform
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from tqdm import tqdm

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.library import Library
from serato_tools.pref_files import CollapsedCrates, CrateOrder
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils import (
    SERATO_DIR as LOCAL_SERATO_DIR,
    SERATO_DIR_NAME,
    SERATO_DRIVE as LOCAL_SERATO_DRIVE,
    logger,
)
from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils.files import copy_if_changed, delete_other_files, is_inside

# the local library's files the export reads, besides its crates
LOCAL_SERATO_DATABASE_PATH = os.path.join(LOCAL_SERATO_DIR, DatabaseV2.FILENAME)
LOCAL_SERATO_STEMS_CRATE_PATH = os.path.join(LOCAL_SERATO_DIR, Crate.SERATO_STEMS_CRATE_PATH)
# the folder on the drive the tracks go in, unless the caller names another
DEFAULT_DRIVE_TRACKS_DIR = "Tracks"
# the crate Serato keeps tracks with stems in, named so in the crate order, never inside a root crate
_STEMS_CRATE_NAME = "Stems"


def copy_crates_to_usb(
    crate_files: Iterable[str],
    dest_drive_dir: str,
    dest_tracks_dir: str = DEFAULT_DRIVE_TRACKS_DIR,
    root_crate: str | None = None,
    delete_unused_tracks: bool = False,
):
    """Copies the crates in `crate_files`, and their tracks, to the drive at `dest_drive_dir`.

    - Every track goes in `dest_tracks_dir` on the drive, `Tracks` by default. Of tracks that share a filename, a later
      one goes in a subfolder named after its own folder.
    - The drive's `_Serato_` folder is replaced by one holding these crates and a database of just their tracks, all
      pointed at the new paths. Smart crates become regular crates of the tracks they hold, keeping their sort,
      columns, and place in the crate order but not their rules, since Serato can't use a smart crate on a drive.
    - A track whose file is already on the drive, unchanged, isn't copied again. Its stems files are copied too.
    - Given `root_crate`, every crate goes inside a crate of that name.
    - Given `delete_unused_tracks`, every other file under `dest_tracks_dir`, such as a track since taken out of the
      crates, is deleted. Raises ValueError, before writing anything, if `dest_tracks_dir` isn't a folder inside the
      drive or there's no track to export, since that would delete more than unused tracks.
    - A track whose file is missing is skipped, logging an error. Raises FileNotFoundError if every one is missing, such
      as when the library's music is on a drive that isn't plugged in.
    """
    if not os.path.isdir(dest_drive_dir):
        raise FileNotFoundError(f"destination drive directory does not exist: {dest_drive_dir}")

    # everything is read from the local library before anything on the drive changes, so a file that can't be read
    # leaves the drive as it was
    crates = [_load_crate(f, root_crate) for f in crate_files if not os.path.isdir(f)]
    # each crate to write to the drive, with its path in the drive's _Serato_ folder
    drive_crates = [(crate, os.path.join(Crate.DIR, name + Crate.EXTENSION)) for crate, name in crates]
    if os.path.exists(LOCAL_SERATO_STEMS_CRATE_PATH):
        drive_crates.append((Crate(LOCAL_SERATO_STEMS_CRATE_PATH), Crate.SERATO_STEMS_CRATE_PATH))
    database = DatabaseV2(LOCAL_SERATO_DATABASE_PATH)
    crate_order = _load_pref_file(CrateOrder, missing_level=logging.WARNING)
    # unlike the crate order, a library doesn't necessarily have one
    collapsed_crates = _load_pref_file(CollapsedCrates, missing_level=logging.INFO)
    dest_paths = _dest_track_paths(
        [os.path.normpath(p) for crate, _ in crates for p in crate.get_track_paths()], dest_tracks_dir
    )
    if delete_unused_tracks:
        _check_unused_tracks_can_be_deleted(dest_drive_dir, dest_tracks_dir, dest_paths)

    dest_serato_dir = os.path.join(dest_drive_dir, SERATO_DIR_NAME)
    # TODO: merge with existing, instead of replacing
    if os.path.isdir(dest_serato_dir):
        shutil.rmtree(dest_serato_dir)
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
        database,
        dest_db_file,
        dest_paths,
        edit_track=lambda track: track.set_value(DatabaseV2.Fields.PLAYED, False),
    )
    logger.info(f"created database file {dest_db_file}")
    crate_names = [name for _, name in crates]
    for pref_file in (crate_order, collapsed_crates):
        if pref_file is not None:
            _export_pref_file(pref_file, os.path.join(dest_serato_dir, pref_file.FILENAME), root_crate, crate_names)
    copied = _copy_tracks(dest_paths, dest_drive_dir)
    if delete_unused_tracks:
        delete_other_files(os.path.join(dest_drive_dir, dest_tracks_dir), copied)


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


def _load_pref_file[T: (CrateOrder, CollapsedCrates)](cls: type[T], missing_level: int) -> T | None:
    """The local library's crate order or collapsed crates, or None if it has none, logged at `missing_level`, or if
    it can't be read, logging a warning.

    The drive then gets no such file, and Serato lists its crates in its default order, or shows them all expanded.
    """
    file = os.path.join(LOCAL_SERATO_DIR, cls.FILENAME)
    if not os.path.isfile(file):
        logger.log(missing_level, f"no {cls.FILENAME} to copy: {file}")
        return None
    try:
        return cls(file)
    except ValueError as e:
        logger.warning(f"can't read {cls.FILENAME}, so not copying it: {file}: {e}")
        return None


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


def _check_unused_tracks_can_be_deleted(dest_drive_dir: str, dest_tracks_dir: str, dest_paths: Mapping[str, str]):
    """Raises ValueError if deleting the files under `dest_tracks_dir` that the export doesn't hold would delete more
    than unused tracks: when it isn't a folder inside the drive, or there's no track to export.
    """
    tracks_dir = os.path.realpath(os.path.join(dest_drive_dir, dest_tracks_dir))
    # not the drive itself, which would hold its _Serato_ folder
    if not is_inside(tracks_dir, dest_drive_dir):
        raise ValueError(f"delete_unused_tracks needs a tracks folder inside the drive, not {tracks_dir}")
    if not dest_paths:
        raise ValueError("delete_unused_tracks needs a track to export, or it would delete every track on the drive")


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


def _export_pref_file(
    pref_file: CrateOrder | CollapsedCrates, dest_file: str, root_crate: str | None, crate_names: Iterable[str]
):
    """Writes the crate order or collapsed crates to `dest_file`, with only the crates in `crate_names` and their
    parents, each named as it is on the drive.

    Given `root_crate`, a crate order also gets that crate, first.
    """
    crate_names = _with_parents(crate_names)
    crates: list[str] = []
    for crate in pref_file.crates:
        if crate == _STEMS_CRATE_NAME:
            crates.append(crate)
        elif (name := _drive_crate_name(crate, root_crate)) in crate_names:
            crates.append(name)
    if root_crate and isinstance(pref_file, CrateOrder):
        # first, where Serato puts it when it rewrites the drive's order file
        crates.insert(0, root_crate)
    pref_file.crates = crates
    pref_file.save(dest_file)
    logger.info(f"copied {dest_file}")


def _with_parents(names: Iterable[str]) -> set[str]:
    """`names`, and the names of every crate they're subcrates of."""
    result: set[str] = set()
    for name in names:
        parts = name.split("%%")
        result.update("%%".join(parts[:i]) for i in range(1, len(parts) + 1))
    return result


def _copy_tracks(dest_paths: Mapping[str, str], dest_drive_dir: str) -> set[str]:
    """Copies each track, and its stems files, to its path in `dest_paths` on the drive, unless it's there unchanged.

    Returns the paths on the drive of the tracks and stems files it's meant to hold, copied now or before, or whose
    track is missing.
    """
    logger.info("copying files over...")

    root = LOCAL_SERATO_DRIVE + os.sep if LOCAL_SERATO_DRIVE else os.sep
    not_found: list[str] = []
    meant_to_hold: set[str] = set()

    for track_path, dest_path in tqdm(dest_paths.items(), desc="Copying tracks", unit="track"):
        src_path = os.path.join(root, track_path)
        dst_path = os.path.join(dest_drive_dir, dest_path)
        # kept whether or not it's copied now, as a track missing from the library still is
        meant_to_hold.add(dst_path)
        if not copy_if_changed(src_path, dst_path):
            not_found.append(src_path)

        stems_files = Library.find_stems_files(src_path)
        for stems_file in stems_files:
            stems_dest = os.path.join(os.path.dirname(dst_path), os.path.basename(stems_file))
            meant_to_hold.add(stems_dest)
            if not copy_if_changed(stems_file, stems_dest):
                # found just now, so gone since; not counted with the tracks, which it isn't one of
                logger.error(f"does not exist - {stems_file}")
        if not stems_files and not os.path.exists(src_path):
            # a missing track's file on the drive is kept, so its stems files there are too
            meant_to_hold.update(Library.find_stems_files(dst_path))

    if dest_paths and len(not_found) == len(dest_paths):
        uniq_dirs = sorted({os.path.dirname(os.path.join(root, d)) for d in dest_paths})
        raise FileNotFoundError("none of the tracks were found, in these folders:\n    " + "\n    ".join(uniq_dirs))

    for n in not_found:
        logger.error(f"does not exist - {n}")
    return meant_to_hold


def main():
    """The `serato_usb_export` CLI: exports the crates matching the patterns given to a drive, under `Tracks`."""
    # ruff: disable[PLC0415]
    import argparse

    @dataclass
    class Args:
        dest_dir: str
        crate_matcher: list[str]
        root_crate: str | None
        delete_unused_tracks: bool

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
    parser.add_argument(
        "--delete_unused_tracks",
        action="store_true",
        help=f"Delete every other file in the drive's {DEFAULT_DRIVE_TRACKS_DIR} folder, such as tracks since taken out of the crates",
    )
    args = Args(**vars(parser.parse_args()))

    library = Library(LOCAL_SERATO_DIR)
    crate_files: list[str] = []
    for cm in args.crate_matcher:
        crate_files += library.find_crate_files(cm)

    if platform.system() == "Windows" and len(args.dest_dir) == 1:
        args.dest_dir += ":\\"

    copy_crates_to_usb(
        crate_files=crate_files,
        dest_drive_dir=args.dest_dir,
        root_crate=args.root_crate,
        delete_unused_tracks=args.delete_unused_tracks,
    )
    # ruff: enable[PLC0415]


if __name__ == "__main__":
    main()
