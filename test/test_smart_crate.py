# pylint: disable=protected-access
import copy
import os
import unittest
from typing import cast
from unittest import mock

from serato_tools.smart_crate import SmartCrate, main
from serato_tools.utils.bin_file_base import DataTypeError

from test.helpers import TEST_SMART_CRATE, cli_args, read_bytes, read_text, temp_copy

SMART_CRATE = os.path.abspath(TEST_SMART_CRATE)
expected = read_text("test/data/smart_crate.txt")


def rule_entries(
    comparison: SmartCrate.RuleComparison,
    field: SmartCrate.RuleField,
    value_field: SmartCrate.RuleFields,
    value: str | int,
) -> SmartCrate.EntryList:
    """A rule's entries, as Serato writes them."""
    return [
        (SmartCrate.RuleFields.RULE_COMPARISON.value, comparison.value),
        (SmartCrate.RuleFields.RULE_FIELD.value, field.value),
        (value_field.value, value),
    ]


def make_rule(
    comparison: SmartCrate.RuleComparison,
    field: SmartCrate.RuleField,
    value_field: SmartCrate.RuleFields,
    value: str | int,
) -> SmartCrate.Rule:
    return SmartCrate.Rule(rule_entries(comparison, field, value_field, value))


class TestCase(unittest.TestCase):
    def check_lines(self, given: str, exp: str):
        """Asserts the two texts are equal, ignoring whitespace at the start and end of each line."""
        given = "\n".join([l.strip() for l in given.splitlines()])
        exp = "\n".join([l.strip() for l in exp.splitlines()])
        self.maxDiff = None
        self.assertMultiLineEqual(given, exp)

    def test_parse_and_add_rule(self):
        crate = SmartCrate(SMART_CRATE)

        self.assertEqual(crate.to_bytes(), read_bytes(SMART_CRATE), "to_bytes")
        self.check_lines(crate.__str__(), expected)

        crate.set_rule(SmartCrate.RuleField.ALBUM, SmartCrate.RuleComparison.STR_IS_NOT, "albo")
        self.check_lines(
            crate.__str__(),
            expected
            + "\nrurt (SmartCrate Rule): [ trft (Rule Comparison): cond_isn_str (STR_IS_NOT) ], [ urkt (Rule Field): 8 (album) ], [ trpt (Rule Value Text): albo ]",
        )

    def test_set_rule_on_malformed_crate_changes_nothing(self):
        crate = SmartCrate(SMART_CRATE)
        # a rule entry after the GROUPING rule that holds text rather than an entry list
        crate.entries.append((SmartCrate.RuleFields.SMARTCRATE_RULE.value, "not a rule"))
        entries_before = copy.deepcopy(crate.entries)

        with self.assertRaises(DataTypeError):
            crate.set_rule(SmartCrate.RuleField.GROUPING, SmartCrate.RuleComparison.STR_IS, "changed")
        self.assertEqual(crate.entries, entries_before, "a rule before the malformed one must not be replaced")

    def test_delete_rule_returns_whether_removed(self):
        crate = SmartCrate(SMART_CRATE)

        self.assertFalse(crate.delete_rule(SmartCrate.RuleField.ALBUM), "the crate has no album rule")
        self.assertFalse(crate.has_changed)
        self.assertTrue(crate.delete_rule(SmartCrate.RuleField.GROUPING))
        self.assertFalse(crate.delete_rule(SmartCrate.RuleField.GROUPING), "the grouping rule was already removed")

    def test_rule_falsy_value_reads_back(self):
        # one falsy value per value field; the dict also pins that every field in the constant is covered
        falsy_values = {
            SmartCrate.RuleFields.RULE_VALUE_INTEGER: 0,
            SmartCrate.RuleFields.RULE_VALUE_TEXT: "",
            SmartCrate.RuleFields.RULE_VALUE_DATE: "",
        }
        self.assertEqual(set(falsy_values), set(SmartCrate.RULE_VALUE_FIELDS))

        for value_field in SmartCrate.RULE_VALUE_FIELDS:
            with self.subTest(value_field=value_field):
                rule = make_rule(
                    SmartCrate.RuleComparison.INT_IS_GE,
                    SmartCrate.RuleField.PLAYS,
                    value_field,
                    falsy_values[value_field],
                )
                self.assertEqual(rule.value, falsy_values[value_field], "a falsy rule value must not read as no value")

    def test_every_comparison_maps_to_a_value_field(self):
        # the suffix lookup must cover every comparison, so a comparison with an unknown suffix
        # fails here rather than at set_rule time
        for comparison in SmartCrate.RuleComparison:
            with self.subTest(comparison=comparison):
                self.assertIn(SmartCrate._get_rule_value_field(comparison.value), SmartCrate.RULE_VALUE_FIELDS)

    def test_rule_value_field_follows_comparison_not_value_type(self):
        # confirmed against Serato itself: an artist rule set to 100 is stored as the text "100",
        # so the comparison, not the passed value's type, decides the value field
        rule = make_rule(
            SmartCrate.RuleComparison.STR_IS,
            SmartCrate.RuleField.ARTIST,
            SmartCrate.RuleFields.RULE_VALUE_TEXT,
            "some artist",
        )
        rule.set_value(100)
        self.assertEqual(
            rule.to_entries(),
            rule_entries(
                SmartCrate.RuleComparison.STR_IS,
                SmartCrate.RuleField.ARTIST,
                SmartCrate.RuleFields.RULE_VALUE_TEXT,
                "100",
            ),
            "a string comparison's value must be stored as text, whatever type was passed",
        )

    def test_rule_set_value_replaces_value_field_on_comparison_type_change(self):
        rule = make_rule(
            SmartCrate.RuleComparison.STR_IS, SmartCrate.RuleField.PLAYS, SmartCrate.RuleFields.RULE_VALUE_TEXT, "100"
        )
        rule.set_comparison(SmartCrate.RuleComparison.INT_IS_GE)
        rule.set_value("100")
        self.assertEqual(
            rule.to_entries(),
            rule_entries(
                SmartCrate.RuleComparison.INT_IS_GE,
                SmartCrate.RuleField.PLAYS,
                SmartCrate.RuleFields.RULE_VALUE_INTEGER,
                100,
            ),
            "old text value field must be replaced in place, not kept alongside the integer field",
        )

    def test_rule_set_value_rejects_non_integer_for_integer_comparison(self):
        rule = make_rule(
            SmartCrate.RuleComparison.INT_IS_GE, SmartCrate.RuleField.PLAYS, SmartCrate.RuleFields.RULE_VALUE_INTEGER, 5
        )
        with self.assertRaisesRegex(ValueError, "requires an integer value"):
            rule.set_value("abc")


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.path = temp_copy(self, TEST_SMART_CRATE)

    def run_cli(self, *args: str) -> str:
        """Runs `serato_smartcrate` on the test smart crate's copy with `args`, and returns what it printed to stdout."""
        with cli_args("serato_smartcrate", self.path, *args) as stdout:
            main()
        return stdout.getvalue()

    def saved_rules(self) -> dict[SmartCrate.RuleField, tuple[str, str | int | float]]:
        """Each rule in the saved crate, by field, as its comparison and value."""
        crate = SmartCrate(self.path)
        rules = [
            SmartCrate.Rule(v)
            for f, v in crate.entries
            if f == SmartCrate.RuleFields.SMARTCRATE_RULE and isinstance(v, list)
        ]
        return {SmartCrate.RuleField(cast(int, r.field)): (str(r.comparison), r.value) for r in rules}

    def test_sets_and_deletes_rules(self):
        self.assertIn(SmartCrate.RuleField.YEAR, self.saved_rules())
        self.run_cli("--GROUPING", "str_is", "UNTAGGED", "--Plays", "INT_IS_GE", "3", "--year", "delete")
        rules = self.saved_rules()
        self.assertEqual(rules[SmartCrate.RuleField.GROUPING], ("cond_is_str", "UNTAGGED"), "field option in any case")
        self.assertEqual(
            rules[SmartCrate.RuleField.PLAYS], ("cond_greq_uint", 3), "field option and comparison in any case"
        )
        self.assertNotIn(SmartCrate.RuleField.YEAR, rules, "DELETE in any case")

    def test_new_rules_are_added_in_the_order_given(self):
        self.run_cli("--genre", "str_is", "G", "--album", "str_is", "A")
        self.assertEqual(list(self.saved_rules())[-2:], [SmartCrate.RuleField.GENRE, SmartCrate.RuleField.ALBUM])

    def test_rules_set_to_their_values_dont_rewrite_the_crate(self):
        with mock.patch("serato_tools.utils.bin_file_base.open", wraps=open, create=True) as opened:
            self.run_cli("--year", "str_is", "2000", "--label", "str_contains", "YT")
        self.assertEqual([c for c in opened.call_args_list if "wb" in c.args], [], "nothing written")

    def test_without_rule_options_prints_the_crate_and_changes_nothing(self):
        before = read_bytes(self.path)
        self.assertIn("SmartCrate Rule", self.run_cli())
        self.assertEqual(read_bytes(self.path), before)

    def test_bad_rule_options_change_nothing(self):
        before = read_bytes(self.path)
        for args in (
            ["--nope", "str_is", "X"],
            ["--grouping", "nope", "X"],
            ["--grouping", "str_is"],
            ["--grouping", "str_is", "X", "Y"],
            ["--plays", "int_is_ge", "abc"],
        ):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                self.run_cli(*args)
        self.assertEqual(read_bytes(self.path), before)


if __name__ == "__main__":
    unittest.main()
