# pylint: disable=protected-access
import os

import pytest

from serato_tools.crate import Crate
from serato_tools.smart_crate import SmartCrate, main

from test.helpers.bin_files import TEST_SMART_CRATE
from test.helpers.cli import cli_args
from test.helpers.files import copy_into, read_bytes, read_text

# the test smart crate parsed, as its __str__ prints it
TEST_SMART_CRATE_TXT_FILE = "test/data/smart_crate.txt"
Comparison = SmartCrate.RuleComparison
Field = SmartCrate.RuleField
ValueField = SmartCrate.RuleFields


def rule_entries(
    comparison: Comparison, field: Field, value_field: ValueField, value: str | int
) -> SmartCrate.EntryList:
    """A rule's entries, as Serato writes them."""
    return [
        (ValueField.RULE_COMPARISON.value, comparison.value),
        (ValueField.RULE_FIELD.value, field.value),
        (value_field.value, value),
    ]


def make_rule(comparison: Comparison, field: Field, value_field: ValueField, value: str | int) -> SmartCrate.Rule:
    return SmartCrate.Rule(rule_entries(comparison, field, value_field, value))


def test_parse():
    crate = SmartCrate(TEST_SMART_CRATE)
    assert crate.to_bytes() == read_bytes(TEST_SMART_CRATE), "round-trips byte-exact"
    assert crate.__str__() == read_text(TEST_SMART_CRATE_TXT_FILE)


def test_add_rule():
    crate = SmartCrate(TEST_SMART_CRATE)
    expected = read_text(TEST_SMART_CRATE_TXT_FILE)

    crate.set_rule(Field.ALBUM, Comparison.STR_IS_NOT, "albo")
    assert crate.__str__() == (
        expected
        + "\nrurt (SmartCrate Rule): [ trft (Rule Comparison): cond_isn_str (STR_IS_NOT) ], [ urkt (Rule Field): 8 (album) ], [ trpt (Rule Value Text): albo ]"
    )


def test_delete_rule_returns_whether_removed():
    crate = SmartCrate(TEST_SMART_CRATE)

    assert crate.delete_rule(Field.ALBUM) is False, "the crate has no album rule"
    assert not crate.has_changed
    assert crate.delete_rule(Field.GROUPING) is True
    assert crate.delete_rule(Field.GROUPING) is False, "the grouping rule was already removed"


# one falsy value per value field
FALSY_VALUES = {ValueField.RULE_VALUE_INTEGER: 0, ValueField.RULE_VALUE_TEXT: "", ValueField.RULE_VALUE_DATE: ""}


def test_falsy_values_cover_every_value_field():
    assert set(FALSY_VALUES) == set(SmartCrate.RULE_VALUE_FIELDS)


@pytest.mark.parametrize("value_field, value", FALSY_VALUES.items(), ids=lambda v: getattr(v, "name", repr(v)))
def test_rule_falsy_value_reads_back(value_field: ValueField, value: str | int):
    rule = make_rule(Comparison.INT_IS_GE, Field.PLAYS, value_field, value)
    assert rule.value == value, "a falsy rule value must not read as no value"


@pytest.mark.parametrize("comparison", Comparison, ids=lambda c: c.name)
def test_every_comparison_maps_to_a_value_field(comparison: Comparison):
    # the suffix lookup must cover every comparison, so a comparison with an unknown suffix
    # fails here rather than at set_rule time
    assert SmartCrate._get_rule_value_field(comparison.value) in SmartCrate.RULE_VALUE_FIELDS


def test_rule_value_field_follows_comparison_not_value_type():
    ARGS = (Comparison.STR_IS, Field.ARTIST, ValueField.RULE_VALUE_TEXT)
    # confirmed against Serato itself: an artist rule set to 100 is stored as the text "100",
    # so the comparison, not the passed value's type, decides the value field
    rule = make_rule(*ARGS, "some artist")
    rule.set_value(100)
    assert rule.to_entries() == rule_entries(*ARGS, "100")


def test_rule_set_value_replaces_value_field_on_comparison_type_change():
    rule = make_rule(Comparison.STR_IS, Field.PLAYS, ValueField.RULE_VALUE_TEXT, "100")
    rule.set_comparison(Comparison.INT_IS_GE)
    rule.set_value("100")
    # the old text value field replaced in place, not kept alongside the integer field
    assert rule.to_entries() == rule_entries(Comparison.INT_IS_GE, Field.PLAYS, ValueField.RULE_VALUE_INTEGER, 100)


def test_rule_set_value_rejects_non_integer_for_integer_comparison():
    rule = make_rule(Comparison.INT_IS_GE, Field.PLAYS, ValueField.RULE_VALUE_INTEGER, 5)
    with pytest.raises(ValueError, match="requires an integer value"):
        rule.set_value("abc")


def test_rule_properties_follow_its_entries():
    rule = make_rule(Comparison.INT_IS_GE, Field.PLAYS, ValueField.RULE_VALUE_INTEGER, 5)
    rule.set_comparison(Comparison.STR_CONTAINS)
    rule.set_field(Field.GENRE)
    rule.set_value("House")
    assert (rule.comparison, rule.field, rule.value) == (
        Comparison.STR_CONTAINS.value,
        Field.GENRE.value,
        "House",
    ), "set through its setters"

    rule.remove_field(ValueField.RULE_VALUE_TEXT)
    assert rule.value is None, "removed"


def test_find_missing_raises():
    # its tracks come from its rules
    with pytest.raises(TypeError):
        SmartCrate(TEST_SMART_CRATE).find_missing()


def test_to_regular_crate_keeps_the_tracks_sort_and_columns_but_not_the_rules(tmp_dir: str):
    smart_crate = SmartCrate(TEST_SMART_CRATE)
    view_fields = {Crate.Fields.SORTING.value, Crate.Fields.COLUMN.value}
    rule_fields = {field.value for field in ValueField}
    assert smart_crate.get_track_paths(), "the fixture has tracks"
    assert any(field in view_fields for field, _ in smart_crate._entries), "and a sort and columns"
    assert any(field in rule_fields for field, _ in smart_crate._entries), "and rules"
    file = os.path.join(tmp_dir, "Regular.crate")
    smart_crate.to_regular_crate(file).save()

    saved = Crate(file)
    assert saved._version == Crate.DEFAULT_ENTRIES[0][1], "a regular crate's version"
    assert saved.get_track_paths() == smart_crate.get_track_paths()
    assert saved._entries[1:] == [
        entry for entry in smart_crate._entries[1:] if entry[0] not in rule_fields
    ], "everything but the version and the rules, in order"


class TestCli:
    """The serato_smartcrate CLI, run on a copy of the test smart crate."""

    @pytest.fixture
    def path(self, tmp_dir: str) -> str:
        return copy_into(tmp_dir, TEST_SMART_CRATE)

    def run_cli(self, path: str, *args: str) -> str:
        """Runs `serato_smartcrate` on `path` with `args`, and returns what it printed to stdout."""
        with cli_args("serato_smartcrate", path, *args) as stdout:
            main()
        return stdout.getvalue()

    def saved_rules(self, path: str) -> dict[Field, tuple[str, str | int | None]]:
        """Each rule in the crate saved at `path`, by field, as its comparison and value."""
        rules = [
            SmartCrate.Rule(v)
            for f, v in SmartCrate(path)._entries
            if f == ValueField.SMARTCRATE_RULE and isinstance(v, list)
        ]
        return {Field(r.field): (r.comparison, r.value) for r in rules}

    def test_sets_and_deletes_rules(self, path: str):
        assert Field.YEAR in self.saved_rules(path)
        self.run_cli(path, "--GROUPING", "str_is", "UNTAGGED", "--Plays", "INT_IS_GE", "3", "--year", "delete")
        rules = self.saved_rules(path)
        assert rules[Field.GROUPING] == ("cond_is_str", "UNTAGGED"), "field option in any case"
        assert rules[Field.PLAYS] == ("cond_greq_uint", 3), "field option and comparison in any case"
        assert Field.YEAR not in rules, "DELETE in any case"

    def test_new_rules_are_added_in_the_order_given(self, path: str):
        self.run_cli(path, "--genre", "str_is", "G", "--album", "str_is", "A")
        assert list(self.saved_rules(path))[-2:] == [Field.GENRE, Field.ALBUM]

    def test_rules_set_to_their_values_dont_rewrite_the_crate(self, path: str, bin_file_writes: list[str]):
        self.run_cli(path, "--year", "str_is", "2000", "--label", "str_contains", "YT")
        assert bin_file_writes == []

    def test_without_rule_options_prints_the_crate_and_changes_nothing(self, path: str, bin_file_writes: list[str]):
        assert "SmartCrate Rule" in self.run_cli(path)
        assert bin_file_writes == []

    @pytest.mark.parametrize(
        "args",
        [
            ["--nope", "str_is", "X"],
            ["--grouping", "nope", "X"],
            ["--grouping", "str_is"],
            ["--grouping", "str_is", "X", "Y"],
            ["--plays", "int_is_ge", "abc"],
        ],
        ids=" ".join,
    )
    def test_bad_rule_options_change_nothing(self, path: str, bin_file_writes: list[str], args: list[str]):
        with pytest.raises(SystemExit):
            self.run_cli(path, *args)
        assert bin_file_writes == []
