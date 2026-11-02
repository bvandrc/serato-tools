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
