import os
import io
import re
import copy
import struct
import base64
import warnings
from enum import StrEnum
import json
from typing import Iterable, TypedDict, Generator, Optional, cast, Callable, Pattern, NotRequired

from serato_tools.utils import get_enum_key_from_value, logger, SERATO_DRIVE, DataTypeError, DeeplyNestedListError


class SeratoBinFile:

    class Fields(StrEnum):
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
        DATE_ADDED_T = "tadd"
        DATE_ADDED_U = "uadd"
        BEATGRID_LOCKED = "bbgl"
        CORRUPT = "bcrt"
        MISSING = "bmis"
        HAS_STEMS = "bstm"
        PLAYED = "bply"
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
    FIELDS = [f.value for field_enum in FIELD_ENUMS for f in field_enum]

    type ParsedField = Fields | str
    type BasicValue = str | bytes | int | bool

    type Entry = tuple[ParsedField, "SeratoBinFile.Value"]
    type EntryList = list[Entry]
    type Value = BasicValue | EntryList

    type EntryFull = tuple[ParsedField, str, "SeratoBinFile.EntryFullValue"]
    type EntryFullList = list[EntryFull]
    type EntryFullValue = BasicValue | EntryFullList

    type ValueOrNone = Value | None

    TESTED_VERSIONS: list[str]
    TRACK_PATH_KEY: Fields
    DEFAULT_ENTRIES: EntryList

    # set once __init__ has parsed the file, so save() can refuse a half-built instance
    _parsed: bool = False

    def __init__(self, file: str):
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
            else:
                with open(file, "rb") as f:
                    self.entries = list(self._parse_item(f.read()))
        else:
            logger.warning(f"File does not exist: {file}. Using default data to create an empty item.")
            # deep copy: nested values (osrt, ovct, ...) are lists too, and a shallow copy would leave every
            # instance sharing — and able to mutate — the class-level DEFAULT_ENTRIES sublists.
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
        if not isinstance(value, str):
            raise DataTypeError(value, str, SeratoBinFile.Fields.VERSION)
        if value not in self.TESTED_VERSIONS:
            raise ValueError(f"""
                ERROR: Untested version Serato bin file version: {value}
                Please contact the developer so we can get it tested and supported!
                We will have you send the file you are trying to parse so we can add support and tests for it.
                We do not want to risk damaging users' library database or crate files!

                Possible versions:
                {'\n'.join(self.TESTED_VERSIONS)}
                """)
        if set_version:
            self.version = value

    class EntryJson(TypedDict):
        field: "SeratoBinFile.ParsedField"
        fieldname: str
        type: str
        value: str | int | bool | list["SeratoBinFile.EntryJson"]

    def to_json_object(self) -> list[EntryJson]:
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
            if field not in self.fields:
                self.fields.append(field)
            setattr(self, field, value)

        def to_entries(self) -> "SeratoBinFile.EntryList":
            return [(f, self.get_value(f)) for f in self.fields]

    class Track(EntryListCls):
        def __init__(self, entries: "SeratoBinFile.EntryList", path_key: str):
            super().__init__(entries)

            self.path_key = path_key
            relative_path = self.get_value(path_key)
            if not isinstance(relative_path, str):
                raise DataTypeError(relative_path, str, path_key)
            self.relpath: str = relative_path

        def set_path(self, path: str):
            relpath = SeratoBinFile.get_relative_path(path)
            self.set_value(self.path_key, relpath)
            self.relpath = relpath

        def get_full_path(self):
            return SeratoBinFile.get_full_path(self.relpath)

    def _get_track(self, entries: "SeratoBinFile.EntryList"):
        return SeratoBinFile.Track(entries, path_key=self.TRACK_PATH_KEY)

    @staticmethod
    def _get_entry_value(entries: "SeratoBinFile.EntryList", field: str) -> "SeratoBinFile.ValueOrNone":
        """The value of the first entry named `field`, or None if there isn't one."""
        return next((v for f, v in entries if f == field), None)

    @staticmethod
    def _get_type(field: str) -> str:
        # vrsn field has no type_id, but contains text ("t")
        return "t" if field == SeratoBinFile.Fields.VERSION else field[0]

    def _parse_item(self, item_data: bytes) -> Generator["SeratoBinFile.Entry", None, None]:
        fp = io.BytesIO(item_data)
        version_set = False
        for header in iter(lambda: fp.read(8), b""):
            assert len(header) == 8
            field_ascii: bytes
            length: int
            field_ascii, length = struct.unpack(">4sI", header)
            field: str = field_ascii.decode("ascii")
            type_id: str = SeratoBinFile._get_type(field)

            data = fp.read(length)
            assert len(data) == length

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
        field, value = entry
        field_bytes = field.encode("ascii")
        assert len(field_bytes) == 4

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

    def get_tracks(self) -> Generator[Track, None, None]:
        for field, value in self.entries:
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                track = self._get_track(value)
                yield track

    def get_track_paths(self, include_drive: bool = False) -> list[str]:
        return [t.get_full_path() if include_drive else t.relpath for t in self.get_tracks()]

    def modify_tracks(self, func: Callable[[Track], Track], files: Optional[list[str]] = None) -> bool:
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

    def remove_track(self, filepath: str) -> bool:
        """Deprecated, to be removed in the next major version: use remove_tracks(), which this calls."""
        warnings.warn("remove_track is deprecated, use remove_tracks instead", DeprecationWarning, stacklevel=2)
        return self.remove_tracks([filepath])

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

    def save(self, file: Optional[str] = None):
        """
        Writes the file's bytes to `file`, or to the path it was loaded from.

        Raises RuntimeError if called before the initial parse has finished, e.g. from a subclass's __init__ before
        it calls super().__init__().
        """
        if not self._parsed:
            raise RuntimeError(f"cannot save a {type(self).__name__} before it has finished parsing")
        if file is None:
            file = self.filepath
        if file.lower().endswith(".json"):
            raise ValueError("cannot save raw data to .json")
        # serialize before opening, since opening truncates and a serialization error would leave the file empty
        data = self.to_bytes()
        with open(file, "wb") as f:
            f.write(data)

    @classmethod
    def get_field_name(cls, field: str) -> str:
        for field_enum in cls.FIELD_ENUMS:
            try:
                return (
                    get_enum_key_from_value(field, field_enum)
                    .replace("_", " ")
                    .title()
                    .replace("Smartcrate", "SmartCrate")
                    .replace("Added U", "Added")
                    .replace("Added T", "Added")
                )
            except ValueError:
                continue
        return "Unknown Field"

    @classmethod
    def _check_valid_field(cls, field: str):
        if field not in cls.FIELDS:
            raise ValueError(
                f"invalid field: {field} must be one of: {str(cls.FIELDS)}\n(see {__file__} for what these keys map to)"
            )

    @staticmethod
    def get_relative_path(filepath: str) -> str:
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
        return os.path.normpath(filepath if drive else os.path.join(SERATO_DRIVE, "\\", filepath))

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

    class ModifyRule(TypedDict):
        field: "SeratoBinFile.Fields"
        func: Callable[[str, "SeratoBinFile.ValueOrNone"], "SeratoBinFile.ValueOrNone"]
        """ (filename: str, prev_value: ValueType | None) -> new_value: ValueType | None """
        files: NotRequired[list[str]]

    def modify(self, rules: list[ModifyRule]) -> bool:
        """Applies `rules` to every track, and returns whether any track changed."""
        # check rule fields
        all_field_names = [rule["field"] for rule in rules]
        assert len(list(rules)) == len(
            list(set(all_field_names))
        ), f"must only have 1 function per field. fields passed: {str(sorted(all_field_names))}"
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

        def _maybe_perform_rule(
            rule: "SeratoBinFile.ModifyRule", prev_val: "SeratoBinFile.ValueOrNone", track_relpath: str
        ):
            field = rule["field"]
            maybe_new_value = rule["func"](track_relpath, prev_val)
            if maybe_new_value is None or maybe_new_value == prev_val:
                return None

            if field == self.TRACK_PATH_KEY:
                if not isinstance(maybe_new_value, str):
                    raise DataTypeError(maybe_new_value, str, field)
                if not os.path.exists(SeratoBinFile.get_full_path(maybe_new_value)):
                    raise FileNotFoundError(f"set track location to {maybe_new_value}, but doesn't exist")
                maybe_new_value = SeratoBinFile.get_relative_path(maybe_new_value)

            field_name = self.get_field_name(field)
            logger.info(f"Set {field}({field_name})={str(maybe_new_value)} in library for {track_relpath}")
            return maybe_new_value

        def modify_track(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
            # loop over the rules rather than the track's fields, since a track has far more fields than there are rules
            relpath_upper = track.relpath.upper()
            for rule, files in zip(rules, rule_files):
                if files is not None and relpath_upper not in files:
                    continue
                field = rule["field"]
                prev_val = track.get_value(field) if field in track.fields else None
                maybe_new_value = _maybe_perform_rule(rule, prev_val, track.relpath)
                if maybe_new_value is not None:
                    track.set_value(field, maybe_new_value)
            return track

        return self.modify_tracks(modify_track, files=only_files)

    def modify_and_save(self, rules: list[ModifyRule], file: Optional[str] = None):
        """
        Applies `rules` to every track, then saves.

        Skips the save when nothing changed, unless `file` names somewhere other than this file's own path.
        """
        changed = self.modify(rules)
        same_file = file is None or os.path.normcase(os.path.abspath(file)) == os.path.normcase(self.filepath)
        if changed or not same_file:
            self.save(file)

    def change_track_path(self, src: str, dest: str) -> bool:
        """Points the track at `src` to `dest`, and returns whether this file had that track."""
        return self.modify([{"field": self.TRACK_PATH_KEY, "files": [src], "func": lambda *args: dest}])

    def find_missing(self):
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
                        possible_new_loc = os.path.join(new_dir, os.path.basename(track_path))
                        if os.path.isfile(possible_new_loc):
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
