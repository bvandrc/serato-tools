"""The legacy `Serato Markers_` tag: a track's first 5 cues, 9 loops, and color, which `Serato Markers2` also holds."""

import enum
import io
import struct
import sys
from dataclasses import dataclass

from mutagen.mp3 import HeaderNotFoundError

from serato_tools.utils.track_tags import GeobKeys, SeratoGeobTag


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
        self._raw_data: bytes | None
        super().__init__(file_or_data)

        self.entries: list[TrackCuesV1.Entry | TrackCuesV1.Color] = []
        if self._raw_data is not None:
            self.entries = list(self._parse(self._raw_data))

    class Entry:
        """A cue or loop slot, with positions in milliseconds, or None where unset, and its color as RGB bytes."""

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
            for field, value in zip(self.FIELDS, args, strict=True):
                setattr(self, field, value)

        def __repr__(self) -> str:
            return "{name}({data})".format(
                name=self.__class__.__name__,
                data=", ".join(f"{name}={getattr(self, name)!r}" for name in self.FIELDS),
            )

        @classmethod
        def _parse(cls, data: bytes):
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
            for field, value in zip(cls.FIELDS, info, strict=True):
                if field == "start_position_set":
                    if value not in (0x00, 0x7F):
                        raise ValueError(f"start_position_set is 00 or 7f, not {value:02x}")
                    value = value != 0x7F
                    start_position_set = value
                elif field == "end_position_set":
                    if value not in (0x00, 0x7F):
                        raise ValueError(f"end_position_set is 00 or 7f, not {value:02x}")
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

        def _serialize(self):
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
                if field in ("start_position_set", "end_position_set"):
                    value = 0x7F if not value else 0x00
                elif field == "color":
                    value = _encode_bytes_32(value)
                elif field in ("start_position", "end_position"):
                    # an unset position is stored as 7f bytes, as Serato writes it; FORMAT packs the field as 4s, so
                    # it has to be bytes, not the int 0x7F7F7F7F
                    value = b"\x7f\x7f\x7f\x7f" if value is None else _encode_bytes_32(struct.pack(">I", value)[1:])
                elif field == "type":
                    value = int(value)
                entry_data.append(value)
            return struct.pack(self.FORMAT, *entry_data)

    class Color(Entry):
        """The track color, as RGB bytes, which ends the tag."""

        FORMAT = ">4s"
        FIELDS = ("color",)

    def _parse(self, data: bytes):
        # the entry classes' _parse() / _serialize() are internal to this module
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        num_entries = struct.unpack(">I", fp.read(4))[0]
        for _ in range(num_entries):
            entry_data = fp.read(0x16)
            if len(entry_data) != 0x16:
                raise ValueError(f"tag ends partway through an entry: {len(entry_data)} of its 22 bytes")

            entry = TrackCuesV1.Entry._parse(entry_data)  # noqa: SLF001
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
