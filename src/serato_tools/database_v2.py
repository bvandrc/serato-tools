#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import warnings
from dataclasses import dataclass


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

    def get_corrupt_tracks(self) -> dict[str, str]:
        """The full path of each track Serato marked corrupt, with the reason Serato gives, or "" if it gave none."""
        fields = SeratoBinFile.Fields
        corrupt: dict[str, str] = {}
        for track in self.get_tracks():
            if fields.CORRUPT in track.fields and track.get_value(fields.CORRUPT):
                reason = track.get_value(fields.CORRUPT_REASON) if fields.CORRUPT_REASON in track.fields else ""
                corrupt[track.get_full_path()] = str(reason)
        return corrupt

    def rename_track_file(self, src: str, dest: str) -> bool:
        """Deprecated, to be removed in the next major version: use Library.rename_track_file(), which this calls."""
        warnings.warn(
            "DatabaseV2.rename_track_file is deprecated, use Library.rename_track_file instead",
            DeprecationWarning,
            stacklevel=2,
        )
        # imported here since library imports this module
        from serato_tools.library import Library  # pylint: disable=import-outside-toplevel

        library = Library(os.path.dirname(self.filepath), database=self)
        return library.rename_track_file(src, dest)


if __name__ == "__main__":
    import argparse

    @dataclass
    class Args:
        file: str
        find_missing: bool
        list_corrupt: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?", default=DatabaseV2.DEFAULT_DATABASE_FILE)
    parser.add_argument("--find_missing", action="store_true", help="List files that do not exist")
    parser.add_argument("--list_corrupt", action="store_true", help="List tracks Serato marked corrupt, and why")
    args = Args(**vars(parser.parse_args()))

    db = DatabaseV2(args.file)

    if args.find_missing:
        # TODO: actually look for that missing flag.
        db.find_missing()
    elif args.list_corrupt:
        for path, reason in db.get_corrupt_tracks().items():
            print(f"{path}: {reason}")
    else:
        print(db)
