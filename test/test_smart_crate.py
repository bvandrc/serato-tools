# pylint: disable=protected-access
import unittest
import os

from src.serato_tools.smart_crate import SmartCrate

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

        self.assertEqual(crate.raw_data, file_data, "raw_data read")
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

    def test_rule_value_zero(self):
        rule = SmartCrate.Rule(
            [
                (SmartCrate.Fields.RULE_COMPARISON.value, SmartCrate.RuleComparison.INT_IS_GE.value),
                (SmartCrate.Fields.RULE_FIELD.value, SmartCrate.RuleField.PLAYS.value),
                (SmartCrate.Fields.RULE_VALUE_INTEGER.value, 0),
            ]
        )
        self.assertEqual(rule.value, 0, "an integer rule value of 0 must not read as None")

    def test_rule_set_value_replaces_value_field_on_type_change(self):
        rule = SmartCrate.Rule(
            [
                (SmartCrate.Fields.RULE_COMPARISON.value, SmartCrate.RuleComparison.STR_IS.value),
                (SmartCrate.Fields.RULE_FIELD.value, SmartCrate.RuleField.ARTIST.value),
                (SmartCrate.Fields.RULE_VALUE_TEXT.value, "some artist"),
            ]
        )
        rule.set_value(100)
        self.assertEqual(
            rule.to_entries(),
            [
                (SmartCrate.Fields.RULE_COMPARISON.value, SmartCrate.RuleComparison.STR_IS.value),
                (SmartCrate.Fields.RULE_FIELD.value, SmartCrate.RuleField.ARTIST.value),
                (SmartCrate.Fields.RULE_VALUE_INTEGER, 100),
            ],
            "old text value field must be replaced in place, not kept alongside the integer field",
        )
