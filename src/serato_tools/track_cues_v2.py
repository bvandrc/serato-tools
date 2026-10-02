#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ast
import base64
import configparser
import io
import os
import struct
import sys
from typing import Callable, ClassVar, Sequence
from enum import Enum
import dataclasses
from dataclasses import dataclass, field


from mutagen.mp3 import HeaderNotFoundError

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.utils import get_enum_key_from_value
from serato_tools.utils.track_tags import SeratoTag
from serato_tools.track_beatgrid import TrackBeatgrid


class TrackCuesV2(SeratoTag):
    GEOB_KEY = "Serato Markers2"
    VERSION = (0x01, 0x01)

    class CueColors(Enum):
        RED = b"\xcc\x00\x00"
        ORANGE = b"\xcc\x44\x00"
        YELLOWORANGE = b"\xcc\x88\x00"
        YELLOW = b"\xcc\xcc\x00"
        LIMEGREEN1 = b"\x88\xcc\x00"
        DARKGREEN = b"\x44\xcc\x00"
        LIMEGREEN2 = b"\x00\xcc\x00"
        LIMEGREEN3 = b"\x00\xcc\x88"
        SEAFOAM = b"\x00\xcc\x88"
        CYAN = b"\x00\xcc\xcc"
        LIGHTBLUE = b"\x00\x88\xcc"
        BLUE1 = b"\x00\x44\xcc"
        BLUE2 = b"\x00\x00\xcc"
        PURPLE1 = b"\x44\x00\xcc"
        PURPLE2 = b"\x88\x00\xcc"
        PINK = b"\xcc\x00\xcc"
        MAGENTA = b"\xcc\x00\x88"
        PINKRED = b"\xcc\x00\x44"

    class TrackColors(Enum):
        PINK = b"\xff\x99\xff"
        DARKPINK = b"\xff\x99\xdd"
        PINKRED = b"\xff\x99\xbb"
        RED = b"\xff\x99\x99"
        ORANGE = b"\xff\xbb\x99"
        YELLOWORANGE = b"\xff\xdd\x99"
        YELLOW = b"\xff\xff\x99"
        LIMEGREEN1 = b"\xdd\xff\x99"
        LIMEGREEN2 = b"\xbb\xff\x99"
        LIMEGREEN3 = b"\x99\xff\x99"
        LIMEGREEN4 = b"\x99\xff\xbb"
        SEAFOAM = b"\x99\xff\xdd"
        CYAN = b"\x99\xff\xff"
        LIGHTBLUE = b"\x99\xdd\xff"
        BLUE1 = b"\x99\xbb\xff"
        BLUE2 = b"\x99\x99\xff"
        PURPLE = b"\xbb\x99\xff"
        MAGENTA = b"\xdd\x99\xff"
        WHITE = b"\xff\xff\xff"
        GREY = b"\xbb\xbb\xbb"
        BLACK = b"\x99\x99\x99"

    def __init__(self, file_or_data: SeratoTag.FileOrData):
        self.raw_data: bytes | None = None
        super().__init__(file_or_data)

        self.entries: list[TrackCuesV2.Entry] = []
        if self.raw_data is not None:
            self.entries = list(self._parse(self.raw_data))
        self.modified: bool = False

        self.beatgrid: TrackBeatgrid | None = None

    def __str__(self) -> str:
        return "\n".join(str(entry) for entry in self.entries)

    @staticmethod
    def _get_cue_color_key(value: bytes) -> str:
        return get_enum_key_from_value(value, TrackCuesV2.CueColors)

    @staticmethod
    def _get_track_color_key(value: bytes) -> str:
        return get_enum_key_from_value(value, TrackCuesV2.TrackColors)

    @staticmethod
    def _get_entry_class(entry_name: str):
        return next(
            (
                cls
                for cls in (
                    TrackCuesV2.BpmLockEntry,
                    TrackCuesV2.ColorEntry,
                    TrackCuesV2.CueEntry,
                    TrackCuesV2.LoopEntry,
                    TrackCuesV2.FlipEntry,
                )
                if cls.NAME == entry_name
            ),
            TrackCuesV2.UnknownEntry,
        )

    class _EntryRepr:
        """Mixin that provides the old Entry-style __repr__ (FIELDS order)."""

        FIELDS: ClassVar[tuple[str, ...]]

        def __repr__(self) -> str:
            return "{}({})".format(
                type(self).__qualname__,
                ", ".join("{}={!r}".format(f, getattr(self, f)) for f in type(self).FIELDS),
            )

    @dataclass(repr=False)
    class UnknownEntry(_EntryRepr):
        """Unknown/opaque entry."""

        data: bytes
        NAME: ClassVar[str | None] = None
        FIELDS: ClassVar[tuple[str, ...]] = ("data",)

        @classmethod
        def load(cls, data: bytes) -> "TrackCuesV2.UnknownEntry":
            return cls(data=data)

        def dump(self) -> bytes:
            return self.data

    @dataclass(repr=False)
    class BpmLockEntry(_EntryRepr):
        """BPM lock state."""

        enabled: bool
        NAME: ClassVar[str] = "BPMLOCK"
        FIELDS: ClassVar[tuple[str, ...]] = ("enabled",)
        _FORMAT: ClassVar[str] = "?"

        @classmethod
        def load(cls, data: bytes) -> "TrackCuesV2.BpmLockEntry":
            return cls(*struct.unpack(cls._FORMAT, data))

        def dump(self) -> bytes:
            return struct.pack(self._FORMAT, self.enabled)

    @dataclass(repr=False)
    class ColorEntry(_EntryRepr):
        """Track color."""

        field1: bytes
        color: bytes
        NAME: ClassVar[str] = "COLOR"
        FIELDS: ClassVar[tuple[str, ...]] = ("field1", "color")
        _FORMAT: ClassVar[str] = "c3s"

        @classmethod
        def load(cls, data: bytes) -> "TrackCuesV2.ColorEntry":
            return cls(*struct.unpack(cls._FORMAT, data))

        def dump(self) -> bytes:
            return struct.pack(self._FORMAT, self.field1, self.color)

    @dataclass(repr=False)
    class CueEntry(_EntryRepr):
        """Cue (hot cue)."""

        field1: bytes
        index: int
        position: int  # milliseconds
        field4: bytes
        color: bytes
        field6: bytes
        name: str
        NAME: ClassVar[str] = "CUE"
        FIELDS: ClassVar[tuple[str, ...]] = (
            "field1",
            "index",
            "position",  # in milliseconds
            "field4",
            "color",
            "field6",
            "name",
        )
        _FORMAT: ClassVar[str] = ">cBIc3s2s"

        @classmethod
        def load(cls, data: bytes) -> "TrackCuesV2.CueEntry":
            info_size = struct.calcsize(cls._FORMAT)
            field1, index, position, field4, color, field6 = struct.unpack(cls._FORMAT, data[:info_size])
            name, nullbyte, other = data[info_size:].partition(b"\x00")
            assert nullbyte == b"\x00"
            assert other == b""
            return cls(field1, index, position, field4, color, field6, name.decode("utf-8"))

        def dump(self) -> bytes:
            position = max(0, min(self.position, 0xFFFFFFFF))
            return b"".join(
                (
                    struct.pack(
                        self._FORMAT,
                        self.field1,
                        self.index,
                        position,
                        self.field4,
                        self.color,
                        self.field6,
                    ),
                    self.name.encode("utf-8"),
                    b"\x00",
                )
            )

    @dataclass(repr=False)
    class LoopEntry(_EntryRepr):
        """Loop/hot cue loop."""

        field1: bytes
        index: int
        startposition: int  # milliseconds
        endposition: int  # milliseconds
        field5: bytes
        field6: bytes
        color: bytes
        locked: bool
        name: str
        NAME: ClassVar[str] = "LOOP"
        FIELDS: ClassVar[tuple[str, ...]] = (
            "field1",
            "index",
            "startposition",
            "endposition",
            "field5",
            "field6",
            "color",
            "locked",
            "name",
        )
        _FORMAT: ClassVar[str] = ">cBII4s4sB?"

        @classmethod
        def load(cls, data: bytes) -> "TrackCuesV2.LoopEntry":
            info_size = struct.calcsize(cls._FORMAT)
            (
                field1,
                index,
                startposition,
                endposition,
                field5,
                field6,
                color,
                locked,
            ) = struct.unpack(cls._FORMAT, data[:info_size])
            name, nullbyte, other = data[info_size:].partition(b"\x00")
            assert nullbyte == b"\x00"
            assert other == b""
            return cls(field1, index, startposition, endposition, field5, field6, color, locked, name.decode("utf-8"))

        def dump(self) -> bytes:
            startposition = max(0, min(self.startposition, 0xFFFFFFFF))
            endposition = max(0, min(self.endposition, 0xFFFFFFFF))
            return b"".join(
                (
                    struct.pack(
                        self._FORMAT,
                        self.field1,
                        self.index,
                        startposition,
                        endposition,
                        self.field5,
                        self.field6,
                        self.color,
                        self.locked,
                    ),
                    self.name.encode("utf-8"),
                    b"\x00",
                )
            )

    @dataclass(repr=False)
    class FlipEntry(_EntryRepr):
        """Flip (performance) entry. Stored as opaque bytes (Serato does not implement dump)."""

        _raw_data: bytes
        NAME: ClassVar[str] = "FLIP"
        FIELDS: ClassVar[tuple[str, ...]] = ("_raw_data",)

        @classmethod
        def load(cls, data: bytes) -> "TrackCuesV2.FlipEntry":
            return cls(_raw_data=data)

        def dump(self) -> bytes:
            return self._raw_data

    type Entry = UnknownEntry | BpmLockEntry | ColorEntry | CueEntry | LoopEntry | FlipEntry

    def _parse(self, data: bytes):
        self._check_version(data[: self.VERSION_LEN])
        data = data[self.VERSION_LEN :]  # b64data
        try:
            end_index = data.index(b"\x00")
            data = data[:end_index]
        except ValueError:
            pass  # data = data
        data = data.replace(b"\n", b"")
        padding = b"A==" if len(data) % 4 == 1 else (b"=" * (-len(data) % 4))
        payload = base64.b64decode(data + padding)
        fp = io.BytesIO(payload)
        self._check_version(fp.read(self.VERSION_LEN))
        num_entries = 0
        MAX_PARSE_ENTRIES = 100
        while True:
            if num_entries >= MAX_PARSE_ENTRIES:
                raise ValueError(f"cue payload has more than {MAX_PARSE_ENTRIES} entries; malformed or unsupported")
            entry_name = SeratoTag._readbytes(fp).decode("utf-8")
            if not entry_name:
                break
            entry_len = struct.unpack(">I", fp.read(4))[0]
            assert entry_len > 0

            entry_class = TrackCuesV2._get_entry_class(entry_name)
            yield entry_class.load(fp.read(entry_len))
            num_entries += 1

    def _dump(self):
        version = self._pack_version()

        contents: list[bytes] = [version]
        for entry in self.entries:
            data = entry.dump()
            if entry.NAME is not None:
                data = b"".join(
                    (
                        entry.NAME.encode("utf-8"),
                        b"\x00",
                        struct.pack(">I", (len(data))),
                        data,
                    )
                )
            contents.append(data)

        payload = b"".join(contents)
        payload_base64 = bytearray(base64.b64encode(payload).replace(b"=", b"A"))

        MAX_LINE_WRAPS = 10_000
        wrap_count = 0
        i = 72
        while i < len(payload_base64):
            if wrap_count >= MAX_LINE_WRAPS:
                raise ValueError(
                    f"base64 payload line wrapping exceeded {MAX_LINE_WRAPS} iterations; payload too large or malformed"
                )
            wrap_count += 1
            payload_base64.insert(i, 0x0A)
            i += 73

        data = version
        data += payload_base64

        new_raw_data = data.ljust(470, b"\x00")

        self.modified = new_raw_data != self.raw_data  # pylint: disable=access-member-before-definition
        self.raw_data = new_raw_data

    @staticmethod
    def parse_entries_file(contents: str, assert_len_1: bool):
        cp = configparser.ConfigParser()
        cp.read_string(contents)
        sections: Sequence[str] = tuple(sorted(cp.sections()))
        if assert_len_1:
            assert len(sections) == 1

        results: list[TrackCuesV2.Entry] = []
        for section in sections:
            l, s, r = section.partition(": ")
            entry_class = TrackCuesV2._get_entry_class(r if s else l)

            e = entry_class(
                *(
                    ast.literal_eval(
                        cp.get(section, field),
                    )
                    for field in entry_class.FIELDS
                )
            )
            results.append(entry_class.load(e.dump()))
        return results

    def _from_entries(self) -> "TrackCuesV2.TrackCuesInfo":
        return TrackCuesV2.TrackCuesInfo.from_entries(self.entries)

    @dataclass
    class TrackCuesInfo:
        bpm_lock: "TrackCuesV2.BpmLockEntry | None" = None
        color: "TrackCuesV2.ColorEntry | None" = None
        cues: list["TrackCuesV2.CueEntry"] = field(default_factory=list)
        loops: list["TrackCuesV2.LoopEntry"] = field(default_factory=list)
        flips: list["TrackCuesV2.FlipEntry"] = field(default_factory=list)
        unknown: list["TrackCuesV2.UnknownEntry"] = field(default_factory=list)

        @classmethod
        def from_entries(cls, entries: list["TrackCuesV2.Entry"]) -> "TrackCuesV2.TrackCuesInfo":
            bpm_lock = None
            color = None
            cues_list: list[TrackCuesV2.CueEntry] = []
            loops_list: list[TrackCuesV2.LoopEntry] = []
            flips_list: list[TrackCuesV2.FlipEntry] = []
            unknown_list: list[TrackCuesV2.UnknownEntry] = []
            for e in entries:
                if isinstance(e, TrackCuesV2.BpmLockEntry):
                    if bpm_lock is not None:
                        raise ValueError("Multiple BPMLOCK entries found")
                    bpm_lock = e
                elif isinstance(e, TrackCuesV2.ColorEntry):
                    if color is not None:
                        raise ValueError("Multiple COLOR entries found")
                    color = e
                elif isinstance(e, TrackCuesV2.CueEntry):
                    cues_list.append(e)
                elif isinstance(e, TrackCuesV2.LoopEntry):
                    loops_list.append(e)
                elif isinstance(e, TrackCuesV2.FlipEntry):
                    flips_list.append(e)
                elif isinstance(e, TrackCuesV2.UnknownEntry):
                    unknown_list.append(e)
            return cls(
                bpm_lock=bpm_lock,
                color=color,
                cues=cues_list,
                loops=loops_list,
                flips=flips_list,
                unknown=unknown_list,
            )

        def to_entries(self) -> list["TrackCuesV2.Entry"]:
            result: list[TrackCuesV2.Entry] = []
            if self.color is not None:
                result.append(self.color)
            result.extend(self.cues)
            result.extend(self.loops)
            result.extend(self.flips)
            if self.bpm_lock is not None:
                result.append(self.bpm_lock)
            result.extend(self.unknown)
            return result

    type ModifyCallback = Callable[["TrackCuesInfo"], "TrackCuesInfo | None"]

    def modify_entries(self, modify_callback: ModifyCallback, delete_tags_v1: bool = True) -> None:
        track = self._from_entries()
        new_track = modify_callback(track)
        if new_track is None:
            return
        # only delete the v1 tag once we know a change is actually being made
        if delete_tags_v1 and self.tagfile:
            super(SeratoTag, self)._del_geob(TrackCuesV1.GEOB_KEY)  # pylint: disable=bad-super-call
        self.entries = new_track.to_entries()
        self._dump()

    def delete(self):
        was_deleted = super().delete()
        self.entries = []
        if was_deleted:
            self.modified = True
        return was_deleted

    def save(self, force: bool = False):
        if self.modified or force:
            super().save()

    def get_track_color(self) -> bytes | None:
        color_entry = next(
            (entry for entry in self.entries if isinstance(entry, TrackCuesV2.ColorEntry)),
            None,
        )
        if color_entry is None:
            return None
        return color_entry.color

    def get_track_color_name(self) -> str | None:
        color_bytes = self.get_track_color()
        if color_bytes is None:
            return None
        return self._get_track_color_key(color_bytes)

    def set_track_color(self, color: TrackColors, delete_tags_v1: bool = True):
        """
        Args:
            color: TrackColors (bytes)
            delete_tags_v1: Must delete delete_tags_v1 in order for track color change to appear in Serato (since we never change tags_v1 along with it (TODO)). Not sure what tags_v1 is even for, probably older versions of Serato. Have found no issues with deleting this, but use with caution if running an older version of Serato.
        """

        def rule(track: "TrackCuesV2.TrackCuesInfo") -> "TrackCuesV2.TrackCuesInfo | None":
            if track.color is None:
                return None
            new_color = dataclasses.replace(track.color, color=color.value)
            new_track = dataclasses.replace(track, color=new_color)
            return new_track if new_track != track else None

        self.modify_entries(rule, delete_tags_v1)

    def get_snapped_beat_ms(self, postion_ms: int, tolerance_beats: float, min_ms_change: int = 1) -> int | None:
        beatgrid = self.beatgrid or self._get_beatgrid()
        snapped_ms = beatgrid.find_nearest_beat(postion_ms, tolerance_beats)
        if snapped_ms is None:  # 0.0 is a valid beat position (a beat at the very start of the track)
            return None
        snapped_ms = int(round(snapped_ms))
        return snapped_ms if abs(snapped_ms - postion_ms) >= min_ms_change else None

    def snap_positions_to_beat_rule(self, tolerance_beats: float, min_ms_change: int = 1) -> ModifyCallback:
        def rule(track: "TrackCuesV2.TrackCuesInfo") -> "TrackCuesV2.TrackCuesInfo | None":
            new_cues = []
            for cue in track.cues:
                new_ms = self.get_snapped_beat_ms(cue.position, tolerance_beats, min_ms_change)
                if new_ms is not None:
                    new_cues.append(dataclasses.replace(cue, position=new_ms))
                else:
                    new_cues.append(cue)
            new_track = dataclasses.replace(track, cues=new_cues)
            return new_track if new_track != track else None

        return rule

    def snap_positions_to_beat(self, tolerance_beats: float, min_ms_change: int = 1) -> None:
        if not self.entries:
            raise ValueError("No entries set")
        track_before = self._from_entries()
        positions_before = {c.index: c.position for c in track_before.cues}
        self.modify_entries(self.snap_positions_to_beat_rule(tolerance_beats, min_ms_change), delete_tags_v1=True)
        track_after = self._from_entries()
        for c in track_after.cues:
            prev = positions_before.get(c.index)
            if prev is not None and c.position != prev:
                print(f"Snapped by {c.position - prev} ms")

    def _get_beatgrid(self, file_or_data: SeratoTag.FileOrData | None = None) -> TrackBeatgrid:
        if file_or_data is None:
            if not self.tagfile:
                raise ValueError("No tagfile set, or must pass beatgrid")
            self.beatgrid = TrackBeatgrid(self.tagfile)
        else:
            self.beatgrid = TrackBeatgrid(file_or_data)
        return self.beatgrid

    def get_beat_position(
        self, entry: "TrackCuesV2.CueEntry", file_or_data: SeratoTag.FileOrData | None = None
    ) -> float:
        beatgrid = self.beatgrid or self._get_beatgrid(file_or_data)
        return beatgrid.get_beat_position(entry.position)

    def is_beatgrid_locked(self) -> bool:
        return any((isinstance(entry, TrackCuesV2.BpmLockEntry) and entry.enabled) for entry in self.entries)


if __name__ == "__main__":
    import argparse
    import math
    import subprocess
    import tempfile

    from serato_tools.utils.ui import get_hex_editor, get_text_editor, ui_ask

    @dataclass
    class Args:
        file: str
        set_color: str | None
        snap_cues: bool
        snap_tolerance: str | None
        edit: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument(
        "--set_color",
        dest="set_color",
        default=None,
        help="Set track color",
    )
    parser.add_argument(
        "--snap_cues",
        action="store_true",
        help="Snap cue positions to nearest beat within tolerance",
    )
    parser.add_argument(
        "--snap_tolerance",
        type=str,
        default=None,
        help='Snapping tolerance as a fraction of a beat (e.g. "1/16", "1/8", "1/4")',
    )
    parser.add_argument("-e", "--edit", action="store_true")
    args = Args(**vars(parser.parse_args()))

    try:
        tags = TrackCuesV2(args.file)
    except HeaderNotFoundError:
        with open(args.file, mode="rb") as fp:
            data = fp.read()
        tags = TrackCuesV2(data)

    if args.set_color:
        try:
            color = TrackCuesV2.TrackColors[args.set_color.upper()]
        except KeyError as exc:
            valid = ", ".join(c.name for c in TrackCuesV2.TrackColors)
            raise ValueError(f"Invalid track color {args.set_color!r}, must be one of: {valid}") from exc

        tags.set_track_color(color)
        tags.save()
        sys.exit()

    if args.snap_cues:
        if not args.snap_tolerance:
            raise ValueError("--snap_cues requires --snap_tolerance")
        num_str, sep, den_str = args.snap_tolerance.partition("/")
        if sep != "/" or not num_str or not den_str:
            raise ValueError(f"Invalid snap tolerance: {args.snap_tolerance!r}, expected format like '1/4'")
        try:
            num = float(num_str)
            den = float(den_str)
        except ValueError as exc:
            raise ValueError(f"Invalid snap tolerance: {args.snap_tolerance!r}") from exc
        if den == 0:
            raise ValueError("Snap tolerance denominator cannot be zero")
        tolerance_beats = num / den
        if tolerance_beats >= 1:
            raise NotImplementedError("Snap tolerance must be less than 1 beat. TODO: implement this to allow")

        tags.snap_positions_to_beat(tolerance_beats)
        tags.save()
        sys.exit()

    if args.edit:
        text_editor = get_text_editor()
        hex_editor = get_hex_editor()

    new_entries: list[TrackCuesV2.Entry] = []
    width = math.floor(math.log10(len(tags.entries))) + 1 if tags.entries else 1
    action = None
    for entry_index, entry in enumerate(tags.entries):
        if args.edit:
            if action not in ("q", "_"):
                print("{:{}d}: {!r}".format(entry_index, width, entry))
                action = ui_ask(
                    "Edit this entry",
                    {
                        "y": "edit this entry",
                        "n": "do not edit this entry",
                        "q": ("quit; do not edit this entry or any of the " "remaining ones"),
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
                                        "{:{}d}: {}".format(i, width, e.NAME if e.NAME is not None else "Unknown"),
                                        e,
                                    )
                                    for i, e in enumerate(tags.entries[entry_index:], start=entry_index)
                                )
                            else:
                                entries_to_edit = ((entry.NAME if entry.NAME is not None else "Unknown", entry),)

                            for section, e in entries_to_edit:
                                f.write("[{}]\n".format(section).encode())
                                for field_name in e.FIELDS:
                                    f.write("{}: {!r}\n".format(field_name, getattr(e, field_name)).encode())
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
                                results = TrackCuesV2.parse_entries_file(output.decode(), assert_len_1=action != "a")
                            else:
                                results = [type(entry).load(output)]
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
        if new_entries == tags.entries:
            print("No changes made.")
        else:
            tags.entries = new_entries
            tags._dump()  # pylint: disable=protected-access
            if tags.tagfile:
                tags.save()
            else:
                with open(args.file, mode="wb") as fp:
                    fp.write(tags.raw_data or b"")
