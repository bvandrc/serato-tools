#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The legacy `Serato Markers_` tag: a track's first 5 cues, 9 loops, and color, which `Serato Markers2` also holds."""

import enum
import io
import struct
import sys
from dataclasses import dataclass
from typing import ClassVar

from mutagen.mp3 import HeaderNotFoundError

from serato_tools.utils.track_tags import GeobKeys, SeratoGeobTag


def _decode_bytes_32(data: bytes) -> bytes:
    """3 bytes, from the 4 Serato stores them as, 7 bits to a byte."""
    w, x, y, z = struct.unpack("BBBB", data)
    c = (z & 0x7F) | ((y & 0x01) << 7)
    b = ((y & 0x7F) >> 1) | ((x & 0x03) << 6)
    a = ((x & 0x7F) >> 2) | ((w & 0x07) << 5)
    return struct.pack("BBB", a, b, c)


def _encode_bytes_32(data: bytes) -> bytes:
    """3 bytes as the 4 Serato stores them, 7 bits to a byte."""
    a, b, c = struct.unpack("BBB", data)
    z = c & 0x7F
    y = ((c >> 7) | (b << 1)) & 0x7F
    x = ((b >> 6) | (a << 2)) & 0x7F
    w = a >> 5
    return bytes([w, x, y, z])


def _parse_position_set(field: str, value: int) -> bool:
    """Whether a slot's position is set: Serato stores 00 for set, and 7f for unset."""
    if value not in (0x00, 0x7F):
        raise ValueError(f"{field} is 00 or 7f, not {value:02x}")
    return value != 0x7F


def _serialize_position_set(is_set: bool) -> int:
    return 0x00 if is_set else 0x7F


def _parse_position(data: bytes) -> int:
    """A position in milliseconds, from its 4 stored bytes."""
    return struct.unpack(">I", _decode_bytes_32(data).rjust(4, b"\x00"))[0]


def _serialize_position(position: int | None) -> bytes:
    """A position's 4 stored bytes: 7f bytes for an unset one, as Serato writes it."""
    return b"\x7f\x7f\x7f\x7f" if position is None else _encode_bytes_32(struct.pack(">I", position)[1:])


class TrackCuesV1(SeratoGeobTag):
    """The legacy `Serato Markers_` tag.

    It holds slots for the first 5 cues and 9 loops, then the track color.

    Current Serato reads `Serato Markers2` (`TrackCuesV2`), but a stale copy of this tag can shadow changes to it.
    """

    GEOB_KEY = GeobKeys.CUES_V1
    VERSION = (0x02, 0x05)

    @enum.unique
    class EntryType(enum.IntEnum):
        """Whether a slot holds a cue, a loop, or nothing (`INVALID`)."""

        INVALID = 0
        CUE = 1
        LOOP = 3

    def __init__(self, file_or_data: SeratoGeobTag.FileOrData):
        super().__init__(file_or_data)

        self.entries: list[TrackCuesV1.Entry | TrackCuesV1.Color] = []
        if self._raw_data is not None:
            self.entries = list(self._parse(self._raw_data))

    class _EntryRepr:
        """Mixin for a repr of the entry's `FIELDS`, named by the class alone, as `Entry(...)`."""

        FIELDS: ClassVar[tuple[str, ...]]

        def __repr__(self) -> str:
            return "{}({})".format(
                type(self).__name__, ", ".join("{}={!r}".format(f, getattr(self, f)) for f in self.FIELDS)
            )

    @dataclass(repr=False)
    class Entry(_EntryRepr):
        """A cue or loop slot, with positions in milliseconds, or None where unset, and its color as RGB bytes."""

        start_position_set: bool
        start_position: int | None
        end_position_set: bool
        end_position: int | None
        field5: bytes
        color: bytes
        type: "TrackCuesV1.EntryType"
        is_locked: int
        FORMAT: ClassVar[str] = ">B4sB4s6s4sBB"
        FIELDS: ClassVar[tuple[str, ...]] = (
            "start_position_set",
            "start_position",
            "end_position_set",
            "end_position",
            "field5",
            "color",
            "type",
            "is_locked",
        )

        @classmethod
        def _parse(cls, data: bytes):
            start_set, start, end_set, end, field5, color, entry_type, is_locked = struct.unpack(
                cls.FORMAT, data[: struct.calcsize(cls.FORMAT)]
            )
            start_position_set = _parse_position_set("start_position_set", start_set)
            end_position_set = _parse_position_set("end_position_set", end_set)
            return cls(
                start_position_set,
                _parse_position(start) if start_position_set else None,
                end_position_set,
                _parse_position(end) if end_position_set else None,
                field5,
                _decode_bytes_32(color),
                TrackCuesV1.EntryType(entry_type),
                is_locked,
            )

        def _serialize(self):
            return struct.pack(
                self.FORMAT,
                _serialize_position_set(self.start_position_set),
                _serialize_position(self.start_position),
                _serialize_position_set(self.end_position_set),
                _serialize_position(self.end_position),
                self.field5,
                _encode_bytes_32(self.color),
                int(self.type),
                self.is_locked,
            )

    @dataclass(repr=False)
    class Color(_EntryRepr):
        """The track color, as RGB bytes, which ends the tag."""

        color: bytes
        FORMAT: ClassVar[str] = ">4s"
        FIELDS: ClassVar[tuple[str, ...]] = ("color",)

        @classmethod
        def _parse(cls, data: bytes):
            (color,) = struct.unpack(cls.FORMAT, data[: struct.calcsize(cls.FORMAT)])
            return cls(_decode_bytes_32(color))

        def _serialize(self):
            return struct.pack(self.FORMAT, _encode_bytes_32(self.color))

    def _parse(self, data: bytes):
        # the entry classes' _parse() / _serialize() are internal to this module
        # pylint: disable=protected-access
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        num_entries = struct.unpack(">I", fp.read(4))[0]
        for _ in range(num_entries):
            entry_data = fp.read(0x16)
            if len(entry_data) != 0x16:
                raise ValueError(f"tag ends partway through an entry: {len(entry_data)} of its 22 bytes")

            entry = TrackCuesV1.Entry._parse(entry_data)
            yield entry

        yield TrackCuesV1.Color._parse(fp.read())

    def delete(self):
        """Deletes the tag in memory, returning whether the file had it; call `save()` to write the deletion."""
        was_deleted = super().delete()
        self.entries = []
        return was_deleted

    def _serialize(self):
        # the entry classes' _parse() / _serialize() are internal to this module
        # pylint: disable=protected-access
        entries = self.entries
        # the trailing Color entry doubles as the format's footer: it is not counted in num_entries,
        # so serializing without it (or with it anywhere else) would write a tag Serato cannot parse
        if not entries or not isinstance(entries[-1], TrackCuesV1.Color):
            raise ValueError("last entry must be a Color entry, cannot serialize")
        if any(isinstance(e, TrackCuesV1.Color) for e in entries[:-1]):
            raise ValueError("only the last entry may be a Color entry, cannot serialize")
        data = self._pack_version()
        num_entries = len(entries) - 1
        data += struct.pack(">I", num_entries)
        for entry_data in entries:
            data += entry_data._serialize()
        self._raw_data = data


if __name__ == "__main__":
    # this script is part of the module, so it uses the tag's and its entries' internal _parse() / _serialize()
    # pylint: disable=protected-access
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

    entries = tags.entries
    if not entries:
        # a parsed tag always has at least the trailing Color entry, so empty means the tag is not set
        print(f'File has no "{TrackCuesV1.GEOB_KEY}" tag.')
        sys.exit()
    new_entries: list[TrackCuesV1.Entry | TrackCuesV1.Color] = []
    width = math.floor(math.log10(len(entries))) + 1
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
                            f.write(entry._serialize())
                            editor = hex_editor  # pyright: ignore[reportPossiblyUnboundVariable]
                        else:
                            if action == "a":
                                entries_to_edit = (
                                    (
                                        "{:{}d}: {}".format(
                                            i,
                                            width,
                                            (repr(e.type) if isinstance(e, TrackCuesV1.Entry) else "Color"),
                                        ),
                                        e,
                                    )
                                    for i, e in enumerate(entries[entry_index:], start=entry_index)
                                )
                            else:
                                entries_to_edit = (
                                    (
                                        (repr(entry.type) if isinstance(entry, TrackCuesV1.Entry) else "Color"),
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
                                if action != "a" and len(sections) != 1:
                                    raise ValueError(f"expected exactly one entry, got {len(sections)}")

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
                                    results.append(cls._parse(e._serialize()))
                            else:
                                results = [entry._parse(output)]
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
            tags._serialize()
            if tags.tagfile:
                tags.save()
            else:
                with open(args.file, mode="wb") as fp:
                    fp.write(tags._raw_data or b"")  # pylint: disable=protected-access
