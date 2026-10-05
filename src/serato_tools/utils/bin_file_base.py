import os
import io
import re
import copy
import struct
import base64
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
        # Smart Crates
        SMARTCRATE_RULE = "rurt"
        SMARTCRATE_LIVE_UPDATE = "rlut"
        SMARTCRATE_MATCH_ALL = "rart"
        RULE_VALUE_TEXT = "trpt"
        RULE_VALUE_DATE = "trtt"
        RULE_VALUE_INTEGER = "urpt"
        RULE_COMPARISON = "trft"
        RULE_FIELD = "urkt"

    FIELDS = list(f.value for f in Fields)

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

    def __init__(self, file: str):
        self.filepath = os.path.abspath(file)

        self.raw_data: bytes
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
                    self.raw_data = f.read()
                    self.entries = list(self._parse_item(self.raw_data))
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
            self._dump()

        if not hasattr(self, "version"):
            raise AttributeError("version not set after parsing file")

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
                    "fieldname": SeratoBinFile.get_field_name(field),
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

        self.entries = json_to_entries(json_data)
        self._dump()

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

    def __repr__(self) -> str:
        return str(self.raw_data)

    class EntryListCls:
        def __init__(self, entries: "SeratoBinFile.EntryList"):
            self.fields: list[str] = []

            for field, value in entries:
                if isinstance(value, list):
                    raise DeeplyNestedListError
                if field in self.fields:
                    # values are stored as attributes, so a repeated field would silently overwrite the
                    # earlier value and then be written back twice — corrupting the file on round-trip
                    raise ValueError(f"duplicate field in entry: {field}")
                setattr(self, field, value)
                self.fields.append(field)

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

    def _dump_item(self, entry: Entry) -> bytes:
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
            data = self._dump_entries(value)
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

    def _dump_entries(self, entries: EntryList):
        return b"".join(self._dump_item(entry) for entry in entries)

    def _dump(self):
        self.raw_data = self._dump_entries(self.entries)

    def get_tracks(self) -> Generator[Track, None, None]:
        for field, value in self.entries:
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                track = self._get_track(value)
                yield track

    def get_track_paths(self, include_drive: bool = False) -> list[str]:
        return [t.get_full_path() if include_drive else t.relpath for t in self.get_tracks()]

    def modify_tracks(self, func: Callable[[Track], Track]):
        for i, (field, value) in enumerate(self.entries):
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                track = self._get_track(value)
                new_track = func(track)
                self.entries[i] = (field, new_track.to_entries())
        self._dump()

    def filter_tracks(self, func: Callable[[Track], bool]):
        new_entries: "SeratoBinFile.EntryList" = []
        for field, value in self.entries:
            if field == SeratoBinFile.Fields.TRACK:
                if not isinstance(value, list):
                    raise DataTypeError(value, list, field)
                track = self._get_track(value)
                if not func(track):
                    continue
            new_entries.append((field, value))
        self.entries = new_entries
        self._dump()

    def remove_track(self, filepath: str):
        self.filter_tracks(lambda track: track.relpath != SeratoBinFile.get_relative_path(filepath))

    def remove_duplicates(self):
        track_paths: list[str] = []

        def filter_track(track: "SeratoBinFile.Track") -> bool:
            was_in_track_paths = track.relpath not in track_paths
            track_paths.append(track.relpath)
            return was_in_track_paths

        self.filter_tracks(filter_track)

    def save(self, file: Optional[str] = None):
        if file is None:
            file = self.filepath
        if file.lower().endswith(".json"):
            raise ValueError("cannot save raw data to .json")
        with open(file, "wb") as f:
            f.write(self.raw_data)

    @staticmethod
    def get_field_name(field: str) -> str:
        try:
            return (
                get_enum_key_from_value(field, SeratoBinFile.Fields)
                .replace("_", " ")
                .title()
                .replace("Smartcrate", "SmartCrate")
                .replace("Added U", "Added")
                .replace("Added T", "Added")
            )
        except ValueError:
            return "Unknown Field"

    @staticmethod
    def _check_valid_field(field: str):
        if field not in SeratoBinFile.FIELDS:
            raise ValueError(
                f"invalid field: {field} must be one of: {str(SeratoBinFile.FIELDS)}\n(see {__file__} for what these keys map to)"
            )

    @staticmethod
    def get_relative_path(filepath: str) -> str:
        filepath = os.path.splitdrive(filepath)[1]
        relpath = os.path.normpath(filepath).replace(os.path.sep, "/").lstrip("/")
        return relpath

    @staticmethod
    def get_full_path(filepath: str):
        drive, filepath = os.path.splitdrive(filepath)
        if drive:
            return filepath
        else:
            return os.path.normpath(os.path.join(SERATO_DRIVE, "\\", filepath))

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
                        new_entries.append((f, SeratoBinFile.get_field_name(f), v))
                except:
                    logger.error(f"error on field: {field} value: {value}")
                    raise
                value = new_entries

            yield field, SeratoBinFile.get_field_name(field), value

    class ModifyRule(TypedDict):
        field: "SeratoBinFile.Fields"
        func: Callable[[str, "SeratoBinFile.ValueOrNone"], "SeratoBinFile.ValueOrNone"]
        """ (filename: str, prev_value: ValueType | None) -> new_value: ValueType | None """
        files: NotRequired[list[str]]

    def modify(self, rules: list[ModifyRule]):
        # check rule fields
        all_field_names = [rule["field"] for rule in rules]
        assert len(list(rules)) == len(
            list(set(all_field_names))
        ), f"must only have 1 function per field. fields passed: {str(sorted(all_field_names))}"
        for field in all_field_names:
            SeratoBinFile._check_valid_field(field)

        # normalize file lists on copies, so the caller's rule dicts are not mutated
        rules = [cast("SeratoBinFile.ModifyRule", dict(rule)) for rule in rules]
        for rule in rules:
            if "files" in rule:
                rule["files"] = [SeratoBinFile.get_relative_path(file).upper() for file in rule["files"]]

        def _maybe_perform_rule(field: str, prev_val: "SeratoBinFile.ValueOrNone", track_relpath: str):
            rule = next((r for r in rules if field == r["field"]), None)
            if rule is None:
                return None
            if "files" in rule and track_relpath.upper() not in rule["files"]:
                return None

            maybe_new_value = rule["func"](track_relpath, prev_val)
            if maybe_new_value is None or maybe_new_value == prev_val:
                return None

            if field == self.TRACK_PATH_KEY:
                if not isinstance(maybe_new_value, str):
                    raise DataTypeError(maybe_new_value, str, field)
                if not os.path.exists(SeratoBinFile.get_full_path(maybe_new_value)):
                    raise FileNotFoundError(f"set track location to {maybe_new_value}, but doesn't exist")
                maybe_new_value = SeratoBinFile.get_relative_path(maybe_new_value)

            field_name = SeratoBinFile.get_field_name(field)
            logger.info(f"Set {field}({field_name})={str(maybe_new_value)} in library for {track_relpath}")
            return maybe_new_value

        def modify_track(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
            for f, v in track.to_entries():
                maybe_new_value = _maybe_perform_rule(f, v, track.relpath)
                if maybe_new_value is not None:
                    track.set_value(f, maybe_new_value)
            for rule in rules:
                if rule["field"] not in track.fields:
                    maybe_new_value = _maybe_perform_rule(rule["field"], None, track.relpath)
                    if maybe_new_value is not None:
                        track.set_value(rule["field"], maybe_new_value)
            return track

        self.modify_tracks(modify_track)

    def modify_and_save(self, rules: list[ModifyRule], file: Optional[str] = None):
        self.modify(rules)
        self.save(file)

    def change_track_path(self, src: str, dest: str):
        self.modify([{"field": self.TRACK_PATH_KEY, "files": [src], "func": lambda *args: dest}])

    def find_missing(self):
        new_entries: SeratoBinFile.EntryList = []
        new_dir: str | None = None
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
                value = track.to_entries()
            new_entries.append((field, value))
        self.entries = new_entries
        self._dump()
        self.save()
