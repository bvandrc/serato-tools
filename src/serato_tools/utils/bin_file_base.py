"""The container format of Serato's library database and crate files.

A file is a list of entries, each a named, typed value, which may itself be a nested list of entries.
"""

import base64
import copy
import hashlib
import io
import json
import os
import re
import struct
from collections.abc import Callable, Collection, Generator, Iterable, Mapping
from enum import StrEnum, unique
from re import Pattern
from typing import (
    Any,
    ClassVar,
    NotRequired,
    TypedDict,
    cast,
    overload,
)

from serato_tools.utils import SERATO_DRIVE, logger


class DataTypeError(Exception):
    """A value whose type doesn't match the one its field holds."""

    def __init__(self, value: Any, expected_type: type, field: str | None):
        super().__init__(
            f"value must be {expected_type.__name__} when field is {field} (type: {type(value).__name__}) (value: {value!s})"
        )


# for `list`, a bare `type[T]` would type the result `list[Unknown]`; this overload keeps the element type of `value`'s
# list member instead, as an isinstance check would
@overload
def expect_type[I](value: object | list[I], expected_type: type[list[Any]], field: str | None) -> list[I]: ...


@overload
def expect_type[T](value: object, expected_type: type[T], field: str | None) -> T: ...


def expect_type(value: object, expected_type: type, field: str | None) -> object:
    """`value`, typed as `expected_type`; raises DataTypeError if it isn't an instance of it."""
    if not isinstance(value, expected_type):
        raise DataTypeError(value, expected_type, field)
    return value


class DeeplyNestedListError(Exception):
    """An entry list nested inside a flat one, such as a track's, which this package can't parse into objects."""

    def __init__(self, field: str, value: Any):
        super().__init__(f"an entry list nested in another, in field {field}, which isn't supported: {value}")


def _field_values(field_enums: tuple[type[StrEnum], ...]) -> frozenset[str]:
    """Every field name in `field_enums`."""
    return frozenset(member.value for field_enum in field_enums for member in field_enum)


def _field_names(field_enums: tuple[type[StrEnum], ...]) -> Mapping[str, str]:
    """A readable name for each field in `field_enums`, from its member's name: "File Path" for `FILE_PATH`."""
    return {
        # DATE_ADDED_T and DATE_ADDED_U hold the same time, so both are "Date Added"
        member.value: member.name.replace("_", " ")
        .title()
        .replace("Smartcrate", "SmartCrate")
        .replace("Added U", "Added")
        .replace("Added T", "Added")
        for field_enum in field_enums
        for member in field_enum
    }


class SeratoBinFile:
    """A Serato database or crate file, parsed into `entries`, a list of (field name, value) pairs.

    A field name's first letter gives its value's type: a nested entry list, text, a bool, or an int. Subclasses set
    `TESTED_VERSIONS`, `TRACK_PATH_KEY`, and `DEFAULT_ENTRIES`. Change the file through the methods here, such as
    `modify_tracks` or `modify`, then call `save()`.
    """

    @unique
    class Fields(StrEnum):
        """The field names found in database and crate files, named for what each holds."""

        # Database & Crate
        VERSION = "vrsn"
        TRACK = "otrk"
        # Database - Track
        FILE_TYPE = "ttyp"
        FILE_PATH = "pfil"
        TITLE = "tsng"
        ARTIST = "tart"
        ALBUM = "talb"
        GENRE = "tgen"
        LENGTH = "tlen"
        BITRATE = "tbit"
        SAMPLE_RATE = "tsmp"
        SIZE = "tsiz"
        BPM = "tbpm"
        KEY = "tkey"
        TIME = "utme"
        GROUPING = "tgrp"
        PUBLISHER = "tlbl"
        COMPOSER = "tcmp"
        YEAR = "ttyr"
        COMMENT = "tcom"
        REMIXER = "trmx"
        TRACK_NUMBER = "utkn"
        DISC_NUMBER = "udsc"
        # the same time as DATE_ADDED_U, as text
        DATE_ADDED_T = "tadd"
        # when the track was added, as a Unix timestamp
        DATE_ADDED_U = "uadd"
        PLAY_COUNT = "utpc"
        # the track color, as 0xRRGGBB: the same color as the track's tags, so a TrackCuesV2.TrackColors value as an int
        COLOR = "ulbl"
        BEATGRID_LOCKED = "bbgl"
        CORRUPT = "bcrt"
        CORRUPT_REASON = "tcor"
        MISSING = "bmis"
        HAS_STEMS = "bstm"
        # set on the last played track only
        PLAYED = "bply"
        READ_ONLY = "biro"
        OVERVIEW_BUILT = "bovc"
        # Unnamed, since what they hold is only a guess. On every track, and the same on every track of a large library:
        # - bitu (False): from iTunes?
        # - buns (False): unsupported?
        # - bwlb (False): white label?
        # - blop (False): loop?
        # - bhrt (True), bkrk (False), bwll (False): unknown
        # Also unnamed: ufsb, maybe the file size in bytes when Serato last read the file, which retagging changes.
        # Crates
        SORTING = "osrt"
        REVERSE_ORDER = "brev"
        COLUMN = "ovct"
        COLUMN_NAME = "tvcn"
        COLUMN_WIDTH = "tvcw"
        TRACK_PATH = "ptrk"

    # the enums holding this class's valid field names; a subclass with fields of its own (SmartCrate's
    # rule fields) extends this, which extends what _check_valid_field accepts and get_field_name resolves
    FIELD_ENUMS: tuple[type[StrEnum], ...] = (Fields,)

    # derived from FIELD_ENUMS, here and for each subclass in __init_subclass__, so they can't drift from it
    FIELDS: frozenset[str] = _field_values(FIELD_ENUMS)
    # a readable name for each field in FIELDS, as get_field_name gives it: "File Path" for pfil; built once per
    # class, since printing or JSON-dumping a large database names every field
    FIELD_NAMES: Mapping[str, str] = _field_names(FIELD_ENUMS)

    type ParsedField = Fields | str
    type BasicValue = str | bytes | int | bool

    type Entry = tuple[ParsedField, "SeratoBinFile.Value"]
    type EntryList = list[Entry]
    type Value = BasicValue | EntryList

    type EntryFull = tuple[ParsedField, str, "SeratoBinFile.EntryFullValue"]
    type EntryFullList = list[EntryFull]
    type EntryFullValue = BasicValue | EntryFullList

    type ValueOrNone = Value | None

    TESTED_VERSIONS: frozenset[str]
    TRACK_PATH_KEY: Fields
    DEFAULT_ENTRIES: ClassVar[EntryList]

    # set once __init__ has parsed the file, so save() can refuse a half-built instance
    _parsed: bool = False

    # a hash of the file's bytes as loaded or last saved to its own path, for has_changed; None if it didn't exist
    _saved_hash: bytes | None = None

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        cls.FIELDS = _field_values(cls.FIELD_ENUMS)
        cls.FIELD_NAMES = _field_names(cls.FIELD_ENUMS)

    def __init__(self, file: str, *, _new: bool = False):
        """Parses `file`, either Serato's binary format or JSON as `write_json` writes it.

        Raises FileNotFoundError if it doesn't exist (a crate's `new` starts one instead), and ValueError for a version
        not in `TESTED_VERSIONS`.
        """
        self.filepath = os.path.abspath(file)

        # every value's type matches its field's, as checked wherever one comes in (parsing, JSON, set_value), so
        # code reading a value can rely on its field's type rather than check it
        self._entries: SeratoBinFile.EntryList
        self._version: str

        for key in ["TESTED_VERSIONS", "TRACK_PATH_KEY", "DEFAULT_ENTRIES"]:
            if not hasattr(self, key):
                raise AttributeError(f"need to set {key} in subclass")

        if _new:
            # CrateBase.new's empty file, from the defaults, which save() creates
            if os.path.exists(file):
                raise FileExistsError(f"file already exists: {file}")
            # copied down to the nested lists (osrt, ovct, ...): a shallow copy would leave every instance sharing —
            # and able to mutate — the class-level DEFAULT_ENTRIES sublists.
            self._entries = copy.deepcopy(self.DEFAULT_ENTRIES)
            self._version = self._check_version(self._entries[0][1])
        elif os.path.exists(file):
            if file.lower().endswith(".json"):
                with open(file, encoding="utf-8") as f:
                    self.from_json_object(json.load(f))
                # what saving the entries as loaded would write
                self._saved_hash = self._hash(self.to_bytes())
            else:
                with open(file, "rb") as f:
                    data = f.read()
                self._entries = list(self._parse_item(data))
                # hashes the bytes already read rather than copying the entries, so a load that only reads pays
                # next to nothing for has_changed
                self._saved_hash = self._hash(data)
        else:
            raise FileNotFoundError(f"file does not exist: {file}")

        # a file with no version entry, such as an empty one, would otherwise load with no version checked
        if not hasattr(self, "_version"):
            raise ValueError(f"no version entry ({SeratoBinFile.Fields.VERSION.value}) in {file}")

        self._parsed = True

    def __str__(self) -> str:
        return self._stringify_entries(self.get_entries())

    def _stringify_entries(self, entries: Iterable[EntryFull], indent: int = 0) -> str:
        lines: list[str] = []
        indent_str = "    " * indent

        for field, fieldname, value in entries:
            if isinstance(value, list):
                lines.append(f"{indent_str}{field} ({fieldname})")
                lines.append(self._stringify_entries(value, indent + 1))
            else:
                lines.append(f"{indent_str}{field} ({fieldname}): {value!s}")

        return "\n".join(lines)

    def _check_version(self, value: Value) -> str:
        """`value`, typed as text; raises unless it's one of `TESTED_VERSIONS`."""
        value = expect_type(value, str, SeratoBinFile.Fields.VERSION)
        if value not in self.TESTED_VERSIONS:
            raise ValueError(f"""
                ERROR: Untested version Serato bin file version: {value}
                Please contact the developer so we can get it tested and supported!
                We will have you send the file you are trying to parse so we can add support and tests for it.
                We do not want to risk damaging users' library database or crate files!

                Possible versions:
                {"\n".join(sorted(self.TESTED_VERSIONS))}
                """)
        return value

    class EntryJson(TypedDict):
        """An entry as `to_json_object` gives it, with its field's readable name and its value's Python type."""

        field: "SeratoBinFile.ParsedField"
        fieldname: str
        type: str
        value: str | int | bool | list["SeratoBinFile.EntryJson"]

    def to_json_object(self) -> list[EntryJson]:
        """The entries as JSON-compatible objects, with bytes base64-encoded; `from_json_object` reads them back."""

        def entries_to_json(entries: SeratoBinFile.EntryList) -> list[SeratoBinFile.EntryJson]:
            result = []

            for field, value in entries:
                if isinstance(value, list):
                    value = entries_to_json(value)
                elif isinstance(value, (bytes, bytearray, memoryview)):
                    value = base64.b64encode(value).decode("utf-8")  # need to make JSON compatible

                entry_obj: SeratoBinFile.EntryJson = {
                    "field": field,
                    "fieldname": self.get_field_name(field),
                    "value": value,
                    "type": type(value).__name__,
                }

                result.append(entry_obj)

            return result

        return entries_to_json(self._entries)

    def from_json_object(self, json_data: list[EntryJson]):
        """Replaces the entries with those in `json_data`, as `to_json_object` gives them.

        Raises, leaving the entries as they were, if they wouldn't serialize or have an untested version.
        """

        def json_to_entries(json_list: list[SeratoBinFile.EntryJson]) -> SeratoBinFile.EntryList:
            result: SeratoBinFile.EntryList = []
            version_set = False
            for entry_obj in json_list:
                field = entry_obj["field"]
                value = entry_obj["value"]
                value_type = entry_obj["type"]

                if value_type == "list":
                    value = json_to_entries(cast(list[SeratoBinFile.EntryJson], value))
                elif value_type in ("bytes", "bytearray", "memoryview"):
                    value = base64.b64decode(cast(bytes, value))
                elif value_type == "int":
                    value = int(cast(int, value))
                elif value_type == "bool":
                    value = bool(cast(bool, value))
                elif value_type == "str":
                    value = str(cast(str, value))
                else:
                    raise ValueError(f"unexpected type: {value_type}")

                if not version_set and field == SeratoBinFile.Fields.VERSION:
                    self._version = self._check_version(value)
                    version_set = True

                result.append((field, value))

            return result

        entries = json_to_entries(json_data)
        # JSON types aren't tied to field prefixes the way the binary format is, so check now that it serializes,
        # rather than failing on the first save. Checked before assigning, so a bad file leaves entries as they were.
        self._serialize_entries(entries)
        self._entries = entries

    def write_json(self, filepath: str) -> None:
        """Writes the entries to `filepath` as JSON, one entry per line, which loading that path reads back."""

        def write_json_array(json_entries: list[SeratoBinFile.EntryJson], indent: int = 0) -> str:
            indent_str = "  " * indent
            lines = ["[\n"]

            for i, entry in enumerate(json_entries):
                if isinstance(entry["value"], list):
                    lines.append(
                        f'{indent_str}  {{"field": "{entry["field"]}", "fieldname": "{entry["fieldname"]}", "type": "{entry["type"]}", "value": '
                    )
                    lines.append(write_json_array(entry["value"], indent + 1))
                    lines.append("}")
                else:
                    lines.append(f"{indent_str}  {json.dumps(entry, ensure_ascii=False)}")

                lines.append(",\n" if i < len(json_entries) - 1 else "\n")

            lines.append(f"{indent_str}]")
            return "".join(lines)

        json_content = write_json_array(self.to_json_object(), indent=0)

        json.loads(json_content)  # check validity before opening (and truncating) the destination file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_content)

    def print(self):
        print(self)  # noqa: T201

    class EntryListCls:
        """A flat entry list, such as a track's, with each field's value as an attribute named for the field.

        Holds copies of the values, so changes reach the file only through `to_entries()`. Set values through
        `set_value`, which checks them, not by assigning the attributes. Raises DeeplyNestedListError for a nested entry
        list, and ValueError for a repeated field.
        """

        def __init__(self, entries: "SeratoBinFile.EntryList"):
            self.fields: list[str] = []

            for field, value in entries:
                if isinstance(value, list):
                    raise DeeplyNestedListError(field, value)
                setattr(self, field, value)
                self.fields.append(field)

            # values are stored as attributes, so a repeated field would silently overwrite the earlier
            # value and then be written back twice — corrupting the file on round-trip. One set-vs-list
            # length comparison is far cheaper than a per-field membership scan; name the culprits only
            # on the failure path.
            if len(set(self.fields)) != len(self.fields):
                duplicates = sorted({f for f in self.fields if self.fields.count(f) > 1})
                raise ValueError(f"duplicate field(s) in entry: {', '.join(duplicates)}")

        def __repr__(self) -> str:
            return str(self.to_entries())

        @overload
        def get_value(self, field: str) -> "SeratoBinFile.Value": ...

        @overload
        def get_value[T](self, field: str, value_type: type[T]) -> T: ...

        def get_value(self, field: str, value_type: type | None = None) -> object:
            """`field`'s value; given `value_type`, the type `field` holds, typed as it.

            `value_type` isn't checked against the value: values are checked when they're set or loaded, so a value
            already has the type its field holds.
            """
            # value_type only types the result for the overload above
            del value_type
            return getattr(self, field)

        def set_value(self, field: str, value: "SeratoBinFile.Value"):
            """Sets `field`'s value, adding the field after the others if it isn't set yet.

            Raises DataTypeError if `value` isn't the type `field` holds, and ValueError as `check_value` does.
            """
            SeratoBinFile.check_value(field, value)
            if field not in self.fields:
                self.fields.append(field)
            setattr(self, field, value)

        def remove_field(self, field: str) -> bool:
            """Removes `field`, and returns whether it was there to remove."""
            if field not in self.fields:
                return False
            self.fields.remove(field)
            delattr(self, field)
            return True

        def to_entries(self) -> "SeratoBinFile.EntryList":
            return [(f, self.get_value(f)) for f in self.fields]

    class Track(EntryListCls):
        """A track's entry, with its path as stored (`relpath`: no drive, `/`-separated) read from `path_key`."""

        def __init__(self, entries: "SeratoBinFile.EntryList", path_key: str):
            super().__init__(entries)

            self.path_key = path_key

        @property
        def relpath(self) -> str:
            """The track's path as stored: without its drive, `/`-separated."""
            return self.get_value(self.path_key, str)

        @property
        def full_path(self) -> str:
            """The track's absolute path, which is its `relpath` on `SERATO_DRIVE`."""
            return SeratoBinFile.get_full_path(self.relpath)

        def set_value(self, field: str, value: "SeratoBinFile.Value"):
            """Sets `field` to `value`.

            An empty string removes the field instead, as Serato does when a tag is cleared, so a track never stores
            one empty. Raises as `EntryListCls.set_value` does.
            """
            if value == "":
                self.remove_field(field)
            else:
                super().set_value(field, value)

        def remove_field(self, field: str) -> bool:
            """Removes `field`, and returns whether it was there to remove.

            Raises ValueError for the track's path, since a track can't be without one.
            """
            if field == self.path_key:
                raise ValueError(f"can't remove a track's path ({field})")
            return super().remove_field(field)

        def set_path(self, path: str):
            """Points the track at `path`, stored without its drive, as Serato stores paths."""
            self.set_value(self.path_key, SeratoBinFile.get_relative_path(path))

    def _get_track(self, entries: "SeratoBinFile.EntryList"):
        return SeratoBinFile.Track(entries, path_key=self.TRACK_PATH_KEY)

    @staticmethod
    def _get_entry_value(entries: "SeratoBinFile.EntryList", field: str) -> "SeratoBinFile.ValueOrNone":
        """The value of the first entry named `field`, or None if there isn't one."""
        return next((v for f, v in entries if f == field), None)

    @staticmethod
    def _get_type(field: str) -> str:
        """The letter that gives `field`'s value type: its first, except for `vrsn`, which holds text."""
        # vrsn field has no type_id, but contains text ("t")
        return "t" if field == SeratoBinFile.Fields.VERSION else field[0]

    def _parse_item(self, item_data: bytes) -> Generator["SeratoBinFile.Entry", None, None]:
        """Each entry in `item_data`, with nested entry lists parsed too; checks and records the first version."""
        fp = io.BytesIO(item_data)
        version_set = False
        for header in iter(lambda: fp.read(8), b""):
            if len(header) != 8:
                raise ValueError(f"file ends partway through an entry's header: {header!r}")
            field_ascii: bytes
            length: int
            field_ascii, length = struct.unpack(">4sI", header)
            field: str = field_ascii.decode("ascii")
            type_id: str = SeratoBinFile._get_type(field)

            data = fp.read(length)
            if len(data) != length:
                raise ValueError(f"file ends partway through a {field} entry: {len(data)} of its {length} bytes")

            value: SeratoBinFile.Value
            if type_id in ("o", "r"):  #  struct
                value = list(self._parse_item(data))
            elif type_id in ("p", "t"):  # text
                value = data.decode("utf-16-be")
            elif type_id == "b":  # single byte, is a boolean
                # anything but 0x00/0x01 would be rewritten as 0x01 on save, so refuse it like an unknown version
                if data not in (b"\x00", b"\x01"):
                    raise ValueError(f"unexpected boolean value for field {field}: {data!r}")
                value = cast(bool, struct.unpack("?", data)[0])
            elif type_id in ("s", "u"):  # unsigned 16-bit or 32-bit int
                size, fmt = (2, ">H") if type_id == "s" else (4, ">I")
                # checked here, rather than left to struct.error, which isn't a ValueError like other malformed data
                if len(data) != size:
                    raise ValueError(f"{field} holds a {size}-byte number, not {len(data)} bytes: {data!r}")
                value = cast(int, struct.unpack(fmt, data)[0])
            else:
                raise ValueError(f"unexpected type for field: {field}")

            if not version_set and field == SeratoBinFile.Fields.VERSION:
                self._version = self._check_version(value)
                version_set = True

            yield field, value

    @staticmethod
    def check_value(field: str, value: Value):
        """Raises unless `field` can hold `value`, as saving it would.

        Raises DataTypeError for the wrong type, and ValueError for a number too big or negative, or a field of no known
        type. Check a value with it before changing anything that a failed save would leave half done.
        """
        if SeratoBinFile._get_type(field) in ("o", "r"):
            expect_type(value, list, field)
        else:
            SeratoBinFile._pack_value(field, value)

    @staticmethod
    def _pack_value(field: str, value: Value) -> bytes:
        """The bytes `field` holds `value` as, for any field but a nested entry list; raises as `check_value`."""
        type_id = SeratoBinFile._get_type(field)
        if type_id in ("p", "t"):  # text
            value = expect_type(value, str, field)
            return value.encode("utf-16-be")
        if type_id == "b":  # single byte, is a boolean
            value = expect_type(value, bool, field)
            return struct.pack("?", value)
        if type_id in ("s", "u"):  # unsigned 16-bit or 32-bit int
            value = expect_type(value, int, field)
            bits, fmt = (16, ">H") if type_id == "s" else (32, ">I")
            # checked here, rather than left to struct.error, so the message names the field
            if not 0 <= value < 2**bits:
                raise ValueError(f"{field} holds a number from 0 to {2**bits - 1}, not {value}")
            return struct.pack(fmt, value)
        raise ValueError(f"unexpected type for field: {field}")

    def _serialize_item(self, entry: Entry) -> bytes:
        """An entry's bytes: its header, then its value encoded as its field's type requires."""
        field, value = entry
        field_bytes = field.encode("ascii")
        if len(field_bytes) != 4:
            raise ValueError(f"field names are 4 characters: {field!r}")

        if field == SeratoBinFile.Fields.VERSION:
            self._check_version(value)
            if value != self._version:
                raise ValueError(f"version field value {value} does not match parsed value {self._version}")

        if SeratoBinFile._get_type(field) in ("o", "r"):  #  struct (list)
            data = self._serialize_entries(expect_type(value, list, field))
        else:
            data = SeratoBinFile._pack_value(field, value)

        length = len(data)
        header = struct.pack(">4sI", field_bytes, length)
        return header + data

    def _serialize_entries(self, entries: EntryList):
        return b"".join(self._serialize_item(entry) for entry in entries)

    def to_bytes(self) -> bytes:
        """
        The file's bytes, serialized from the current entries.

        Each call re-serializes the whole file, so call it once rather than in a loop.
        """
        return self._serialize_entries(self._entries)

    @staticmethod
    def _hash(data: bytes) -> bytes:
        return hashlib.sha256(data).digest()

    @property
    def has_changed(self) -> bool:
        """Whether saving would change the file's bytes from those loaded or last saved, however `entries` was edited.

        Sees edits made to `entries` directly, in place or by assignment, as well as through this class's methods.
        Each call serializes the whole file, as `to_bytes()` does, and raises as it does for an invalid entry. Compared
        with the file as loaded or saved, not with the file on disk now, which this doesn't reread. A file that didn't
        exist when loaded counts as changed, since saving creates it.
        """
        return self._differs_from_saved(self.to_bytes())

    def _differs_from_saved(self, data: bytes) -> bool:
        """Whether `data` differs from the bytes loaded or last saved, or there were none, as for a new file."""
        return self._saved_hash is None or self._hash(data) != self._saved_hash

    def _is_own_path(self, file: str) -> bool:
        """Whether `file` is the file this was loaded from, by any path to it."""
        if os.path.normcase(os.path.abspath(file)) == os.path.normcase(self.filepath):
            return True
        # the same file by another name: a symlink or hard link, or another case on a case-insensitive filesystem
        try:
            return os.path.samefile(file, self.filepath)
        except OSError:  # either doesn't exist, so they can't be the same file
            return False

    def _entry_lists(self, field: str) -> Generator[tuple[int, EntryList], None, None]:
        """The index in `_entries` and the value of each top-level entry named `field`, which holds an entry list."""
        for i, (entry_field, value) in enumerate(self._entries):
            if entry_field == field:
                # a field named for an entry list holds one, which loading checks
                yield i, cast(SeratoBinFile.EntryList, value)

    def _filter_entry_lists(self, field: str, keep: Callable[[EntryList], bool]) -> bool:
        """Removes each top-level entry named `field` whose entry list `keep` returns False for; returns if any were."""
        removed_indices = {i for i, value in self._entry_lists(field) if not keep(value)}
        if removed_indices:
            self._entries = [entry for i, entry in enumerate(self._entries) if i not in removed_indices]
        return bool(removed_indices)

    def get_tracks(self) -> Generator[Track, None, None]:
        """Each track entry, as a `Track`.

        A `Track` holds copies of the entry's values, so changing one doesn't change the file: use `modify_tracks`.
        """
        for _, value in self._entry_lists(SeratoBinFile.Fields.TRACK):
            yield self._get_track(value)

    def get_track_paths(self, include_drive: bool = False) -> list[str]:
        """Each track's path: as stored, with no drive, or with `include_drive`, as an absolute path."""
        return [t.full_path if include_drive else t.relpath for t in self.get_tracks()]

    def modify_tracks(self, func: Callable[[Track], Track], files: Iterable[str] | None = None) -> bool:
        """
        Replaces each track with what `func` returns for it, and returns whether any track changed.

        Given `files`, only those tracks are passed to `func`, and the rest are skipped after reading just their path,
        which is much faster on a large library. Raises as `check_value` does for a value a changed track's field can't
        hold. If this or `func` raises for any track, no track is changed.
        """
        relpaths = None if files is None else {SeratoBinFile.get_relative_path(f).upper() for f in files}
        replaced: list[tuple[int, SeratoBinFile.EntryList]] = []
        for i, value in self._entry_lists(SeratoBinFile.Fields.TRACK):
            if relpaths is not None:
                # check the path first: building a Track, running func, and comparing the result costs far more
                relpath = self._get_entry_value(value, self.TRACK_PATH_KEY)
                if isinstance(relpath, str) and relpath.upper() not in relpaths:
                    continue
            track = self._get_track(value)
            # Track copies the values out of `value`, so this compares against the untouched original
            if (new_entries := func(track).to_entries()) != value:
                # set_value checks each value, but one assigned straight to an attribute, or a Track built by hand,
                # skips it; checking only changed tracks keeps a whole-library pass from re-checking values loaded
                for field, new_value in new_entries:
                    SeratoBinFile.check_value(field, new_value)
                replaced.append((i, new_entries))
        # replaced only once func has run for every track, so one that raises leaves the file unchanged
        for i, new_entries in replaced:
            self._entries[i] = (SeratoBinFile.Fields.TRACK.value, new_entries)
        return bool(replaced)

    def filter_tracks(self, func: Callable[[Track], bool]) -> bool:
        """Keeps only the tracks `func` returns True for, and returns whether any track was removed."""
        return self._filter_entry_lists(SeratoBinFile.Fields.TRACK, lambda value: func(self._get_track(value)))

    def remove_tracks(self, filepaths: Iterable[str]) -> bool:
        """Removes every track whose path is in `filepaths`, in one pass, and returns whether any was removed.

        Paths match whatever their case, as `modify_tracks` matches its `files`.
        """
        relpaths = {SeratoBinFile.get_relative_path(f).upper() for f in filepaths}
        return self.filter_tracks(lambda track: track.relpath.upper() not in relpaths)

    def remove_duplicates(self) -> bool:
        """Removes every repeat of an earlier track's path, and returns whether any were removed.

        A path repeats one in another case too, as `remove_tracks` matches paths whatever their case.
        """
        seen_track_paths: set[str] = set()

        def filter_track(track: "SeratoBinFile.Track") -> bool:
            relpath = track.relpath.upper()
            is_new = relpath not in seen_track_paths
            seen_track_paths.add(relpath)
            return is_new

        return self.filter_tracks(filter_track)

    def save(self, file: str | None = None, force: bool = False) -> bool:
        """Writes the file's bytes to `file`, or to the path it was loaded from, and returns whether it wrote them.

        Saving to its own path writes only if the file changed since it was loaded or last saved (`has_changed`), unless
        `force`; saving to any other path always writes. Serializes the file once, to check it and to write it.

        Raises RuntimeError if called before the initial parse has finished, e.g. from a subclass's __init__ before
        it calls super().__init__(), and ValueError for a path the class can't save to, such as a `.json` file.
        """
        if not self._parsed:
            raise RuntimeError(f"cannot save a {type(self).__name__} before it has finished parsing")
        if file is None:
            file = self.filepath
        if file.lower().endswith(".json"):
            raise ValueError("cannot save raw data to .json")
        # serialize before opening, since opening truncates and a serialization error would leave the file empty
        data = self.to_bytes()
        own_path = self._is_own_path(file)
        if own_path and not force and not self._differs_from_saved(data):
            return False
        with open(file, "wb") as f:
            f.write(data)
        # saving a copy elsewhere leaves this file's own changes unsaved
        if own_path:
            self._saved_hash = self._hash(data)
        return True

    @classmethod
    def get_field_name(cls, field: str) -> str:
        """A readable name for `field`, such as "File Path" for `pfil`, or "Unknown Field" if it isn't known."""
        return cls.FIELD_NAMES.get(field, "Unknown Field")

    @classmethod
    def _check_valid_field(cls, field: str):
        if field not in cls.FIELDS:
            raise ValueError(
                f"invalid field: {field} must be one of: {', '.join(sorted(cls.FIELDS))}\n(see {__file__} for what these keys map to)"
            )

    @staticmethod
    def get_relative_path(filepath: str) -> str:
        """`filepath` as Serato stores a track path: without its drive or leading slash, and `/`-separated."""
        filepath = os.path.splitdrive(filepath)[1]
        relpath = os.path.normpath(filepath).replace(os.path.sep, "/").lstrip("/")
        return relpath  # noqa: RET504

    @staticmethod
    def get_full_path(filepath: str) -> str:
        """Get the absolute, normalized form of a track path.

        - A path with a drive or UNC share keeps it.
        - A path without one, which is how Serato stores track paths, is resolved from the root of `SERATO_DRIVE`.

        Doesn't check that the file exists.
        """
        # with no drive, splitdrive's path half is the whole of filepath, so filepath serves both branches
        drive = os.path.splitdrive(filepath)[0]
        return os.path.normpath(filepath if drive else os.path.join(SERATO_DRIVE, os.sep, filepath))

    def get_entries(self, track_matcher: str | Pattern[str] | None = None) -> Generator[EntryFull, None, None]:
        """Each entry with its field's readable name, as is each entry in a nested entry list.

        Given `track_matcher`, a regex, only the tracks whose path it matches (ignoring case) are included. Raises
        DeeplyNestedListError for an entry list nested in a nested one.
        """
        for field, value in self._entries:
            if isinstance(value, list):
                if (
                    track_matcher
                    and field == SeratoBinFile.Fields.TRACK
                    and not re.search(track_matcher, self._get_track(value).relpath, re.IGNORECASE)
                ):
                    continue
                named: list[SeratoBinFile.EntryFull] = []
                for nested_field, nested_value in value:
                    if isinstance(nested_value, list):
                        raise DeeplyNestedListError(field, value)
                    named.append((nested_field, self.get_field_name(nested_field), nested_value))
                value = named

            yield field, self.get_field_name(field), value

    type ModifyFunc = Callable[[str, "SeratoBinFile.ValueOrNone"], "SeratoBinFile.ValueOrNone"]
    """ (filename: str, prev_value: ValueType | None) -> new_value: ValueType | None """

    class ModifyRule(TypedDict):
        """A change for `modify`: `func` gives `field`'s new value for each track, or for only those in `files`."""

        field: "SeratoBinFile.Fields"
        func: "SeratoBinFile.ModifyFunc"
        files: NotRequired[Collection[str]]

    def modify(self, rules: Collection[ModifyRule]) -> bool:
        """Applies `rules` to every track, and returns whether any track changed.

        A rule whose `func` returns `""` removes the field from the track, as Serato does when a tag is cleared. A rule
        for the track path can't remove it, and raises ValueError.
        """
        # check rule fields
        all_field_names = [rule["field"] for rule in rules]
        if len(all_field_names) != len(set(all_field_names)):
            raise ValueError(f"must only have 1 rule per field. fields passed: {sorted(all_field_names)}")
        for field in all_field_names:
            self._check_valid_field(field)

        # normalize file lists on copies, so the caller's rule dicts are not mutated
        rules = [cast("SeratoBinFile.ModifyRule", dict(rule)) for rule in rules]
        for rule in rules:
            if "files" in rule:
                rule["files"] = [SeratoBinFile.get_relative_path(file).upper() for file in rule["files"]]

        # if every rule is limited to certain files, no other track can change, so skip them entirely
        every_rule_limited = all("files" in rule for rule in rules)
        only_files = [f for r in rules for f in r.get("files", [])] if every_rule_limited else None

        # as sets, since each track is checked against them
        rule_files = [set(rule["files"]) if "files" in rule else None for rule in rules]

        def modify_track(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
            # loop over the rules rather than the track's fields, since a track has far more fields than there are rules
            relpath_upper = track.relpath.upper()
            for rule, files in zip(rules, rule_files, strict=True):
                if files is not None and relpath_upper not in files:
                    continue
                field = rule["field"]
                prev_val = track.get_value(field) if field in track.fields else None
                maybe_new_val = rule["func"](track.relpath, prev_val)
                if maybe_new_val == "":
                    # set_value would remove it too, but this logs it as a removal rather than a set
                    if track.remove_field(field):
                        logger.info(f"Removed {field}({self.get_field_name(field)}) in library for {track.relpath}")
                    continue
                if maybe_new_val is None or maybe_new_val == prev_val:
                    continue

                if field == self.TRACK_PATH_KEY:
                    maybe_new_val = expect_type(maybe_new_val, str, field)
                    if not os.path.exists(SeratoBinFile.get_full_path(maybe_new_val)):
                        raise FileNotFoundError(f"set track location to {maybe_new_val}, but doesn't exist")
                    maybe_new_val = SeratoBinFile.get_relative_path(maybe_new_val)

                logger.info(
                    f"Set {field}({self.get_field_name(field)})={maybe_new_val!s} in library for {track.relpath}"
                )
                track.set_value(field, maybe_new_val)
            return track

        return self.modify_tracks(modify_track, files=only_files)

    def modify_and_save(self, rules: Collection[ModifyRule], file: str | None = None):
        """
        Applies `rules` to every track, then saves.

        Skips the save when nothing changed, unless `file` names somewhere other than this file's own path.
        """
        changed = self.modify(rules)
        if changed or (file is not None and not self._is_own_path(file)):
            self.save(file)

    def change_track_path(self, src: str, dest: str) -> bool:
        """Points the track at `src` to `dest`, and returns whether this file had that track."""
        return self.modify([{"field": self.TRACK_PATH_KEY, "files": [src], "func": lambda *args: dest}])

    def find_missing(self):
        """Prompts for a new location for each track whose file doesn't exist, then saves if any was given.

        Each answer can be the file's new path; a folder, where it and later missing tracks are looked for by name; or
        "s" to skip it. Interrupting a prompt (Ctrl-C, or input running out) leaves every track as it was.
        """
        new_dir: str | None = None

        def relocate(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
            nonlocal new_dir
            track_path = track.full_path
            if os.path.isfile(track_path):
                return track
            print(f"missing: {track_path}")  # noqa: T201
            filename = os.path.basename(track_path)
            new_location = None
            if new_dir is not None and os.path.isfile(in_new_dir := os.path.join(new_dir, filename)):
                new_location = in_new_dir
            while not new_location:
                answer = os.path.normpath(
                    input('enter new location of file, or directory to look for missing files, or "s" to skip:')
                    .strip()
                    .strip('"')
                )
                if answer == "s":
                    return track
                if os.path.isdir(answer):
                    new_dir = answer
                    answer = os.path.join(new_dir, filename)
                if os.path.exists(answer):
                    new_location = answer
            print("   new_location: " + new_location)  # noqa: T201
            track.set_path(new_location)
            return track

        if self.modify_tracks(relocate):
            self.save()
