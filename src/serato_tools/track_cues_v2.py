#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `Serato Markers2` tag, which holds a track's hot cues, loops, flips, color, and beatgrid lock.

Also the `serato_snap_cues_v2` CLI, which sets the color, snaps cues to the beatgrid, or edits the tag's entries.
"""

import ast
import base64
import configparser
import io
import os
import struct
import sys
import warnings
from typing import TYPE_CHECKING, Callable, ClassVar, Sequence
from enum import Enum, unique
import dataclasses
from dataclasses import dataclass, field


from mutagen.mp3 import HeaderNotFoundError


from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.utils.track_tags import (
    SeratoGeobTag,
    del_geob,
    GeobKeys,
    MissingTagError,
    NoBeatgridError,
    NoCuesError,
)

if TYPE_CHECKING:
    # only for snap_cues_to_beats' annotation: the beatgrid is passed in, never read from this tag's file
    from serato_tools.track_beatgrid import TrackBeatgrid

# the sizes Serato writes the tag at, in an ID3 file: 470 bytes, or larger by a multiple of 512
_MIN_SIZE = 470
_GROWTH_STEP = 512

# cue 8: Serato numbers its cue pads from 0
_MAX_CUE_INDEX = 7

# the package's folder: a deprecation warning skips its frames, to point at the caller's code even when it came through
# another of the package's methods (Track.set_track_color)
_PACKAGE_DIR = os.path.dirname(__file__) + os.sep

# Every tag Serato DJ Pro 2 was seen writing passes the entry checks below, so an entry that doesn't is one this class
# may not understand, and rewriting it could corrupt the tag. Mixxx's parser checks the same fields, with comments on them:
# https://github.com/mixxxdj/mixxx/blob/main/src/track/serato/markers2.cpp


def _check_len(entry_name: str, data: bytes, expected: int):
    """Raises ValueError unless the entry's data is `expected` bytes long."""
    if len(data) != expected:
        raise ValueError(f"{entry_name} entry is {len(data)} bytes, not {expected}")


def _check_fixed(entry_name: str, field: str, value: bytes, expected: bytes):
    """Raises ValueError unless a field Serato always writes the same holds that value, `expected`."""
    if value != expected:
        raise ValueError(f"{entry_name} entry's {field} isn't {expected!r}: {value!r}")


def _check_cue_index(index: int):
    """Raises ValueError for a cue past Serato's 8 cue pads."""
    # Serato only has 8 cue pads, so it ignores a cue past them: it doesn't show it, or move it up when a cue before it
    # is deleted. Such cues, found in real tags, also have bytes unlike any cue Serato shows (field4 cc, color cccccc).
    if index > _MAX_CUE_INDEX:
        raise ValueError(f"cue {index + 1} is past Serato's 8 cue pads, so Serato ignores it: remove it from the tag")


def _parse_name(entry_name: str, data: bytes) -> str:
    """The entry's name, which ends its data: UTF-8 text with a null byte after it and nothing else."""
    name, nullbyte, other = data.partition(b"\x00")
    if nullbyte != b"\x00" or other != b"":
        raise ValueError(f"{entry_name} entry's name isn't followed by a null byte and nothing else: {data!r}")
    return name.decode("utf-8")


class TrackCuesV2(SeratoGeobTag):
    """The `Serato Markers2` tag.

    It holds a track's hot cues, loops, flips, color, and beatgrid lock, as a list of entries.

    Read the entries as a `TrackCuesInfo` and change them with `modify_entries`, or with the methods built on it, then
    call `save()`.
    """

    GEOB_KEY = GeobKeys.CUES_V2
    VERSION = (0x01, 0x01)

    # the colors Serato stores; Serato DJ Pro and Lite show each one a little differently (see docs/colors.md)
    @unique
    class CueColors(Enum):
        """The colors Serato stores for a hot cue, as the RGB bytes in a `CueEntry`'s `color`."""

        RED = b"\xcc\x00\x00"
        ORANGE = b"\xcc\x44\x00"
        YELLOWORANGE = b"\xcc\x88\x00"
        YELLOW = b"\xcc\xcc\x00"
        LIMEGREEN1 = b"\x88\xcc\x00"
        DARKGREEN = b"\x44\xcc\x00"
        LIMEGREEN2 = b"\x00\xcc\x00"
        LIMEGREEN3 = b"\x00\xcc\x44"
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

    # the colors in Serato DJ Pro's track color picker, named for how they look there: the library column shows each
    # one differently, e.g. WHITE as 333333 (see docs/colors.md)
    @unique
    class TrackColors(Enum):
        """The track colors Serato stores, as the RGB bytes in the `ColorEntry`'s `color`."""

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
        # also what Serato writes for a newly analyzed track
        WHITE = b"\xff\xff\xff"
        GREY = b"\xbb\xbb\xbb"
        BLACK = b"\x99\x99\x99"

    def __init__(self, file_or_data: SeratoGeobTag.FileOrData):
        self._raw_data: bytes | None = None
        super().__init__(file_or_data)

        self.entries: list[TrackCuesV2.Entry] = []
        if self._raw_data is not None:
            self.entries = list(self._parse(self._raw_data))

        # whether every edit since this tag last wrote passed the deprecated delete_tags_v1=False, which keeps Serato
        # Markers_ as before it was deprecated; None when no edit has changed anything since
        self._edits_keep_tags_v1: bool | None = None

    def __str__(self) -> str:
        return "\n".join(str(entry) for entry in self.entries)

    @staticmethod
    def _get_entry_class(entry_name: str):
        """The class for an entry named `entry_name`, such as "CUE", or `UnknownEntry` for a name it doesn't know."""
        return TrackCuesV2._ENTRY_CLASS_BY_NAME.get(entry_name, TrackCuesV2.UnknownEntry)

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
        def _parse(cls, data: bytes) -> "TrackCuesV2.UnknownEntry":
            return cls(data=data)

        def _serialize(self) -> bytes:
            return self.data

    @dataclass(repr=False)
    class BpmLockEntry(_EntryRepr):
        """BPM lock state."""

        enabled: bool
        NAME: ClassVar[str] = "BPMLOCK"
        FIELDS: ClassVar[tuple[str, ...]] = ("enabled",)
        _FORMAT: ClassVar[str] = "?"

        @classmethod
        def _parse(cls, data: bytes) -> "TrackCuesV2.BpmLockEntry":
            _check_len(cls.NAME, data, struct.calcsize(cls._FORMAT))
            return cls(*struct.unpack(cls._FORMAT, data))

        def _serialize(self) -> bytes:
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
        def _parse(cls, data: bytes) -> "TrackCuesV2.ColorEntry":
            _check_len(cls.NAME, data, struct.calcsize(cls._FORMAT))
            field1, color = struct.unpack(cls._FORMAT, data)
            _check_fixed(cls.NAME, "field1", field1, b"\x00")
            return cls(field1, color)

        def _serialize(self) -> bytes:
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
        def _parse(cls, data: bytes) -> "TrackCuesV2.CueEntry":
            info_size = struct.calcsize(cls._FORMAT)
            field1, index, position, field4, color, field6 = struct.unpack(cls._FORMAT, data[:info_size])
            _check_cue_index(index)  # first, since such a cue's other fields fail their checks less helpfully
            _check_fixed(cls.NAME, "field1", field1, b"\x00")
            _check_fixed(cls.NAME, "field4", field4, b"\x00")
            _check_fixed(cls.NAME, "field6", field6, b"\x00\x00")
            return cls(field1, index, position, field4, color, field6, _parse_name(cls.NAME, data[info_size:]))

        def _serialize(self) -> bytes:
            _check_cue_index(self.index)
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
        # 27AAE1 for every loop in the captures in data/, which are from Serato DJ Pro 2 (2019-2020). Later versions
        # may set it. Mixxx notes "Serato's Loops don't have a color":
        # https://github.com/mixxxdj/mixxx/blob/main/src/track/serato/markers2.cpp
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
        # the x is a byte that's always 00, so it isn't a field: it's checked on parse and written as 00
        _FORMAT: ClassVar[str] = ">cBII4sc3sx?"

        @classmethod
        def _parse(cls, data: bytes) -> "TrackCuesV2.LoopEntry":
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
            _check_fixed(cls.NAME, "field1", field1, b"\x00")
            _check_fixed(cls.NAME, "field5", field5, b"\xff\xff\xff\xff")
            _check_fixed(cls.NAME, "field6", field6, b"\x00")
            _check_fixed(cls.NAME, "byte 18", data[info_size - 2 : info_size - 1], b"\x00")
            name = _parse_name(cls.NAME, data[info_size:])
            return cls(field1, index, startposition, endposition, field5, field6, color, locked, name)

        def _serialize(self) -> bytes:
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
        """Flip (performance) entry. Flips aren't parsed, so it holds the raw bytes and writes them back unchanged."""

        _raw_data: bytes
        NAME: ClassVar[str] = "FLIP"
        FIELDS: ClassVar[tuple[str, ...]] = ("_raw_data",)

        @classmethod
        def _parse(cls, data: bytes) -> "TrackCuesV2.FlipEntry":
            return cls(_raw_data=data)

        def _serialize(self) -> bytes:
            return self._raw_data

    type Entry = UnknownEntry | BpmLockEntry | ColorEntry | CueEntry | LoopEntry | FlipEntry

    _ENTRY_CLASS_BY_NAME: ClassVar[dict[str, type[Entry]]] = {
        entry_class.NAME: entry_class for entry_class in (BpmLockEntry, ColorEntry, CueEntry, LoopEntry, FlipEntry)
    }

    def _parse(self, data: bytes):
        # the entry classes' _parse() / _serialize() are internal to this module
        # pylint: disable=protected-access
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
            entry_name = SeratoGeobTag._readbytes(fp).decode("utf-8")
            if not entry_name:
                break
            entry_len = struct.unpack(">I", fp.read(4))[0]
            assert entry_len > 0

            entry_class = TrackCuesV2._get_entry_class(entry_name)
            yield entry_class._parse(fp.read(entry_len))
            num_entries += 1

    def _serialize(self):
        # the entry classes' _parse() / _serialize() are internal to this module
        # pylint: disable=protected-access
        version = self._pack_version()

        contents: list[bytes] = [version]
        for entry in self.entries:
            data = entry._serialize()
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

        # Serato ends the payload with a null byte, then drops the base64 padding along with the last character before
        # it: the dropped bits only ever belong to that null byte, so _parse() still reads every entry
        payload = b"".join(contents) + b"\x00"
        payload_base64 = base64.b64encode(payload).rstrip(b"=")
        if len(payload) % 3:
            payload_base64 = payload_base64[:-1]
        lines = [payload_base64[i : i + 72] for i in range(0, len(payload_base64), 72)]

        # Serato keeps the size the tag already had (at least 470 bytes), padding it with nulls, rather than shrinking it.
        # A tag whose content doesn't fit grows in 512-byte steps past 470 (see docs/serato_markers2.md), keeping at
        # least the null byte every tag Serato writes ends with. Whether Serato takes the next step when the content
        # fills a step exactly, with no null byte, isn't known.
        content = version + b"\n".join(lines)
        if len(lines[-1]) == 72:
            content += b"\n"  # Serato ends every full line with one, even the last
        size = max(_MIN_SIZE, len(self._raw_data or b""))
        if len(content) >= size:
            steps = -(-(len(content) + 1 - _MIN_SIZE) // _GROWTH_STEP)  # rounded up
            size = _MIN_SIZE + steps * _GROWTH_STEP
        new_raw_data = content.ljust(size, b"\x00")

        self._raw_data = new_raw_data

    @staticmethod
    def parse_entries_file(contents: str, assert_len_1: bool):
        """Entries read from INI text with a section per entry, as the CLI's edit mode writes them for a text editor.

        Each section is named for its entry type (e.g. `[CUE]` or `[3: CUE]`), with a Python literal per field in the
        entry class's `FIELDS`. Entries are in the order of their sorted section names. `assert_len_1` requires
        exactly one.
        """
        # the entry classes' _parse() / _serialize() are internal to this module
        # pylint: disable=protected-access
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
            results.append(entry_class._parse(e._serialize()))
        return results

    def _from_entries(self) -> "TrackCuesV2.TrackCuesInfo":
        return TrackCuesV2.TrackCuesInfo.from_entries(self.entries)

    @dataclass
    class TrackCuesInfo:
        """The tag's entries grouped by kind, which `modify_entries` hands its callback to change."""

        bpm_lock: "TrackCuesV2.BpmLockEntry | None" = None
        color: "TrackCuesV2.ColorEntry | None" = None
        cues: list["TrackCuesV2.CueEntry"] = field(default_factory=list)
        loops: list["TrackCuesV2.LoopEntry"] = field(default_factory=list)
        flips: list["TrackCuesV2.FlipEntry"] = field(default_factory=list)
        unknown: list["TrackCuesV2.UnknownEntry"] = field(default_factory=list)

        @classmethod
        def from_entries(cls, entries: list["TrackCuesV2.Entry"]) -> "TrackCuesV2.TrackCuesInfo":
            """Groups `entries` by kind; raises ValueError for more than one BPM lock or color entry."""
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
            """The entries in a flat list, in the order Serato writes them."""
            result: list[TrackCuesV2.Entry] = []
            if self.color is not None:
                result.append(self.color)
            result.extend(self.cues)
            result.extend(self.loops)
            # Serato's order: BPMLOCK before the flips, as in data/id3/flips and as Mixxx writes them. Mixxx: "new
            # entry types are appended when Serato decides to add a new type. For FLIP entries, this holds true"
            # https://github.com/mixxxdj/mixxx/blob/main/src/track/serato/markers2.cpp
            if self.bpm_lock is not None:
                result.append(self.bpm_lock)
            result.extend(self.flips)
            result.extend(self.unknown)
            return result

    type ModifyCallback = Callable[["TrackCuesInfo"], "TrackCuesInfo | None"]

    def modify_entries(self, modify_callback: ModifyCallback, delete_tags_v1: bool | None = None) -> None:
        """Replaces the entries with what `modify_callback` returns for them, or leaves them if it returns None.

        `delete_tags_v1` is deprecated, to be removed in the next major version: pass it to `save()` instead. Until
        then, passing False keeps `Serato Markers_` at the next save, unless another edit since the last save didn't pass
        False.
        """
        if delete_tags_v1 is not None:
            warnings.warn(
                "passing delete_tags_v1 to an edit is deprecated and will be removed in a future major version, pass it to save() instead",
                DeprecationWarning,
                skip_file_prefixes=(_PACKAGE_DIR,),
            )
        track = self._from_entries()
        new_track = modify_callback(track)
        if new_track is None:
            return
        # any edit that didn't pass False deletes Serato Markers_, as it did when each edit chose
        self._edits_keep_tags_v1 = delete_tags_v1 is False and self._edits_keep_tags_v1 is not False
        self.entries = new_track.to_entries()
        self._serialize()

    def _put_in_tagfile(self, delete_tags_v1: bool = True):
        """As `SeratoGeobTag._put_in_tagfile`, also deleting `Serato Markers_` unless told not to."""
        super()._put_in_tagfile()
        # deleted only here, when this tag writes, and not by the edit: deleted from the shared tagfile for an edit
        # that changed nothing, or was changed back, it would be written by another tag's save
        if delete_tags_v1 and not self._edits_keep_tags_v1 and self.tagfile:
            # TODO: keep Serato Markers_ in sync with Markers2 instead of deleting it
            del_geob(self.tagfile, TrackCuesV1.GEOB_KEY)
        self._edits_keep_tags_v1 = None

    def _write_to_tagfile(self, delete_tags_v1: bool = True) -> bool:
        if not self.has_changed:
            return False
        self._put_in_tagfile(delete_tags_v1)
        return True

    def delete(self):
        """Deletes the tag in memory, returning whether the file had it; call `save()` to write the deletion."""
        was_deleted = super().delete()
        self.entries = []
        return was_deleted

    def save(self, force: bool = False, delete_tags_v1: bool = True):
        """Writes the tag to the file, if it changed since it was read or last saved, or if `force`.

        Args:
            force: Write the tag even if it hasn't changed.
            delete_tags_v1: When writing, delete the legacy `Serato Markers_` tag, because a stale one stops changes to this tag from appearing in Serato. No issues have been found from deleting it, but use caution with versions of Serato before 3, which may still read it.
        """
        if not (self.has_changed or force):
            return
        if not self.tagfile:
            raise Exception("no tagfile, no saving")
        self._put_in_tagfile(delete_tags_v1)
        self.tagfile.save()

    def get_track_color(self) -> bytes | None:
        """The track's color as the bytes of a `TrackColors` value, or None if the tag has no color entry yet."""
        color_entry = next((entry for entry in self.entries if isinstance(entry, TrackCuesV2.ColorEntry)), None)
        return None if color_entry is None else color_entry.color

    def get_track_color_name(self) -> str | None:
        """The name of the track's `TrackColors` value, or None if the tag has no color entry yet.

        Raises ValueError for a color that isn't one of `TrackColors`.
        """
        return None if (color_bytes := self.get_track_color()) is None else TrackCuesV2.TrackColors(color_bytes).name

    def set_track_color(self, color: TrackColors, delete_tags_v1: bool | None = None):
        """Sets the track color in memory; call `save()` to write it to the file.

        Adds the color entry, and the tag itself, if the track doesn't have them yet, as Serato writes them.
        `delete_tags_v1` is deprecated: see `modify_entries`.
        """

        def rule(track: "TrackCuesV2.TrackCuesInfo") -> "TrackCuesV2.TrackCuesInfo | None":
            if track.color is None:
                # field1 is 0 in every COLOR entry Serato wrote in this repo's data/ captures
                new_color = TrackCuesV2.ColorEntry(field1=b"\x00", color=color.value)
            else:
                new_color = dataclasses.replace(track.color, color=color.value)
            new_track = dataclasses.replace(track, color=new_color)
            return new_track if new_track != track else None

        self.modify_entries(rule, delete_tags_v1)

    def set_beatgrid_locked(self, locked: bool, delete_tags_v1: bool | None = None):
        """Locks or unlocks the track's beatgrid in memory; call `save()` to write it to the file.

        Adds the BPM lock entry, and the tag itself, if the track doesn't have them yet, as Serato writes them.
        `delete_tags_v1` is deprecated: see `modify_entries`.
        """

        def rule(track: "TrackCuesV2.TrackCuesInfo") -> "TrackCuesV2.TrackCuesInfo | None":
            if track.bpm_lock is not None and track.bpm_lock.enabled == locked:
                return None
            return dataclasses.replace(track, bpm_lock=TrackCuesV2.BpmLockEntry(enabled=locked))

        self.modify_entries(rule, delete_tags_v1)

    @dataclass(frozen=True)
    class SnappedCue:
        """A cue that `snap_cues_to_beats` moved: its index (from 0) and its position in ms before and after."""

        index: int
        old_position: int
        new_position: int

    def snap_cues_to_beats(
        self, beatgrid: "TrackBeatgrid", tolerance_beats: float, min_ms_change: int = 2
    ) -> list["TrackCuesV2.SnappedCue"]:
        """Moves each cue to its nearest beat in `beatgrid` in memory, and returns the moves.

        Where each cue goes is decided by `beatgrid.get_snapped_position`. Pass the track's own beatgrid, as
        `Track.snap_cues_to_beats` does. Call `save()` to write the change to the file. A `min_ms_change` below 2
        warns, since that moves nearly every cue Serato placed.

        Raises NoCuesError for a track without a `Serato Markers2` tag, and NoBeatgridError for one without a beatgrid,
        such as one Serato hasn't analyzed, which Mixed In Key may already have added cues to. A tag with no cues in it
        moves nothing.
        """
        if not self.entries:
            raise NoCuesError(self.filename)
        if not beatgrid.entries:
            raise NoBeatgridError(beatgrid.filename)
        if min_ms_change < 2:
            warnings.warn(
                f"min_ms_change={min_ms_change} snaps cues that are 1 ms off the beat, which is most cues Serato placed",
                skip_file_prefixes=(_PACKAGE_DIR,),
            )
        snapped: list[TrackCuesV2.SnappedCue] = []

        def rule(track: "TrackCuesV2.TrackCuesInfo") -> "TrackCuesV2.TrackCuesInfo | None":
            new_cues: list[TrackCuesV2.CueEntry] = []
            for cue in track.cues:
                new_ms = beatgrid.get_snapped_position(cue.position, tolerance_beats, min_ms_change)
                # a min_ms_change of 0 or less can snap a cue to where it already is, which isn't a move
                if new_ms is None or new_ms == cue.position:
                    new_cues.append(cue)
                else:
                    snapped.append(TrackCuesV2.SnappedCue(cue.index, cue.position, new_ms))
                    new_cues.append(dataclasses.replace(cue, position=new_ms))
            return dataclasses.replace(track, cues=new_cues) if snapped else None

        self.modify_entries(rule)
        return snapped

    def is_beatgrid_locked(self) -> bool:
        """Whether the tag has a BPM lock entry that's enabled."""
        return any((isinstance(entry, TrackCuesV2.BpmLockEntry) and entry.enabled) for entry in self.entries)


def main():
    """The `serato_snap_cues_v2` CLI: sets the track color, snaps cues to the beatgrid, or prints or edits entries."""
    # this script is part of the module, so it uses the tag's and its entries' internal _parse() / _serialize()
    # pylint: disable=protected-access
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

        if not tags.tagfile:
            raise ValueError("--snap_cues needs an audio file, to read its beatgrid")
        # imported here, so that the tag's module needs the beatgrid's only for this option
        from serato_tools.track_beatgrid import TrackBeatgrid

        try:
            snapped_cues = tags.snap_cues_to_beats(TrackBeatgrid(tags.tagfile), tolerance_beats)
        except MissingTagError as error:
            sys.exit(f"Can't snap the cues: {error}")
        for snapped in snapped_cues:
            print(f"Snapped cue {snapped.index + 1} by {snapped.new_position - snapped.old_position} ms")
        tags.save(delete_tags_v1=True)
        sys.exit()

    if args.edit:
        text_editor = get_text_editor()
        hex_editor = get_hex_editor()

    if not tags.entries:
        print(f'File has no "{TrackCuesV2.GEOB_KEY}" entries.')
        sys.exit()
    new_entries: list[TrackCuesV2.Entry] = []
    width = math.floor(math.log10(len(tags.entries))) + 1
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
                                results = [type(entry)._parse(output)]
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
            tags._serialize()
            if tags.tagfile:
                tags.save()
            else:
                with open(args.file, mode="wb") as fp:
                    fp.write(tags._raw_data or b"")  # pylint: disable=protected-access


if __name__ == "__main__":
    main()
