"""Tests that every console script in pyproject.toml points at a function that exists."""

import importlib
import tomllib
import unittest


class TestCase(unittest.TestCase):
    def test_entry_points_resolve(self):
        with open("pyproject.toml", "rb") as f:
            scripts: dict[str, str] = tomllib.load(f)["project"]["scripts"]
        self.assertTrue(scripts)

        for name, target in scripts.items():
            with self.subTest(script=name):
                module_name, _, attr = target.partition(":")
                module = importlib.import_module(module_name)
                self.assertTrue(callable(getattr(module, attr, None)), f"{target} is not a callable")


if __name__ == "__main__":
    unittest.main()
