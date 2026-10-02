import os
import sys
from typing import cast
from enum import StrEnum, IntEnum
from dataclasses import dataclass

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.crate_base import CrateBase
from serato_tools.utils import get_enum_key_from_value, parse_cli_keys_and_values, SERATO_DIR, DataTypeError


class SmartCrate(CrateBase):
    TESTED_VERSIONS = ["1.0/Serato ScratchLive Smart Crate"]
    EXTENSION = ".scrate"
    DIR = "SmartCrates"
    DIR_PATH = os.path.join(SERATO_DIR, DIR)

    class RuleField(IntEnum):
        ADDED = 25
        ALBUM = 8
        ARTIST = 7
        BPM = 15
        COMMENT = 17
        COMPOSER = 22
        FILENAME = 4
        GENRE = 9
        GROUPING = 19
        KEY = 51
        LABEL = 21
        PLAYS = 79
        REMIXER = 20
        SONG = 6
        YEAR = 23

    class RuleComparison(StrEnum):
        STR_CONTAINS = "cond_con_str"
        STR_DOES_NOT_CONTAIN = "cond_dnc_str"
        STR_IS = "cond_is_str"
        STR_IS_NOT = "cond_isn_str"
        STR_DATE_BEFORE = "cond_bef_str"
        STR_DATE_AFTER = "cond_aft_str"
        TIME_IS_BEFORE = "cond_bef_time"
        TIME_IS_AFTER = "cond_aft_time"
        INT_IS_GE = "cond_greq_uint"
        INT_IS_LE = "cond_lseq_uint"

    DEFAULT_ENTRIES = [
        (CrateBase.Fields.VERSION, "1.0/Serato ScratchLive Smart Crate"),
        (CrateBase.Fields.SMARTCRATE_MATCH_ALL, [("brut", False)]),
        (CrateBase.Fields.SMARTCRATE_LIVE_UPDATE, [("brut", False)]),
        (CrateBase.Fields.SORTING, [(CrateBase.Fields.COLUMN_NAME, "key"), (CrateBase.Fields.REVERSE_ORDER, False)]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "song"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "playCount"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "artist"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "bpm"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "key"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "album"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "length"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "comment"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
        (CrateBase.Fields.COLUMN, [(CrateBase.Fields.COLUMN_NAME, "added"), (CrateBase.Fields.COLUMN_WIDTH, "0")]),
    ]

    @staticmethod
    def _get_rule_field_from_val(value: int) -> str:
        return get_enum_key_from_value(value, SmartCrate.RuleField)

    @staticmethod
    def _get_rule_comparison_from_val(value: str) -> str:
        return get_enum_key_from_value(value, SmartCrate.RuleComparison)

    @staticmethod
    def _get_rule_field_from_key(key: str):
        try:
            return SmartCrate.RuleField[key.upper()]
        except KeyError as exc:
            raise KeyError(
                f"bad field {key.upper()} , must be one of {[c.name for c in SmartCrate.RuleField]}"
            ) from exc

    @staticmethod
    def _get_rule_comparison_from_key(key: str):
        try:
            return SmartCrate.RuleComparison[key.upper()]
        except KeyError as exc:
            raise KeyError(
                f"bad comparison {key.upper()} , must be one of {[c.name for c in SmartCrate.RuleComparison]}"
            ) from exc

    @staticmethod
    def _get_rule_value_type(value: str | int):
        if isinstance(value, int):
            return SmartCrate.Fields.RULE_VALUE_INTEGER
        elif isinstance(value, str):
            return SmartCrate.Fields.RULE_VALUE_TEXT
        else:
            raise TypeError(f"Bad type: {type(value)} (value: {value})")

    def _stringify_entry(self, entry: CrateBase.EntryFull, indent: int = 0) -> str:
        field, fieldname, value = entry  # pylint: disable=unused-variable
        if isinstance(value, list):
            return self._stringify_entries(value, indent)

        ret_val = str(value)
        if field == CrateBase.Fields.RULE_FIELD:
            if not isinstance(value, int):
                raise DataTypeError(value, int, field)
            ret_val += f" ({self._get_rule_field_from_val(value).lower()})"
        elif field == CrateBase.Fields.RULE_COMPARISON:
            if not isinstance(value, str):
                raise DataTypeError(value, str, field)
            ret_val += f" ({self._get_rule_comparison_from_val(value)})"

        return ret_val

    class Rule(CrateBase.EntryListCls):
        def __init__(self, entries: "CrateBase.EntryList"):
            super().__init__(entries)

            # TODO: check and ensure types

            self.comparison = self.get_value(SmartCrate.Fields.RULE_COMPARISON)
            self.field = self.get_value(SmartCrate.Fields.RULE_FIELD)

            def try_to_get_value(field: str):
                try:
                    return self.get_value(field)
                except AttributeError:
                    return None

            # check "is None" rather than truthiness: 0 and "" are valid rule values
            self.value = cast(
                str | int | float,  # float for date or no?
                next(
                    (
                        value
                        for value in (
                            try_to_get_value(SmartCrate.Fields.RULE_VALUE_INTEGER),
                            try_to_get_value(SmartCrate.Fields.RULE_VALUE_TEXT),
                            try_to_get_value(SmartCrate.Fields.RULE_VALUE_DATE),
                        )
                        if value is not None
                    ),
                    None,
                ),
            )

        def set_value(  # pylint: disable=arguments-differ # pyright: ignore[reportIncompatibleMethodOverride]
            self, value: str | int
        ):
            field = SmartCrate._get_rule_value_type(value)  # pylint: disable=protected-access
            # a rule holds exactly one value field: when the value type changes (e.g. text -> integer),
            # replace the old value field in place instead of leaving both in the rule
            for other in (
                SmartCrate.Fields.RULE_VALUE_INTEGER,
                SmartCrate.Fields.RULE_VALUE_TEXT,
                SmartCrate.Fields.RULE_VALUE_DATE,
            ):
                if other == field or other not in self.fields:
                    continue
                if field in self.fields:
                    self.fields.remove(other)
                else:
                    self.fields[self.fields.index(other)] = field
                delattr(self, other)
            super().set_value(field, value)

        def set_field(self, value: "SmartCrate.RuleField"):
            super().set_value(SmartCrate.Fields.RULE_FIELD, value.value)

        def set_comparison(self, value: "SmartCrate.RuleComparison"):
            super().set_value(SmartCrate.Fields.RULE_COMPARISON, value.value)

    def set_rule(self, field: "SmartCrate.RuleField", comparison: "SmartCrate.RuleComparison", value: str | int):
        rule_field_id = field.value
        rule_exists: bool = False
        new_entries: SmartCrate.EntryList = []
        for f, v in self.entries:  # pylint: disable=access-member-before-definition
            if f == CrateBase.Fields.SMARTCRATE_RULE:
                if not isinstance(v, list):
                    raise DataTypeError(v, list, f)
                rule = SmartCrate.Rule(v)
                if rule.field == rule_field_id:
                    rule.set_value(value)
                    rule.set_comparison(comparison)
                    rule_exists = True
                v = rule.to_entries()
            new_entries.append((f, v))

        if not rule_exists:
            new_rule = SmartCrate.Rule(
                [
                    (SmartCrate.Fields.RULE_COMPARISON.value, comparison.value),
                    (SmartCrate.Fields.RULE_FIELD.value, rule_field_id),
                    (SmartCrate._get_rule_value_type(value).value, value),
                ]
            )
            new_entries.append((CrateBase.Fields.SMARTCRATE_RULE.value, new_rule.to_entries()))

        self.entries = new_entries  # pylint: disable=attribute-defined-outside-init
        self._dump()

    def delete_rule(self, field: "SmartCrate.RuleField"):
        rule_field_id = field.value
        new_entries: SmartCrate.EntryList = []
        for f, v in self.entries:  # pylint: disable=access-member-before-definition
            if f == CrateBase.Fields.SMARTCRATE_RULE:
                if not isinstance(v, list):
                    raise DataTypeError(v, list, f)
                rule = SmartCrate.Rule(v)
                if rule.field == rule_field_id:
                    continue
            new_entries.append((f, v))

        self.entries = new_entries  # pylint: disable=attribute-defined-outside-init
        self._dump()

    def find_missing(self):
        raise Exception("cannot be done on smart crate")


def main():
    import argparse

    @dataclass
    class Args:
        file_or_dir: str | None
        all: bool
        list_tracks: bool
        filenames_only: bool
        set_rules: list[str] | None

    parser = argparse.ArgumentParser()
    parser.add_argument("file_or_dir", nargs="?", help="Set the crate file, or a directory to do all files in it")
    parser.add_argument("--all", action="store_true", help="Perform actions on all crates.")
    parser.add_argument("-l", "--list_tracks", action="store_true", help="Only list tracks")
    parser.add_argument("-f", "--filenames_only", action="store_true", help="Only list track filenames")
    parser.add_argument(
        "--set_rules",
        nargs=argparse.REMAINDER,
        help="Set rules for all crates using key-value pairs like --grouping str_contains NEW --title str_does_not_contain NEW_TITLE\nCan also do --key DELETE",
    )
    args = Args(**vars(parser.parse_args()))

    if args.all:
        args.file_or_dir = SmartCrate.DIR_PATH

    if not args.file_or_dir:
        print(f"must pass a file or dir, or --all!\nfiles in {SmartCrate.DIR_PATH}:")
        print("\n".join(SmartCrate.get_crate_files()))
        sys.exit()

    set_rules = parse_cli_keys_and_values(args.set_rules) if args.set_rules else {}

    for crate_path in SmartCrate.get_crate_files(args.file_or_dir):
        crate = SmartCrate(crate_path)

        if args.set_rules:
            for key, value in set_rules.items():
                field = SmartCrate._get_rule_field_from_key(key)  # pylint: disable=protected-access
                if not value:
                    raise ValueError(f"no value given for --{key}, must specify a comparison and a value, or DELETE")
                if str(value[0]).upper() == "DELETE":
                    crate.delete_rule(field)
                else:
                    assert len(value) == 2, "must specify 2 values: a comparison and a value"
                    comparison = SmartCrate._get_rule_comparison_from_key(  # pylint: disable=protected-access
                        str(value[0])
                    )
                    rule_value: str | int = value[1]
                    if comparison in (SmartCrate.RuleComparison.INT_IS_GE, SmartCrate.RuleComparison.INT_IS_LE):
                        # integer comparisons must be stored in the integer value field, not as text
                        rule_value = int(rule_value)
                    crate.set_rule(field, comparison, rule_value)
            crate.save()
            continue

        if args.list_tracks or args.filenames_only:
            crate.print_track_paths(filenames_only=args.filenames_only)
        else:
            print(crate)


if __name__ == "__main__":
    main()
