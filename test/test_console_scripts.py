import importlib
import tomllib

import pytest

with open("pyproject.toml", "rb") as f:
    SCRIPTS: dict[str, str] = tomllib.load(f)["project"]["scripts"]


def test_there_are_entry_points():
    assert SCRIPTS


@pytest.mark.parametrize("target", SCRIPTS.values(), ids=SCRIPTS.keys())
def test_entry_point_resolves(target: str):
    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    assert callable(getattr(module, attr, None)), f"{target} is not a callable"
