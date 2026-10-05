#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import enum
import io
import os
import struct
import sys
from dataclasses import dataclass

from mutagen.mp3 import HeaderNotFoundError

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.track_tags import SeratoTag


class TrackCuesV1(SeratoTag):
    GEOB_KEY = "Serato Markers_"
    VERSION = (0x02, 0x05)

    class EntryType(enum.IntEnum):
        INVALID = 0
        CUE = 1
        LOOP = 3

    def __init__(self, file_or_data: SeratoTag.FileOrData):
        self.raw_data: bytes | None
        super().__init__(file_or_data)

        self.entries: list[TrackCuesV1.Entry | TrackCuesV1.Color] = []
        if self.raw_data is not None:
            self.entries = list(self._parse(self.raw_data))

    class Entry(object):
        FORMAT = ">B4sB4s6s4sBB"
        FIELDS = (
            "start_position_set",
            "start_position",
            "end_position_set",
            "end_position",
            "field5",
            "color",
            "type",
            "is_locked",
        )
        type: bytes | str

        def __init__(self, *args):
            assert len(args) == len(self.FIELDS)
            for field, value in zip(self.FIELDS, args):
                setattr(self, field, value)

        def __repr__(self) -> str:
            return "{name}({data})".format(
                name=self.__class__.__name__,
                data=", ".join("{}={!r}".format(name, getattr(self, name)) for name in self.FIELDS),
            )

        @classmethod
        def load(cls, data: bytes):
            def _decode_bytes_32(data: bytes):
                """Decode 4 byte Serato binary format into 3 byte plain text."""
                w, x, y, z = struct.unpack("BBBB", data)
                c = (z & 0x7F) | ((y & 0x01) << 7)
                b = ((y & 0x7F) >> 1) | ((x & 0x03) << 6)
                a = ((x & 0x7F) >> 2) | ((w & 0x07) << 5)
                return struct.pack("BBB", a, b, c)

            info_size = struct.calcsize(cls.FORMAT)
            info = struct.unpack(cls.FORMAT, data[:info_size])
            entry_data = []

            start_position_set = None
            end_position_set = None
            for field, value in zip(cls.FIELDS, info):
                if field == "start_position_set":
                    assert value in (0x00, 0x7F)
                    value = value != 0x7F
                    start_position_set = value
                elif field == "end_position_set":
                    assert value in (0x00, 0x7F)
                    value = value != 0x7F
                    end_position_set = value
                elif field == "start_position":
                    assert start_position_set is not None
                    if start_position_set:
                        assert isinstance(value, bytes)
                        value = struct.unpack(">I", _decode_bytes_32(value).rjust(4, b"\x00"))[0]
                    else:
                        value = None
                elif field == "end_position":
                    assert end_position_set is not None
                    if end_position_set:
                        assert isinstance(value, bytes)
                        value = struct.unpack(">I", _decode_bytes_32(value).rjust(4, b"\x00"))[0]
                    else:
                        value = None
                elif field == "color":
                    assert isinstance(value, bytes)
                    value = _decode_bytes_32(value)
                elif field == "type":
                    value = TrackCuesV1.EntryType(value)
                entry_data.append(value)

            return cls(*entry_data)

        def dump(self):
            def _encode_bytes_32(data: bytes):
                """Encode 3 byte plain text into 4 byte Serato binary format."""
                a, b, c = struct.unpack("BBB", data)
                z = c & 0x7F
                y = ((c >> 7) | (b << 1)) & 0x7F
                x = ((b >> 6) | (a << 2)) & 0x7F
                w = a >> 5
                return bytes(bytearray([w, x, y, z]))

            entry_data = []
            for field in self.FIELDS:
                value = getattr(self, field)
                if field == "start_position_set":
                    value = 0x7F if not value else 0x00
                elif field == "end_position_set":
                    value = 0x7F if not value else 0x00
                elif field == "color":
                    value = _encode_bytes_32(value)
                elif field == "start_position":
                    if value is None:
                        value = 0x7F7F7F7F
                    else:
                        value = _encode_bytes_32(struct.pack(">I", value)[1:])
                elif field == "end_position":
                    if value is None:
                        value = 0x7F7F7F7F
                    else:
                        value = _encode_bytes_32(struct.pack(">I", value)[1:])
                elif field == "type":
                    value = int(value)
                entry_data.append(value)
            return struct.pack(self.FORMAT, *entry_data)

    class Color(Entry):
        FORMAT = ">4s"
        FIELDS = ("color",)

    def _parse(self, data: bytes):
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        num_entries = struct.unpack(">I", fp.read(4))[0]
        for i in range(num_entries):  # pylint: disable=unused-variable
            entry_data = fp.read(0x16)
            assert len(entry_data) == 0x16

            entry = TrackCuesV1.Entry.load(entry_data)
            yield entry

        yield TrackCuesV1.Color.load(fp.read())

    def delete(self):
        was_deleted = super().delete()
        self.entries = []
        return was_deleted

    def _dump(self):
        entries = self.entries
        # the trailing Color entry doubles as the format's footer: it is not counted in num_entries,
        # so dumping without it (or with it anywhere else) would write a tag Serato cannot parse
        if not entries or not isinstance(entries[-1], TrackCuesV1.Color):
            raise ValueError("last entry must be a Color entry, cannot dump")
        if any(isinstance(e, TrackCuesV1.Color) for e in entries[:-1]):
            raise ValueError("only the last entry may be a Color entry, cannot dump")
        data = self._pack_version()
        num_entries = len(entries) - 1
        data += struct.pack(">I", num_entries)
        for entry_data in entries:
            data += entry_data.dump()
        self.raw_data = data


if __name__ == "__main__":
    import argparse
    import ast
    import configparser
    import math
    import subprocess
    import tempfile

    from serato_tools.utils.ui import get_hex_editor, get_text_editor, ui_ask

    @dataclass
    class Args:
        file: str
        edit: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("-e", "--edit", action="store_true")
    args = Args(**vars(parser.parse_args()))

    try:
        tags = TrackCuesV1(args.file)
    except HeaderNotFoundError:
        with open(args.file, mode="rb") as fp:
            data = fp.read()
        tags = TrackCuesV1(data)

    if args.edit:
        text_editor = get_text_editor()
        hex_editor = get_hex_editor()

    entries: list[TrackCuesV1.Entry] = tags.entries
    new_entries: list[TrackCuesV1.Entry] = []
    width = math.floor(math.log10(len(entries))) + 1 if entries else 1
    action: str | None = None
    for entry_index, entry in enumerate(entries):
        if args.edit:
            if action not in ("q", "_"):
                print("{:{}d}: {!r}".format(entry_index, width, entry))
                action = ui_ask(
                    "Edit this entry",
                    {
                        "y": "edit this entry",
                        "n": "do not edit this entry",
                        "q": "quit; do not edit this entry or any of the remaining ones",
                        "a": "edit this entry and all later entries in the file",
                        "b": "edit raw bytes",
                        "r": "remove this entry",
                    },
                    default="n",
                )

            if action in ("y", "a", "b"):
                while True:
                    with tempfile.NamedTemporaryFile() as f:
                        if action == "b":
                            f.write(entry.dump())
                            editor = hex_editor  # pyright: ignore[reportPossiblyUnboundVariable]
                        else:
                            if action == "a":
                                entries_to_edit = (
                                    (
                                        "{:{}d}: {}".format(
                                            i,
                                            width,
                                            (repr(e.type) if e.__class__ == TrackCuesV1.Entry else "Color"),
                                        ),
                                        e,
                                    )
                                    for i, e in enumerate(entries[entry_index:], start=entry_index)
                                )
                            else:
                                entries_to_edit = (
                                    (
                                        (repr(entry.type) if entry.__class__ == TrackCuesV1.Entry else "Color"),
                                        entry,
                                    ),
                                )

                            for section, e in entries_to_edit:
                                f.write("[{}]\n".format(section).encode())
                                for field in e.FIELDS:
                                    value = getattr(e, field)
                                    if field == "type":
                                        value = int(value)
                                    f.write(
                                        "{}: {!r}\n".format(
                                            field,
                                            value,
                                        ).encode()
                                    )
                                f.write(b"\n")
                            editor = text_editor  # pyright: ignore[reportPossiblyUnboundVariable]
                        f.flush()
                        status = subprocess.call((editor, f.name))
                        f.seek(0)
                        output = f.read()

                    if status != 0:
                        if (
                            ui_ask(
                                "Command failed, retry",
                                {
                                    "y": "edit again",
                                    "n": "leave unchanged",
                                },
                            )
                            == "n"
                        ):
                            break
                    else:
                        try:
                            if action != "b":
                                cp = configparser.ConfigParser()
                                cp.read_string(output.decode())
                                sections = tuple(sorted(cp.sections()))
                                if action != "a":
                                    assert len(sections) == 1

                                results = []
                                for section in sections:
                                    l, s, r = section.partition(": ")
                                    name = r if s else l
                                    cls = TrackCuesV1.Color if name == "Color" else TrackCuesV1.Entry
                                    e = cls(
                                        *(
                                            ast.literal_eval(
                                                cp.get(section, field),
                                            )
                                            for field in cls.FIELDS
                                        )
                                    )
                                    results.append(cls.load(e.dump()))
                            else:
                                results = [entry.load(output)]
                        except Exception as e:  # pylint: disable=broad-exception-caught
                            print(str(e))
                            if (
                                ui_ask(
                                    "Content seems to be invalid, retry",
                                    {
                                        "y": "edit again",
                                        "n": "leave unchanged",
                                    },
                                )
                                == "n"
                            ):
                                break
                        else:
                            for i, e in enumerate(results, start=entry_index):
                                print("{:{}d}: {!r}".format(i, width, e))
                            subaction = ui_ask(
                                "Above content is valid, save changes",
                                {
                                    "y": "save current changes",
                                    "n": "discard changes",
                                    "e": "edit again",
                                },
                                default="y",
                            )
                            if subaction == "y":
                                new_entries.extend(results)
                                if action == "a":
                                    action = "_"
                                break
                            elif subaction == "n":
                                if action == "a":
                                    action = "q"
                                new_entries.append(entry)
                                break
            elif action in ("r", "_"):
                continue
            else:
                new_entries.append(entry)
        else:
            print("{:{}d}: {!r}".format(entry_index, width, entry))

    if args.edit:
        if new_entries == entries:
            print("No changes made.")
        else:
            tags.entries = new_entries
            tags._dump()  # pylint: disable=protected-access
            if tags.tagfile:
                tags.save()
            else:
                with open(args.file, mode="wb") as fp:
                    fp.write(tags.raw_data or b"")
