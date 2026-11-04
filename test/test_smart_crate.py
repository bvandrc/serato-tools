# pylint: disable=protected-access
import unittest
import os

from serato_tools.smart_crate import SmartCrate

with open("test/data/smart_crate.txt", "r", encoding="utf-8") as f:
    expected = f.read()


class TestCase(unittest.TestCase):
    def check_lines(self, given: str, exp: str):
        given = "\n".join([l.strip() for l in given.splitlines()])
        exp = "\n".join([l.strip() for l in exp.splitlines()])
        self.maxDiff = None
        self.assertMultiLineEqual(given, exp)

    def test_parse(self):
        file = os.path.abspath("test/data/TestSmartCrate.scrate")
        with open(file, mode="rb") as fp:
            file_data = fp.read()

        crate = SmartCrate(file)

        self.assertEqual(crate.to_bytes(), file_data, "to_bytes")
        self.check_lines(crate.__str__(), expected)

    def test_add_rule(self):
        file = os.path.abspath("test/data/TestSmartCrate.scrate")

        crate = SmartCrate(file)
        crate.set_rule(SmartCrate.RuleField.ALBUM, SmartCrate.RuleComparison.STR_IS_NOT, "albo")
        self.check_lines(
            crate.__str__(),
            expected
            + "\nrurt (SmartCrate Rule): [ trft (Rule Comparison): cond_isn_str (STR_IS_NOT) ], [ urkt (Rule Field): 8 (album) ], [ trpt (Rule Value Text): albo ]",
        )

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
                rule = SmartCrate.Rule(
                    [
                        (SmartCrate.RuleFields.RULE_COMPARISON.value, SmartCrate.RuleComparison.INT_IS_GE.value),
                        (SmartCrate.RuleFields.RULE_FIELD.value, SmartCrate.RuleField.PLAYS.value),
                        (value_field.value, falsy_values[value_field]),
                    ]
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
        rule = SmartCrate.Rule(
            [
                (SmartCrate.RuleFields.RULE_COMPARISON.value, SmartCrate.RuleComparison.STR_IS.value),
                (SmartCrate.RuleFields.RULE_FIELD.value, SmartCrate.RuleField.ARTIST.value),
                (SmartCrate.RuleFields.RULE_VALUE_TEXT.value, "some artist"),
            ]
        )
        rule.set_value(100)
        self.assertEqual(
            rule.to_entries(),
            [
                (SmartCrate.RuleFields.RULE_COMPARISON.value, SmartCrate.RuleComparison.STR_IS.value),
                (SmartCrate.RuleFields.RULE_FIELD.value, SmartCrate.RuleField.ARTIST.value),
                (SmartCrate.RuleFields.RULE_VALUE_TEXT.value, "100"),
            ],
            "a string comparison's value must be stored as text, whatever type was passed",
        )

    def test_rule_set_value_replaces_value_field_on_comparison_type_change(self):
        rule = SmartCrate.Rule(
            [
                (SmartCrate.RuleFields.RULE_COMPARISON.value, SmartCrate.RuleComparison.STR_IS.value),
                (SmartCrate.RuleFields.RULE_FIELD.value, SmartCrate.RuleField.PLAYS.value),
                (SmartCrate.RuleFields.RULE_VALUE_TEXT.value, "100"),
            ]
        )
        rule.set_comparison(SmartCrate.RuleComparison.INT_IS_GE)
        rule.set_value("100")
        self.assertEqual(
            rule.to_entries(),
            [
                (SmartCrate.RuleFields.RULE_COMPARISON.value, SmartCrate.RuleComparison.INT_IS_GE.value),
                (SmartCrate.RuleFields.RULE_FIELD.value, SmartCrate.RuleField.PLAYS.value),
                (SmartCrate.RuleFields.RULE_VALUE_INTEGER.value, 100),
            ],
            "old text value field must be replaced in place, not kept alongside the integer field",
        )

    def test_rule_set_value_rejects_non_integer_for_integer_comparison(self):
        rule = SmartCrate.Rule(
            [
                (SmartCrate.RuleFields.RULE_COMPARISON.value, SmartCrate.RuleComparison.INT_IS_GE.value),
                (SmartCrate.RuleFields.RULE_FIELD.value, SmartCrate.RuleField.PLAYS.value),
                (SmartCrate.RuleFields.RULE_VALUE_INTEGER.value, 5),
            ]
        )
        with self.assertRaisesRegex(ValueError, "requires an integer value"):
            rule.set_value("abc")
