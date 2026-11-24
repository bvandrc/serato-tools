"""Serato smart crate files (`.scrate`), and the `serato_smartcrate` CLI for listing their tracks and setting rules."""

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum, unique
from typing import TYPE_CHECKING, ClassVar, cast, override

from serato_tools.utils import SERATO_DIR
from serato_tools.utils.crate_base import CrateBase

if TYPE_CHECKING:
    from serato_tools.crate import Crate


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
    _RULE_VALUE_FIELD_BY_COMPARISON_SUFFIX: ClassVar[Mapping[str, RuleFields]] = {
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

    DEFAULT_ENTRIES: ClassVar[CrateBase.EntryList] = [
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

        # one this package doesn't know, such as one a newer Serato wrote, is printed as it is rather than refused
        if field == SmartCrate.RuleFields.RULE_FIELD:
            name = SmartCrate.RuleField(value).name.lower() if value in SmartCrate.RuleField else "unknown"
        elif field == SmartCrate.RuleFields.RULE_COMPARISON:
            name = SmartCrate.RuleComparison(value).name if value in SmartCrate.RuleComparison else "unknown"
        else:
            return str(value)
        return f"{value} ({name})"

    class Rule(CrateBase.EntryListCls):
        """One of a smart crate's rules: the track field it tests (`field`), the `comparison`, and the `value`."""

        def __init__(self, entries: "SmartCrate.EntryList"):
            """Reads the entries, raising ValueError for a missing or unknown comparison or track field."""
            super().__init__(entries)
            comparison, field = SmartCrate.RuleFields.RULE_COMPARISON, SmartCrate.RuleFields.RULE_FIELD
            for required in (comparison, field):
                if required not in self.fields:
                    raise ValueError(f"rule has no {required.name.lower()} ({required.value})")
            if self.comparison not in SmartCrate.RuleComparison:
                raise ValueError(
                    f'rule has an unknown {comparison.name.lower()} "{self.comparison}" ({comparison.value})'
                )
            if self.field not in SmartCrate.RuleField:
                raise ValueError(f'rule has an unknown {field.name.lower()} "{self.field}" ({field.value})')

        @override
        def remove_field(self, field: str) -> bool:
            """Removes an optional field, raising ValueError for the comparison or track field."""
            if field in (SmartCrate.RuleFields.RULE_COMPARISON, SmartCrate.RuleFields.RULE_FIELD):
                raise ValueError(f"can't remove a rule's required field ({field})")
            return super().remove_field(field)

        @property
        def comparison(self) -> str:
            """The rule's comparison, as a `SmartCrate.RuleComparison` value."""
            return self.get_value(SmartCrate.RuleFields.RULE_COMPARISON, str)

        @property
        def field(self) -> int:
            """The track field the rule tests, as a `SmartCrate.RuleField` value."""
            return self.get_value(SmartCrate.RuleFields.RULE_FIELD, int)

        @property
        def value(self) -> str | int | None:
            """The value the rule compares with, or None if it has none."""
            value_field = next((field for field in SmartCrate.RULE_VALUE_FIELDS if field in self.fields), None)
            return cast(str | int, self.get_value(value_field)) if value_field is not None else None

        def set_value(  # pyright: ignore[reportIncompatibleMethodOverride]
            self, value: str | int
        ):
            """Sets the rule's value, converted to the type its comparison stores, in the field that type goes in."""
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

        def set_field(self, value: "SmartCrate.RuleField"):
            super().set_value(SmartCrate.RuleFields.RULE_FIELD, value.value)

        def set_comparison(self, value: "SmartCrate.RuleComparison"):
            super().set_value(SmartCrate.RuleFields.RULE_COMPARISON, value.value)

    @staticmethod
    def _get_rule_field(rule_entries: "SmartCrate.EntryList") -> int | None:
        """The track field a rule tests, or None if it has none, read without reading the rest of the rule."""
        field = SmartCrate.RuleFields.RULE_FIELD
        return next((cast(int, value) for name, value in rule_entries if name == field), None)

    def set_rule(self, field: "SmartCrate.RuleField", comparison: "SmartCrate.RuleComparison", value: str | int):
        """Sets the rule on `field` to `comparison` and `value`, adding the rule if the crate has none on `field`.

        `value` is converted to the type `comparison` compares, e.g. `100` to `"100"` for a text comparison; raises
        ValueError, changing nothing, if a comparison of numbers is given text that isn't one. Rules on other fields are
        kept as they are, even ones this package can't read, such as one a newer Serato wrote, and a rule on `field`
        whose comparison is missing or unknown is replaced.
        """
        comparison_field = SmartCrate.RuleFields.RULE_COMPARISON.value
        updated_rules: list[tuple[int, SmartCrate.EntryList]] = []
        for i, rule_entries in self._entry_lists(SmartCrate.RuleFields.SMARTCRATE_RULE):
            if SmartCrate._get_rule_field(rule_entries) != field.value:
                continue
            # the new comparison goes in before the rule is read, so an unknown or missing one is replaced rather than
            # refused, and before set_value, since it decides which value field that stores into
            if any(name == comparison_field for name, _ in rule_entries):
                rule_entries = [
                    (name, comparison.value if name == comparison_field else rule_value)
                    for name, rule_value in rule_entries
                ]
            else:
                rule_entries = [(comparison_field, comparison.value), *rule_entries]
            rule = SmartCrate.Rule(rule_entries)
            rule.set_value(value)
            updated_rules.append((i, rule.to_entries()))
        # replaced only once every rule has been read, so one that raises leaves the crate unchanged
        for i, rule_entries in updated_rules:
            self._entries[i] = (SmartCrate.RuleFields.SMARTCRATE_RULE.value, rule_entries)

        if not updated_rules:
            new_rule = SmartCrate.Rule(
                [
                    (comparison_field, comparison.value),
                    (SmartCrate.RuleFields.RULE_FIELD.value, field.value),
                ]
            )
            new_rule.set_value(value)
            self._entries.append((SmartCrate.RuleFields.SMARTCRATE_RULE.value, new_rule.to_entries()))

    def delete_rule(self, field: "SmartCrate.RuleField") -> bool:
        """Removes every rule on `field`, and returns whether there was one to remove.

        Rules on other fields are kept as they are, even ones this package can't read, and a rule on `field` is removed
        whatever its comparison.
        """
        return self._filter_entry_lists(
            SmartCrate.RuleFields.SMARTCRATE_RULE,
            lambda rule_entries: SmartCrate._get_rule_field(rule_entries) != field.value,
        )

    def to_regular_crate(self, file: str) -> "Crate":
        """A regular crate for `file`, holding this smart crate's tracks and view settings (its sort and columns), but
        not its rules.

        Serato can't use a smart crate on a drive, so USB export writes each one as this. Call its `save()` to write
        the file. Raises FileExistsError if `file` already exists, as `Crate.new` does.
        """
        # imported here, since only this method needs regular crates
        from serato_tools.crate import Crate  # noqa: PLC0415

        crate = Crate.new(file)
        rule_fields = {field.value for field in SmartCrate.RuleFields}
        crate._entries = [  # noqa: SLF001
            # a regular crate's version, then this smart crate's entries but its own version and its rules
            *(entry for entry in crate._entries if entry[0] == Crate.Fields.VERSION),  # noqa: SLF001
            *(entry for entry in self._entries if entry[0] != Crate.Fields.VERSION and entry[0] not in rule_fields),
        ]
        return crate

    def find_missing(self):
        """Always raises, since a smart crate's tracks come from its rules."""
        raise TypeError("a smart crate's tracks come from its rules, so it can't have missing tracks to find")


def main():
    """The `serato_smartcrate` CLI: prints smart crates, lists their tracks, or sets or deletes their rules."""
    # ruff: disable[PLC0415, T201]
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

        @override
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
                SmartCrate._coerce_rule_value(comparison, value)  # noqa: SLF001
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
    # ruff: enable[PLC0415, T201]


if __name__ == "__main__":
    main()
