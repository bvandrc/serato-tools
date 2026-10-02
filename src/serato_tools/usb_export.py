import sys
import os
import filecmp
import fnmatch
import shutil
import glob
import re
import platform
from typing import Optional
from dataclasses import dataclass

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.database_v2 import DatabaseV2
from serato_tools.crate import Crate
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils import (
    logger,
    SERATO_DIR_NAME,
    SERATO_DIR as LOCAL_SERATO_DIR,
    SERATO_DRIVE as LOCAL_SERATO_DRIVE,
)

# TODO: put in folders if there are different locations locally for the same basename


def _uniq_by_basename(paths: list[str]):
    basenames: list[str] = []
    return_paths: list[str] = []
    for path in paths:
        basename = os.path.basename(path)
        if basename not in basenames:
            basenames.append(basename)
            return_paths.append(path)
    return return_paths


def copy_crates_to_usb(
    crate_files: list[str], dest_drive_dir: str, dest_tracks_dir: str, root_crate: Optional[str] = None
):
    if not os.path.isdir(dest_drive_dir):
        raise FileNotFoundError(f"destination drive directory does not exist: {dest_drive_dir}")

    DEST_SERATO_DIR = os.path.join(dest_drive_dir, SERATO_DIR_NAME)

    # TODO: merge with existing, instead of replacing
    if os.path.isdir(DEST_SERATO_DIR):
        shutil.rmtree(DEST_SERATO_DIR)

    # copy the crate files, and get the filenames from them
    tracks_to_copy: list[str] = []

    crate_dir = os.path.join(DEST_SERATO_DIR, Crate.DIR)
    os.makedirs(crate_dir, exist_ok=True)

    def change_track_path(track_path: str):
        return Crate.get_relative_path(os.path.join(dest_tracks_dir, os.path.basename(track_path)))

    def modify_crate_track(track: Crate.Track) -> Crate.Track:
        tracks_to_copy.append(track.relpath)
        track.set_path(change_track_path(track.relpath))
        return track

    for crate_file in crate_files:
        if os.path.isdir(crate_file):
            continue
        elif crate_file.endswith(Crate.EXTENSION):
            crate = Crate(crate_file)
        elif crate_file.endswith(SmartCrate.EXTENSION):
            crate = SmartCrate(crate_file)
        else:
            raise ValueError(
                f"not a crate file, should end with {Crate.EXTENSION} or {SmartCrate.EXTENSION}: {crate_file}"
            )

        crate.modify_tracks(modify_crate_track)
        crate.remove_duplicates()

        crate_filename = os.path.basename(crate_file)
        if root_crate is not None:
            crate_filename = root_crate + "%%" + crate_filename
        new_crate_file = os.path.join(crate_dir, crate_filename)
        crate.save(new_crate_file)

        # need to just save smartCrates as a .crate instead of a .scrate, can't do smart crate on USB.
        if isinstance(crate, SmartCrate):
            existing = new_crate_file
            dirname, basename = os.path.split(existing)
            # only touch the filename: str.replace on the full path could hit a directory name
            new = os.path.join(dirname, os.path.splitext(basename.replace("≫≫", "%%"))[0] + Crate.EXTENSION)
            os.replace(existing, new)
            new_crate_file = new
        logger.info(f"copied crate {new_crate_file}")

    # create the db file
    db = DatabaseV2()
    tracks_to_copy = [os.path.normpath(f) for f in tracks_to_copy]
    tracks_to_copy = _uniq_by_basename(tracks_to_copy)
    tracks_to_copy_basenames = [os.path.basename(f) for f in tracks_to_copy]

    def modify_db_track(track: DatabaseV2.Track) -> DatabaseV2.Track:
        track.set_path(os.path.join(dest_tracks_dir, os.path.basename(track.relpath)))
        track.set_value(DatabaseV2.Fields.PLAYED, False)
        return track

    db.filter_tracks(lambda track: os.path.basename(track.relpath) in tracks_to_copy_basenames)
    db.modify_tracks(modify_db_track)
    db.remove_duplicates()

    new_db_file = os.path.join(DEST_SERATO_DIR, DatabaseV2.FILENAME)
    db.save(new_db_file)
    logger.info(f"created database file {new_db_file}")

    # copy crate order file, modify if needed
    NEW_ORDER_FILE = "neworder.pref"
    LOCAL_NEW_ORDER_FILEPATH = os.path.join(LOCAL_SERATO_DIR, NEW_ORDER_FILE)
    if os.path.isfile(LOCAL_NEW_ORDER_FILEPATH):
        with open(LOCAL_NEW_ORDER_FILEPATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

        if root_crate:
            CRATE_KEY = "[crate]"
            new_lines = []
            for line in lines:
                if line.startswith(CRATE_KEY):
                    value = line[len(CRATE_KEY) :]
                    if value != "Stems":
                        line = f"{CRATE_KEY}{root_crate}%%{value}"
                new_lines.append(line)
            lines = new_lines

        DEST_NEW_ORDER_FILEPATH = os.path.join(DEST_SERATO_DIR, NEW_ORDER_FILE)
        with open(DEST_NEW_ORDER_FILEPATH, "w", encoding="utf-8") as f:
            # splitlines() strips the newlines, so they must be re-added on write
            f.write("\n".join(lines) + "\n")
            logger.info(f"copied order file {DEST_NEW_ORDER_FILEPATH}")
    else:
        logger.warning(f"no order file to copy: {LOCAL_NEW_ORDER_FILEPATH}")

    # copy stems crate
    LOCAL_STEMS_CRATE = os.path.join(LOCAL_SERATO_DIR, Crate.SERATO_STEMS_CRATE_PATH)
    if os.path.exists(LOCAL_STEMS_CRATE):
        DEST_STEMS_CRATE = os.path.join(DEST_SERATO_DIR, Crate.SERATO_STEMS_CRATE_PATH)
        os.makedirs(os.path.dirname(DEST_STEMS_CRATE), exist_ok=True)
        stems_crate = Crate(LOCAL_STEMS_CRATE)

        def modify_stems_crate_track(track: Crate.Track) -> Crate.Track:
            track.set_path(change_track_path(track.relpath))
            return track

        stems_crate.filter_tracks(lambda track: os.path.basename(track.relpath) in tracks_to_copy_basenames)
        stems_crate.modify_tracks(modify_stems_crate_track)
        stems_crate.remove_duplicates()
        stems_crate.save(DEST_STEMS_CRATE)
        logger.info(f"copied crate {DEST_STEMS_CRATE}")

    # copy files
    logger.info("copying files over...")

    root = LOCAL_SERATO_DRIVE + os.sep if LOCAL_SERATO_DRIVE else os.sep
    tracks_to_copy = [os.path.join(root, t) for t in tracks_to_copy]

    not_found: list[str] = []

    def maybe_copy(src_path: str, dst_path: str):
        if not os.path.exists(src_path):
            not_found.append(src_path)
            return
        copy = (not filecmp.cmp(src_path, dst_path, shallow=True)) if os.path.exists(dst_path) else True
        if copy:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            logger.info(f"copying {src_path}")
            shutil.copy2(src_path, dst_path)

    for index, src_path in enumerate(tracks_to_copy):
        percent_complete = index / float(len(tracks_to_copy)) * 100
        print(f"{percent_complete:.1f}%", end="\r", flush=True)
        maybe_copy(
            src_path=src_path,
            dst_path=os.path.join(dest_drive_dir, dest_tracks_dir, os.path.basename(src_path)),
        )

        maybe_stem_files = glob.glob(os.path.splitext(src_path)[0] + "*.serato-stems")
        if len(maybe_stem_files) > 1:
            ERROR_STR = "should not have more than 1 stem file for: " + src_path
            print(ERROR_STR)
            print("Files found:")
            print("\n".join(maybe_stem_files))
            raise Exception(ERROR_STR)
        if len(maybe_stem_files) == 1:
            maybe_copy(
                src_path=maybe_stem_files[0],
                dst_path=os.path.join(dest_drive_dir, dest_tracks_dir, os.path.basename(maybe_stem_files[0])),
            )
    print("\n")

    if tracks_to_copy and len(not_found) == len(tracks_to_copy):
        logger.error("No source files found.")
        uniq_dirs = list(set(os.path.dirname(d) for d in tracks_to_copy))
        logger.error(f"Directories: \n{"\n    ".join(uniq_dirs)}")
        return

    for n in not_found:
        logger.warning(f"ERROR: does not exist - {n}")


def get_crate_files(pattern: str):
    filepaths: list[str] = []
    for dir in [Crate.DIR, SmartCrate.DIR]:
        root_dir = os.path.join(LOCAL_SERATO_DIR, dir)
        filepaths += [os.path.join(root_dir, f) for f in os.listdir(root_dir)]
    filepaths = [f for f in filepaths if os.path.isfile(f)]  # remove dirs

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
        help='Directory of the destination drive. Example: "E" on Windows',
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
        args.dest_dir += ":\\\\"

    copy_crates_to_usb(
        crate_files=crate_files,
        dest_drive_dir=args.dest_dir,
        dest_tracks_dir="Tracks",
        root_crate=args.root_crate,
    )


if __name__ == "__main__":
    main()
