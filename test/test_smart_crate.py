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
            SmartCrate.Fields.RULE_VALUE_INTEGER: 0,
            SmartCrate.Fields.RULE_VALUE_TEXT: "",
            SmartCrate.Fields.RULE_VALUE_DATE: "",
        }
        self.assertEqual(set(falsy_values), set(SmartCrate.RULE_VALUE_FIELDS))

        for value_field in SmartCrate.RULE_VALUE_FIELDS:
            with self.subTest(value_field=value_field):
                rule = SmartCrate.Rule(
                    [
                        (SmartCrate.Fields.RULE_COMPARISON.value, SmartCrate.RuleComparison.INT_IS_GE.value),
                        (SmartCrate.Fields.RULE_FIELD.value, SmartCrate.RuleField.PLAYS.value),
                        (value_field.value, falsy_values[value_field]),
                    ]
                )
                self.assertEqual(rule.value, falsy_values[value_field], "a falsy rule value must not read as no value")
