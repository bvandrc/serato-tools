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
from enum import StrEnum, unique
from typing import Any, Callable, Collection, Generator, Iterable, NotRequired, Optional, Pattern, TypedDict, cast

from serato_tools.utils import SERATO_DRIVE, logger


class DataTypeError(Exception):
    """A value whose type doesn't match the one its field holds."""

    def __init__(self, value: Any, expected_type: type, field: str | None):
        super().__init__(
            f"value must be {expected_type.__name__} when field is {field} (type: {type(value).__name__}) (value: {str(value)})"
        )


class DeeplyNestedListError(Exception):
    """An entry list nested inside a flat one, such as a track's, which this package can't parse into objects."""

    def __init__(self):
        super().__init__("unexpected type, deeply nested list. if this occurs, need to implement code for it.")


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

    # derived from FIELD_ENUMS so the two can't drift; redefine it alongside FIELD_ENUMS in a subclass
    FIELDS = frozenset(f.value for field_enum in FIELD_ENUMS for f in field_enum)

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
    DEFAULT_ENTRIES: EntryList

    # set once __init__ has parsed the file, so save() can refuse a half-built instance
    _parsed: bool = False

    # a hash of the file's bytes as loaded or last saved to its own path, for has_changed; None if it didn't exist
    _saved_hash: bytes | None = None

    def __init__(self, file: str):
        """Parses `file`, either Serato's binary format or JSON as `write_json` writes it.

        A file that doesn't exist yet starts from `DEFAULT_ENTRIES`, and `save()` creates it. Raises ValueError for a
        version not in `TESTED_VERSIONS`.
        """
        self.filepath = os.path.abspath(file)

        self.entries: SeratoBinFile.EntryList
        self.version: str

        for key in ["TESTED_VERSIONS", "TRACK_PATH_KEY", "DEFAULT_ENTRIES"]:
            if not hasattr(self, key):
                raise AttributeError(f"need to set {key} in subclass")

        if os.path.exists(file):
            if file.lower().endswith(".json"):
                with open(file, "r", encoding="utf-8") as f:
                    self.from_json_object(json.load(f))
                # what saving the entries as loaded would write
                self._saved_hash = self._hash(self.to_bytes())
            else:
                with open(file, "rb") as f:
                    data = f.read()
                self.entries = list(self._parse_item(data))
                # hashes the bytes already read rather than copying the entries, so a load that only reads pays
                # next to nothing for has_changed
                self._saved_hash = self._hash(data)
        else:
            logger.warning(f"File does not exist: {file}. Using default data to create an empty item.")
            # copied down to the nested lists (osrt, ovct, ...): a shallow copy would leave every instance sharing —
            # and able to mutate — the class-level DEFAULT_ENTRIES sublists.
            self.entries = copy.deepcopy(self.DEFAULT_ENTRIES)
            version_entry = self.entries[0]
            default_version = version_entry[1]
            if not isinstance(default_version, str):
                raise DataTypeError(default_version, str, version_entry[0])
            if default_version not in self.TESTED_VERSIONS:
                raise ValueError("version in DEFAULT_ENTRIES is not in TESTED_VERSIONS")
            self.version = default_version

        if not hasattr(self, "version"):
            raise AttributeError("version not set after parsing file")

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
                lines.append(f"{indent_str}{field} ({fieldname}): {str(value)}")

        return "\n".join(lines)

    def _check_version(self, value: Value, set_version: bool = False):
        """Raises unless `value` is one of `TESTED_VERSIONS`; with `set_version`, also records it as `self.version`."""
        if not isinstance(value, str):
            raise DataTypeError(value, str, SeratoBinFile.Fields.VERSION)
        if value not in self.TESTED_VERSIONS:
            raise ValueError(f"""
                ERROR: Untested version Serato bin file version: {value}
                Please contact the developer so we can get it tested and supported!
                We will have you send the file you are trying to parse so we can add support and tests for it.
                We do not want to risk damaging users' library database or crate files!

                Possible versions:
                {'\n'.join(sorted(self.TESTED_VERSIONS))}
                """)
        if set_version:
            self.version = value

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

        return entries_to_json(self.entries)

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
                    self._check_version(value, set_version=True)
                    version_set = True

                result.append((field, value))

            return result

        entries = json_to_entries(json_data)
        # JSON types aren't tied to field prefixes the way the binary format is, so check now that it serializes,
        # rather than failing on the first save. Checked before assigning, so a bad file leaves entries as they were.
        self._serialize_entries(entries)
        self.entries = entries

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
        print(self)

    class EntryListCls:
        """A flat entry list, such as a track's, with each field's value as an attribute named for the field.

        Holds copies of the values, so changes reach the file only through `to_entries()`. Raises
        DeeplyNestedListError for a nested entry list, and ValueError for a repeated field.
        """

        def __init__(self, entries: "SeratoBinFile.EntryList"):
            self.fields: list[str] = []

            for field, value in entries:
                if isinstance(value, list):
                    raise DeeplyNestedListError
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

        def get_value(self, field: str) -> "SeratoBinFile.Value":
            return getattr(self, field)

        def set_value(self, field: str, value: "SeratoBinFile.Value"):
            """Sets `field`'s value, adding the field after the others if it isn't set yet."""
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
            relative_path = self.get_value(path_key)
            if not isinstance(relative_path, str):
                raise DataTypeError(relative_path, str, path_key)
            self.relpath: str = relative_path

        def set_value(self, field: str, value: "SeratoBinFile.Value"):
            """Sets `field` to `value`.

            An empty string removes the field instead, as Serato does when a tag is cleared, so a track never stores
            one empty.
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
            relpath = SeratoBinFile.get_relative_path(path)
            self.set_value(self.path_key, relpath)
            self.relpath = relpath

        def get_full_path(self):
            """The track's absolute path, which is its `relpath` on `SERATO_DRIVE`."""
            return SeratoBinFile.get_full_path(self.relpath)

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
                # value = (data[1:] + b"\00").decode("utf-16") # from imported code
                value = data.decode("utf-16-be")
            elif type_id == "b":  # single byte, is a boolean
                # anything but 0x00/0x01 would be rewritten as 0x01 on save, so refuse it like an unknown version
                if data not in (b"\x00", b"\x01"):
                    raise ValueError(f"unexpected boolean value for field {field}: {data!r}")
                value = cast(bool, struct.unpack("?", data)[0])
            elif type_id == "s":  # unsigned 16-bit int
                value = cast(int, struct.unpack(">H", data)[0])
            elif type_id == "u":  # unsigned int
                value = cast(int, struct.unpack(">I", data)[0])
            else:
                raise ValueError(f"unexpected type for field: {field}")

            if not version_set and field == SeratoBinFile.Fields.VERSION:
                self._check_version(value, set_version=True)
                version_set = True

            yield field, value

    def _serialize_item(self, entry: Entry) -> bytes:
        """An entry's bytes: its header, then its value encoded as its field's type requires."""
        field, value = entry
        field_bytes = field.encode("ascii")
        if len(field_bytes) != 4:
            raise ValueError(f"field names are 4 characters: {field!r}")

        if field == SeratoBinFile.Fields.VERSION:
            self._check_version(value)
            if value != self.version:
                raise ValueError(f"version field value {value} does not match parsed value {self.version}")

        type_id: str = SeratoBinFile._get_type(field)

        if type_id in ("o", "r"):  #  struct (list)
            if not isinstance(value, list):
                raise DataTypeError(value, list, field)
            data = self._serialize_entries(value)
        elif type_id in ("p", "t"):  # text
            if not isinstance(value, str):
                raise DataTypeError(value, str, field)
            data = value.encode("utf-16-be")
        elif type_id == "b":  # single byte, is a boolean
            if not isinstance(value, bool):
                raise DataTypeError(value, bool, field)
            data = struct.pack("?", value)
        elif type_id == "s":  # unsigned 16-bit int
            if not isinstance(value, int):
                raise DataTypeError(value, int, field)
            data = struct.pack(">H", value)
        elif type_id == "u":  # unsigned int
            if not isinstance(value, int):
                raise DataTypeError(value, int, field)
            data = struct.pack(">I", value)
        else:
            raise ValueError(f"unexpected type for field: {field}")

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
        return self._serialize_entries(self.entries)

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

    def get_tracks(self) -> Generator[Track, None, None]:
        """Each track entry, as a `Track`.

        A `Track` holds copies of the entry's values, so changing one doesn't change the file: use `modify_tracks`.
        """
        for field, value in self.entries:
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                track = self._get_track(value)
                yield track

    def get_track_paths(self, include_drive: bool = False) -> list[str]:
        """Each track's path: as stored, with no drive, or with `include_drive`, as an absolute path."""
        return [t.get_full_path() if include_drive else t.relpath for t in self.get_tracks()]

    def modify_tracks(self, func: Callable[[Track], Track], files: Optional[Iterable[str]] = None) -> bool:
        """
        Replaces each track with what `func` returns for it, and returns whether any track changed.

        Given `files`, only those tracks are passed to `func`, and the rest are skipped after reading just their path,
        which is much faster on a large library.
        """
        relpaths = None if files is None else {SeratoBinFile.get_relative_path(f).upper() for f in files}
        changed = False
        for i, (field, value) in enumerate(self.entries):
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                if relpaths is not None:
                    # check the path first: building a Track, running func, and comparing the result costs far more
                    relpath = self._get_entry_value(value, self.TRACK_PATH_KEY)
                    if isinstance(relpath, str) and relpath.upper() not in relpaths:
                        continue
                track = self._get_track(value)
                # Track copies the values out of `value`, so this compares against the untouched original
                new_entries = func(track).to_entries()
                if new_entries != value:
                    self.entries[i] = (field, new_entries)
                    changed = True
        return changed

    def filter_tracks(self, func: Callable[[Track], bool]) -> bool:
        """Keeps only the tracks `func` returns True for, and returns whether any track was removed."""
        new_entries: "SeratoBinFile.EntryList" = []
        for field, value in self.entries:
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                track = self._get_track(value)
                if not func(track):
                    continue
            new_entries.append((field, value))
        removed = len(new_entries) != len(self.entries)
        self.entries = new_entries
        return removed

    def remove_tracks(self, filepaths: Iterable[str]) -> bool:
        """Removes every track whose path is in `filepaths`, in one pass, and returns whether any was removed."""
        relpaths = {SeratoBinFile.get_relative_path(f) for f in filepaths}
        return self.filter_tracks(lambda track: track.relpath not in relpaths)

    def remove_duplicates(self) -> bool:
        """Removes every repeat of an earlier track's path, and returns whether any were removed."""
        seen_track_paths: set[str] = set()

        def filter_track(track: "SeratoBinFile.Track") -> bool:
            is_new = track.relpath not in seen_track_paths
            seen_track_paths.add(track.relpath)
            return is_new

        return self.filter_tracks(filter_track)

    def save(self, file: Optional[str] = None, force: bool = False) -> bool:
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
        # a map built once per class, since printing or JSON-dumping a large database names every field; checked in
        # vars(cls), not by attribute, so a subclass with its own FIELD_ENUMS doesn't use the base's map
        if "_field_names" not in vars(cls):
            cls._field_names = {
                # DATE_ADDED_T and DATE_ADDED_U hold the same time, so both are "Date Added"
                member.value: member.name.replace("_", " ")
                .title()
                .replace("Smartcrate", "SmartCrate")
                .replace("Added U", "Added")
                .replace("Added T", "Added")
                for field_enum in cls.FIELD_ENUMS
                for member in field_enum
            }
        return cls._field_names.get(field, "Unknown Field")

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
        return relpath

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

    def get_entries(self) -> Generator[EntryFull, None, None]:
        """Get entry fieldnames."""
        yield from self.__get_entries_internal(track_matcher=None)

    def get_entries_filtered(self, track_matcher: str | Pattern[str]) -> Generator[EntryFull, None, None]:
        """Get entry fieldnames with track matching filter."""
        yield from self.__get_entries_internal(track_matcher=track_matcher)

    def __get_entries_internal(self, track_matcher: Optional[str | Pattern[str]]) -> Generator[EntryFull, None, None]:
        """Internal implementation for getting entry fieldnames."""
        for field, value in self.entries:
            if isinstance(value, list):
                if track_matcher and field == SeratoBinFile.Fields.TRACK:
                    if not isinstance(value, list):
                        raise DataTypeError(value, list, field)
                    track = self.__class__.Track(value, path_key=self.TRACK_PATH_KEY)
                    if not bool(re.search(track_matcher, track.relpath, re.IGNORECASE)):
                        continue

                try:
                    new_entries: list[SeratoBinFile.EntryFull] = []
                    for f, v in value:
                        if isinstance(v, list):
                            raise DeeplyNestedListError
                        new_entries.append((f, self.get_field_name(f), v))
                except:
                    logger.error(f"error on field: {field} value: {value}")
                    raise
                value = new_entries

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
            for rule, files in zip(rules, rule_files):
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
                    if not isinstance(maybe_new_val, str):
                        raise DataTypeError(maybe_new_val, str, field)
                    if not os.path.exists(SeratoBinFile.get_full_path(maybe_new_val)):
                        raise FileNotFoundError(f"set track location to {maybe_new_val}, but doesn't exist")
                    maybe_new_val = SeratoBinFile.get_relative_path(maybe_new_val)

                logger.info(
                    f"Set {field}({self.get_field_name(field)})={str(maybe_new_val)} in library for {track.relpath}"
                )
                track.set_value(field, maybe_new_val)
            return track

        return self.modify_tracks(modify_track, files=only_files)

    def modify_and_save(self, rules: Collection[ModifyRule], file: Optional[str] = None):
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
        "s" to skip it.
        """
        new_entries: SeratoBinFile.EntryList = []
        new_dir: str | None = None
        changed = False
        for field, value in self.entries:
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                track = self._get_track(value)
                track_path = track.get_full_path()
                if not os.path.isfile(track_path):
                    print(f"missing: {track_path}")
                    new_location = None
                    if new_dir is not None:
                        if os.path.isfile(possible_new_loc := os.path.join(new_dir, os.path.basename(track_path))):
                            new_location = possible_new_loc
                    if not new_location:
                        while True:
                            new_location = os.path.normpath(
                                input(
                                    'enter new location of file, or directory to look for missing files, or "s" to skip:'
                                )
                                .strip()
                                .strip('"')
                            )
                            if new_location == "s":
                                new_location = None
                                break
                            if os.path.isdir(new_location):
                                new_dir = new_location
                                new_location = os.path.join(new_dir, os.path.basename(track_path))
                            if os.path.exists(new_location):
                                break
                    if new_location:
                        print("   new_location: " + new_location)
                        track.set_path(new_location)
                        changed = True
                value = track.to_entries()
            new_entries.append((field, value))
        self.entries = new_entries
        if changed:
            self.save()
