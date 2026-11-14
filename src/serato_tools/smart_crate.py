"""Serato smart crate files (`.scrate`), and the `serato_smartcrate` CLI for listing their tracks and setting rules."""

import os
import sys
from dataclasses import dataclass
from enum import IntEnum, StrEnum, unique
from typing import cast

from serato_tools.utils import SERATO_DIR
from serato_tools.utils.bin_file_base import DataTypeError
from serato_tools.utils.crate_base import CrateBase


class SmartCrate(CrateBase):
    """A Serato smart crate file (`.scrate`): its rules, and the paths of the tracks they matched when last saved."""

    TESTED_VERSIONS = frozenset({"1.0/Serato ScratchLive Smart Crate"})
    EXTENSION = ".scrate"
    DIR = "SmartCrates"
    DIR_PATH = os.path.join(SERATO_DIR, DIR)

    @unique
    class RuleFields(StrEnum):
        """The fields only a smart crate holds, which extend the common `Fields` of the other bin files."""

        SMARTCRATE_RULE = "rurt"
        SMARTCRATE_LIVE_UPDATE = "rlut"
        SMARTCRATE_MATCH_ALL = "rart"
        # the on/off value inside SMARTCRATE_MATCH_ALL and SMARTCRATE_LIVE_UPDATE
        SETTING_VALUE = "brut"
        RULE_VALUE_TEXT = "trpt"
        RULE_VALUE_DATE = "trtt"
        RULE_VALUE_INTEGER = "urpt"
        RULE_COMPARISON = "trft"
        RULE_FIELD = "urkt"

    FIELD_ENUMS = (CrateBase.Fields, RuleFields)

    # the fields a rule can hold its value in, one per value type; a rule has exactly one of them
    RULE_VALUE_FIELDS = frozenset(
        (
            RuleFields.RULE_VALUE_INTEGER,
            RuleFields.RULE_VALUE_TEXT,
            RuleFields.RULE_VALUE_DATE,
        )
    )

    # each comparison names its value's type in its suffix (cond_is_str, cond_bef_time, cond_greq_uint)
    _RULE_VALUE_FIELD_BY_COMPARISON_SUFFIX = {
        "str": RuleFields.RULE_VALUE_TEXT,
        "time": RuleFields.RULE_VALUE_DATE,
        "uint": RuleFields.RULE_VALUE_INTEGER,
    }

    @unique
    class RuleField(IntEnum):
        """The track field a rule tests, such as artist or BPM, as the number Serato stores in `RULE_FIELD`."""

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

    @unique
    class RuleComparison(StrEnum):
        """How a rule compares its value with the track's; the suffix gives the type of value it compares."""

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
        (RuleFields.SMARTCRATE_MATCH_ALL, [(RuleFields.SETTING_VALUE, False)]),
        (RuleFields.SMARTCRATE_LIVE_UPDATE, [(RuleFields.SETTING_VALUE, False)]),
        *CrateBase.DEFAULT_VIEW_ENTRIES,
    ]

    @staticmethod
    def _get_rule_value_field(comparison: str) -> "SmartCrate.RuleFields":
        """The field a rule stores its value in.

        Serato picks it by the comparison's type (the cond_*_str / cond_*_time / cond_*_uint suffixes),
        not by the value's own type: an artist rule set to 100 is stored as the text "100".
        """
        suffix = SmartCrate.RuleComparison(comparison).value.rsplit("_", 1)[-1]
        return SmartCrate._RULE_VALUE_FIELD_BY_COMPARISON_SUFFIX[suffix]

    @staticmethod
    def _coerce_rule_value(comparison: str, value: str | int) -> str | int:
        """The value converted to the type of the field the comparison stores it in."""
        if SmartCrate._get_rule_value_field(comparison) == SmartCrate.RuleFields.RULE_VALUE_INTEGER:
            try:
                return int(value)
            except ValueError:
                raise ValueError(f'comparison "{comparison}" requires an integer value, got "{value}"') from None
        return str(value)

    def _stringify_entry(self, entry: CrateBase.EntryFull, indent: int = 0) -> str:
        field, _fieldname, value = entry
        if isinstance(value, list):
            return self._stringify_entries(value, indent)

        ret_val = str(value)
        if field == SmartCrate.RuleFields.RULE_FIELD:
            if not isinstance(value, int):
                raise DataTypeError(value, int, field)
            ret_val += f" ({SmartCrate.RuleField(value).name.lower()})"
        elif field == SmartCrate.RuleFields.RULE_COMPARISON:
            if not isinstance(value, str):
                raise DataTypeError(value, str, field)
            ret_val += f" ({SmartCrate.RuleComparison(value).name})"

        return ret_val

    class Rule(CrateBase.EntryListCls):
        """One of a smart crate's rules: the track field it tests (`field`), the `comparison`, and the `value`."""

        def __init__(self, entries: "CrateBase.EntryList"):
            super().__init__(entries)

            # TODO: check and ensure types

            self.comparison = self.get_value(SmartCrate.RuleFields.RULE_COMPARISON)
            self.field = self.get_value(SmartCrate.RuleFields.RULE_FIELD)

            value_field = next((field for field in SmartCrate.RULE_VALUE_FIELDS if field in self.fields), None)
            self.value = cast(
                str | int | float,  # float for date or no?
                self.get_value(value_field) if value_field is not None else None,
            )

        def set_value(  # pylint: disable=arguments-differ # pyright: ignore[reportIncompatibleMethodOverride]
            self, value: str | int
        ):
            """Sets the rule's value, converted to the type its comparison stores, in the field that type goes in."""
            if not isinstance(self.comparison, str):
                raise DataTypeError(self.comparison, str, SmartCrate.RuleFields.RULE_COMPARISON)
            # pylint: disable=protected-access
            field = SmartCrate._get_rule_value_field(self.comparison)
            value = SmartCrate._coerce_rule_value(self.comparison, value)
            # when the comparison's type differs from the old value's (e.g. text -> integer), replace
            # the old value field in place instead of leaving both in the rule
            for other in SmartCrate.RULE_VALUE_FIELDS - {field}:
                if other not in self.fields:
                    continue
                if field in self.fields:
                    self.fields.remove(other)
                else:
                    self.fields[self.fields.index(other)] = field
                delattr(self, other)
            super().set_value(field, value)
            self.value = value

        def set_field(self, value: "SmartCrate.RuleField"):
            super().set_value(SmartCrate.RuleFields.RULE_FIELD, value.value)
            self.field = value.value

        def set_comparison(self, value: "SmartCrate.RuleComparison"):
            super().set_value(SmartCrate.RuleFields.RULE_COMPARISON, value.value)
            self.comparison = value.value

    def set_rule(self, field: "SmartCrate.RuleField", comparison: "SmartCrate.RuleComparison", value: str | int):
        """Sets the rule on `field` to `comparison` and `value`, adding the rule if the crate has none on `field`.

        `value` is converted to the type `comparison` compares, e.g. `100` to `"100"` for a text comparison; raises
        ValueError if a comparison of numbers is given text that isn't one.
        """
        updated_rules: list[tuple[int, SmartCrate.EntryList]] = []
        for i, rule_entries in self._entry_lists(SmartCrate.RuleFields.SMARTCRATE_RULE):
            rule = SmartCrate.Rule(rule_entries)
            if rule.field == field.value:
                # the comparison first: it decides which value field set_value stores into
                rule.set_comparison(comparison)
                rule.set_value(value)
                updated_rules.append((i, rule.to_entries()))
        # replaced only once every rule has been read, so one that raises leaves the crate unchanged
        for i, rule_entries in updated_rules:
            self.entries[i] = (SmartCrate.RuleFields.SMARTCRATE_RULE.value, rule_entries)

        if not updated_rules:
            new_rule = SmartCrate.Rule(
                [
                    (SmartCrate.RuleFields.RULE_COMPARISON.value, comparison.value),
                    (SmartCrate.RuleFields.RULE_FIELD.value, field.value),
                ]
            )
            new_rule.set_value(value)
            self.entries.append((SmartCrate.RuleFields.SMARTCRATE_RULE.value, new_rule.to_entries()))

    def delete_rule(self, field: "SmartCrate.RuleField") -> bool:
        """Removes every rule on `field`, and returns whether there was one to remove."""
        return self._filter_entry_lists(
            SmartCrate.RuleFields.SMARTCRATE_RULE,
            lambda rule_entries: SmartCrate.Rule(rule_entries).field != field.value,
        )

    def find_missing(self):
        """Always raises, since a smart crate's tracks come from its rules."""
        raise Exception("cannot be done on smart crate")


def main():
    """The `serato_smartcrate` CLI: prints smart crates, lists their tracks, or sets or deletes their rules."""
    import argparse

    @dataclass
    class Args:
        file_or_dir: str | None
        all: bool
        list_tracks: bool
        filenames_only: bool
        # each rule option given, in the order given: its field, and the arguments after it
        rule_args: list[tuple[SmartCrate.RuleField, list[str]]]

    class AppendRule(argparse.Action):
        """Adds the option's field, its `const`, and its arguments to `rule_args`."""

        def __call__(self, parser, namespace, values, option_string=None):
            namespace.rule_args.append((self.const, values))

    comparisons = ", ".join(comparison.name.lower() for comparison in SmartCrate.RuleComparison)
    option_by_field = {field: f"--{field.name.lower()}" for field in SmartCrate.RuleField}

    parser = argparse.ArgumentParser()
    parser.add_argument("file_or_dir", nargs="?", help="Set the crate file, or a directory to do all files in it")
    parser.add_argument("--all", action="store_true", help="Perform actions on all crates.")
    parser.add_argument("-l", "--list_tracks", action="store_true", help="Only list tracks")
    parser.add_argument("-f", "--filenames_only", action="store_true", help="Only list track filenames")
    rule_options = parser.add_argument_group(
        "rules",
        "Set a rule on every crate given with --FIELD COMPARISON VALUE, such as --grouping str_is UNTAGGED, or delete "
        f"it with --FIELD DELETE. COMPARISON is one of: {comparisons}",
    )
    # one option per rule field, so argparse lists the fields in --help and rejects one that isn't a field; they all
    # append to one list, so the rules are set in the order given, as the crate then lists them
    for field, option in option_by_field.items():
        rule_options.add_argument(
            option,
            nargs="+",
            metavar="ARG",
            dest="rule_args",
            action=AppendRule,
            const=field,
            help=f"COMPARISON VALUE for the {field.name.lower()} rule, or DELETE",
        )
    parser.set_defaults(rule_args=[])
    # argparse matches options by case, so lowercase a rule field option given in another case (--GROUPING); only
    # exact field names are touched, so a value is never changed
    option_by_upper = {option.upper(): option for option in option_by_field.values()}
    args = Args(**vars(parser.parse_args([option_by_upper.get(arg.upper(), arg) for arg in sys.argv[1:]])))

    # each rule's field, and its comparison and value, or None to delete it; checked before any crate is changed
    rules: list[tuple[SmartCrate.RuleField, tuple[SmartCrate.RuleComparison, str] | None]] = []
    for field, rule_arg in args.rule_args:
        option = option_by_field[field]
        if len(rule_arg) == 1 and rule_arg[0].upper() == "DELETE":
            rules.append((field, None))
        elif len(rule_arg) == 2:
            comparison_name, value = rule_arg
            try:
                comparison = SmartCrate.RuleComparison[comparison_name.upper()]
            except KeyError:
                parser.error(f"{option}: unknown comparison {comparison_name}, must be one of: {comparisons}")
            try:
                SmartCrate._coerce_rule_value(comparison, value)  # pylint: disable=protected-access
            except ValueError:
                parser.error(f"{option}: {comparison_name} compares whole numbers, got {value}")
            rules.append((field, (comparison, value)))
        else:
            parser.error(f"{option} takes a comparison and a value, or DELETE")

    if args.all:
        args.file_or_dir = SmartCrate.DIR_PATH

    if not args.file_or_dir:
        print(f"must pass a file or dir, or --all!\nfiles in {SmartCrate.DIR_PATH}:")
        print("\n".join(SmartCrate.get_crate_files()))
        sys.exit()

    for crate_path in SmartCrate.get_crate_files(args.file_or_dir):
        crate = SmartCrate(crate_path)

        if rules:
            for field, rule in rules:
                if rule is None:
                    crate.delete_rule(field)
                else:
                    # set_rule stores the value in the field the comparison expects, parsing it as needed
                    crate.set_rule(field, *rule)
            # skipped if the rules are as they were, as when a rule is set to the value it already has
            crate.save()
        elif args.list_tracks or args.filenames_only:
            crate.print_track_paths(filenames_only=args.filenames_only)
        else:
            print(crate)


if __name__ == "__main__":
    main()
