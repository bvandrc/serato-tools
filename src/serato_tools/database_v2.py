#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
from dataclasses import dataclass

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils import logger, SERATO_DIR


class DatabaseV2(SeratoBinFile):
    TESTED_VERSIONS = ["2.0/Serato Scratch LIVE Database"]
    FILENAME = "database V2"
    DEFAULT_DATABASE_FILE = os.path.join(SERATO_DIR, FILENAME)
    TRACK_PATH_KEY = SeratoBinFile.Fields.FILE_PATH

    DEFAULT_ENTRIES = [
        (SeratoBinFile.Fields.VERSION, "2.0/Serato Scratch LIVE Database"),
    ]

    def __init__(self, file: str = DEFAULT_DATABASE_FILE):
        if not os.path.exists(file):
            raise FileNotFoundError(f"file does not exist: {file}")
        super().__init__(file=file)

    def rename_track_file(self, src: str, dest: str):
        """
        This renames the file path, and also changes the path in the database to point to the new filename, so that
        the renamed file is not missing in the library.
        """
        # os.rename only raises FileExistsError on Windows; on POSIX it silently overwrites, so check
        # first. A case-only rename is fine: on case-insensitive filesystems dest is then the same file.
        if os.path.exists(dest) and not (os.path.exists(src) and os.path.samefile(src, dest)):
            logger.error(f"File already exists with change: {src}")
            return
        try:
            os.rename(src=src, dst=dest)
            logger.info(f"renamed {src} to {dest}")
        except FileExistsError:
            # can't just do os.path.exists, doesn't pick up case changes for certain filesystems
            logger.error(f"File already exists with change: {src}")
            return
        self.change_track_path(src, dest)
        self.save()

        from serato_tools.crate import Crate

        for crate_path in Crate.get_crate_files():
            crate = Crate(crate_path)
            crate.change_track_path(src, dest)
            crate.save()


if __name__ == "__main__":
    import argparse

    @dataclass
    class Args:
        file: str
        find_missing: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?", default=DatabaseV2.DEFAULT_DATABASE_FILE)
    parser.add_argument("--find_missing", action="store_true", help="List files that do not exist")
    args = Args(**vars(parser.parse_args()))

    db = DatabaseV2(args.file)

    if args.find_missing:
        # TODO: actually look for that missing flag.
        db.find_missing()
    else:
        print(db)
