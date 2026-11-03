#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import warnings
from dataclasses import dataclass

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils import SERATO_DIR


class DatabaseV2(SeratoBinFile):
    TESTED_VERSIONS = frozenset({"2.0/Serato Scratch LIVE Database"})
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
        """Deprecated, to be removed in the next major version: use Library.rename_track_file(), which this calls."""
        warnings.warn(
            "DatabaseV2.rename_track_file is deprecated, use Library.rename_track_file instead",
            DeprecationWarning,
            stacklevel=2,
        )
        # imported here since library imports this module
        from serato_tools.library import Library  # pylint: disable=import-outside-toplevel

        # pyright sees this file as src.serato_tools.database_v2 but library's import as serato_tools.database_v2,
        # two names for the same class
        library = Library(os.path.dirname(self.filepath), database=self)  # pyright: ignore[reportArgumentType]
        library.rename_track_file(src, dest)


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
