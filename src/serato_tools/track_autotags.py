#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io
import os
import sys
from typing import Optional
from dataclasses import dataclass

from mutagen.mp3 import HeaderNotFoundError

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.track_tags import SeratoTag
from serato_tools.utils import logger


class TrackAutotags(SeratoTag):
    GEOB_KEY = "Serato Autotags"
    VERSION = (0x01, 0x01)

    def __init__(self, file_or_data: SeratoTag.FileOrData):
        self.raw_data: bytes | None = None
        super().__init__(file_or_data)

        self.bpm: float | None = None
        self.autogain: float | None = None
        self.gaindb: float | None = None

        if self.raw_data is not None:
            self.bpm, self.autogain, self.gaindb = self._parse(self.raw_data)

    def __str__(self) -> str:
        return f"bpm: {self.bpm}\nautogain: {self.autogain}\ngaindb: {self.gaindb}"

    def _parse(self, data: bytes):
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        def get_value():
            value = self._readbytes(fp).decode("ascii")
            return float(value)

        bpm = get_value()
        autogain = get_value()
        gaindb = get_value()
        return bpm, autogain, gaindb

    def _dump(self):
        if self.bpm is None or self.autogain is None or self.gaindb is None:
            raise ValueError(
                "bpm, autogain, and gaindb must all be set before dumping (file had no existing Serato Autotags tag)"
            )
        data: bytes = self._pack_version()
        for value, decimals in ((self.bpm, 2), (self.autogain, 3), (self.gaindb, 3)):
            data += "{:.{}f}".format(value, decimals).encode("ascii")
            data += b"\x00"
        self.raw_data = data

    def set(
        self,
        bpm: Optional[float] = None,
        autogain: Optional[float] = None,
        gaindb: Optional[float] = None,
    ):
        if bpm is not None:
            self.bpm = bpm
        if autogain is not None:
            self.autogain = autogain
        if gaindb is not None:
            self.gaindb = gaindb
        self._dump()


if __name__ == "__main__":
    import argparse
    import configparser
    import subprocess
    import tempfile

    from serato_tools.utils.ui import get_text_editor

    @dataclass
    class Args:
        file: str
        edit: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("-e", "--edit", action="store_true")
    args = Args(**vars(parser.parse_args()))

    try:
        tags = TrackAutotags(args.file)
    except HeaderNotFoundError:
        with open(args.file, mode="rb") as fp:
            data = fp.read()
        tags = TrackAutotags(data)

    if args.edit:
        editor = get_text_editor()

        with tempfile.NamedTemporaryFile() as f:
            f.write(str(tags).encode("ascii"))
            f.flush()
            status = subprocess.call((editor, f.name))
            f.seek(0)
            output = f.read()

        if status != 0:
            ERROR_STR = f"Command executation failed with status: {status}"
            print(ERROR_STR, file=sys.stderr)
            logger.error(ERROR_STR)
            raise Exception(ERROR_STR)

        cp = configparser.ConfigParser()
        try:
            SECTION = "Autotags"
            cp.read_string(f"[{SECTION}]\n" + output.decode())
            bpm = cp.getfloat(SECTION, "bpm")
            autogain = cp.getfloat(SECTION, "autogain")
            gaindb = cp.getfloat(SECTION, "gaindb")
        except Exception:
            ERROR_STR = "Invalid input, no changes made"
            print(ERROR_STR, file=sys.stderr)
            logger.error(ERROR_STR)
            raise

        tags.set(bpm=bpm, autogain=autogain, gaindb=gaindb)
        if tags.tagfile:
            tags.save()
        else:
            with open(args.file, mode="wb") as fp:
                fp.write(tags.raw_data or b"")
    else:
        print(str(tags))
