"""The legacy `Serato Markers_` tag: a track's first 5 cues, 9 loops, and color, which `Serato Markers2` also holds."""

import enum
import io
import struct
import sys
from dataclasses import dataclass

from mutagen.mp3 import HeaderNotFoundError

from serato_tools.utils.track_tags import GeobKeys, SeratoGeobTag

# the bytes Serato writes for a position that isn't set
_NO_POSITION = b"\x7f\x7f\x7f\x7f"
# the bytes Serato writes in every entry's field5, whose meaning is unknown
_FIELD5 = b"\x00\x7f\x7f\x7f\x7f\x7f"
# Serato always writes this many cue entries, then this many loop entries, whether they're set or not
_NUM_CUES = 5
_NUM_LOOPS = 9


def _unpack_exactly(fmt: str, data: bytes, name: str) -> tuple:
    """`data` unpacked as `fmt`; raises ValueError, naming the `name` entry, unless it's exactly `fmt`'s size."""
    if len(data) != (size := struct.calcsize(fmt)):
        raise ValueError(f"{name} entry is {len(data)} bytes, not {size}")
    return struct.unpack(fmt, data)


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
    # bytes, not the int 0x7F7F7F7F, since FORMAT packs the field as 4s
    return _NO_POSITION if position is None else _encode_bytes_32(struct.pack(">I", position)[1:])


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

    class Entry:
        """A cue or loop slot, with positions in milliseconds, or None where unset, and its color as RGB bytes."""

        start_position_set: bool
        start_position: int | None
        end_position_set: bool
        end_position: int | None
        field5: bytes
        color: bytes
        type: "TrackCuesV1.EntryType"
        is_locked: int
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

        def __init__(self, *args):
            for field, value in zip(self.FIELDS, args, strict=True):
                setattr(self, field, value)

        def __repr__(self) -> str:
            return "{name}({data})".format(
                name=self.__class__.__name__,
                data=", ".join(f"{name}={getattr(self, name)!r}" for name in self.FIELDS),
            )

        @classmethod
        def _parse(cls, data: bytes):
            start_set, start, end_set, end, field5, color, entry_type, is_locked = _unpack_exactly(
                cls.FORMAT, data, cls.__name__
            )
            # every tag Serato DJ Pro 2 was seen writing passes these checks, so a tag that doesn't is one this class
            # may not understand, and rewriting it could corrupt it. Mixxx's parser checks the same fields, with
            # comments on them: https://github.com/mixxxdj/mixxx/blob/main/src/track/serato/markers.cpp
            for name, position_set, position in (("start_position", start_set, start), ("end_position", end_set, end)):
                if position_set == 0x7F and position != _NO_POSITION:
                    raise ValueError(f"unset {name} isn't {_NO_POSITION!r}: {position!r}")
            if field5 != _FIELD5:
                raise ValueError(f"field5 isn't {_FIELD5!r}: {field5!r}")
            if is_locked and entry_type != TrackCuesV1.EntryType.LOOP:
                raise ValueError("only a loop can be locked")
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

    class Color(Entry):
        """The track color, as RGB bytes, which ends the tag."""

        FORMAT = ">4s"
        FIELDS = ("color",)

        @classmethod
        def _parse(cls, data: bytes):
            (color,) = _unpack_exactly(cls.FORMAT, data, cls.__name__)
            return cls(_decode_bytes_32(color))

        def _serialize(self):
            return struct.pack(self.FORMAT, _encode_bytes_32(self.color))

    def _parse(self, data: bytes):
        # the entry classes' _parse() / _serialize() are internal to this module
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        num_entries = struct.unpack(">I", fp.read(4))[0]
        if num_entries != _NUM_CUES + _NUM_LOOPS:
            raise ValueError(f"tag has {num_entries} entries, not {_NUM_CUES + _NUM_LOOPS}")
        for i in range(num_entries):
            entry_data = fp.read(0x16)
            if len(entry_data) != 0x16:
                raise ValueError(f"tag ends partway through an entry: {len(entry_data)} of its 22 bytes")

            entry = TrackCuesV1.Entry._parse(entry_data)  # noqa: SLF001
            # an unset cue has type INVALID, but an unset loop keeps type LOOP
            if i < _NUM_CUES and entry.type not in (TrackCuesV1.EntryType.INVALID, TrackCuesV1.EntryType.CUE):
                raise ValueError(f"entry {i} should be a cue, but has type {entry.type!r}")
            if i >= _NUM_CUES and entry.type != TrackCuesV1.EntryType.LOOP:
                raise ValueError(f"entry {i} should be a loop, but has type {entry.type!r}")
            yield entry

        yield TrackCuesV1.Color._parse(fp.read())  # noqa: SLF001

    def delete(self):
        """Deletes the tag in memory, returning whether the file had it; call `save()` to write the deletion."""
        was_deleted = super().delete()
        self.entries = []
        return was_deleted

    def _serialize(self):
        # the entry classes' _parse() / _serialize() are internal to this module
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
            data += entry_data._serialize()  # noqa: SLF001
        self._raw_data = data


if __name__ == "__main__":
    # ruff: disable[T201]
    import argparse
    import math

    @dataclass
    class Args:
        file: str

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = Args(**vars(parser.parse_args()))

    try:
        tags = TrackCuesV1(args.file)
    except HeaderNotFoundError:
        with open(args.file, mode="rb") as fp:
            data = fp.read()
        tags = TrackCuesV1(data)

    entries: list[TrackCuesV1.Entry] = tags.entries
    if not entries:
        # a parsed tag always has at least the trailing Color entry, so empty means the tag is not set
        print(f'File has no "{TrackCuesV1.GEOB_KEY}" tag.')
        sys.exit()
    width = math.floor(math.log10(len(entries))) + 1
    for entry_index, entry in enumerate(entries):
        print("{:{}d}: {!r}".format(entry_index, width, entry))
    # ruff: enable[T201]
