#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import os
import sys
from dataclasses import dataclass

import mutagen._file
import mutagen.aiff
import mutagen.flac
import mutagen.mp3
import mutagen.mp4
import mutagen.oggvorbis

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.track_tags import SeratoTrack
from serato_tools.utils import logger


def get_serato_tagdata(tagfile: mutagen._file.FileType, decode: bool = False):
    if not tagfile:
        raise Exception("tagfile is None")
    if not tagfile.tags:
        raise Exception("no tags")

    if isinstance(tagfile, (mutagen.mp3.MP3, mutagen.aiff.AIFF)):
        tf = SeratoTrack(tagfile)
        for tagname in tagfile.tags.keys():
            tagname = str(tagname)
            if tagname.startswith("GEOB:Serato"):
                tagvalue = tf._get_geob(tagname.lstrip("GEOB:"))  # pylint: disable=protected-access
                if not tagvalue:
                    raise ValueError(f"no value for {tagname}")
                yield tagname[5:], tagvalue

    elif isinstance(tagfile, (mutagen.flac.FLAC, mutagen.mp4.MP4)):
        for tagname, tagvalue in tagfile.tags.items():  # type: ignore
            tagname = str(tagname)
            if not (tagname.startswith("serato_") or tagname.startswith("----:com.serato.dj:")):
                continue

            tagvalue = tagvalue[0]
            encoded_data: bytes
            if isinstance(tagfile, mutagen.flac.FLAC):
                if not isinstance(tagvalue, str):
                    raise TypeError("unexpected type")
                encoded_data = tagvalue.encode("utf-8")
            else:
                encoded_data = bytes(tagvalue)

            fixed_data: bytes = encoded_data

            length = len(fixed_data.splitlines()[-1])
            if length % 4 == 1:
                fixed_data += b"A=="
            elif length % 4 == 2:
                fixed_data += b"=="
            elif length % 4 == 3:
                fixed_data += b"="
            data = base64.b64decode(fixed_data)

            if not data.startswith(b"application/octet-stream\0"):
                logger.error(f"Failed to parse tag: {tagname}")
                continue
            fieldname_endpos = data.index(b"\0", 26)
            fieldname = data[26:fieldname_endpos].decode()
            fielddata = data[fieldname_endpos + 1 :]
            yield fieldname, fielddata if decode else encoded_data

    elif isinstance(tagfile, mutagen.oggvorbis.OggVorbis):
        for tagname, tagvalue in tagfile.tags.items():  # type: ignore
            tagname = str(tagname)
            tagvalue = tagvalue[0]
            if not tagname.startswith("serato_"):
                continue
            if not isinstance(tagvalue, str):
                raise TypeError("unexpected type")
            yield tagname, tagvalue.encode("utf-8")


if __name__ == "__main__":
    import argparse

    @dataclass
    class Args:
        input_file: str
        output_dir: str | None
        decode: bool

    parser = argparse.ArgumentParser()

    parser.add_argument("input_file")
    parser.add_argument("output_dir", nargs="?")
    parser.add_argument("-d", "--decode", action="store_true")
    args = Args(**vars(parser.parse_args()))

    # pylint: disable-next=protected-access
    tagfile: mutagen._file.FileType | None = mutagen._file.File(args.input_file)

    if not tagfile:
        raise Exception("couldn't parse file")

    for field, value in get_serato_tagdata(tagfile, decode=args.decode):
        log_str = f'field {field} { "decoded " if args.decode else "" }value: {value}'
        if args.output_dir:
            filepath = os.path.join(args.output_dir, f"{field}.octet-stream")
            print(log_str + f" (written to file {filepath})")
            with open(filepath, mode="wb") as fp:
                fp.write(value)
        else:
            print(log_str)
