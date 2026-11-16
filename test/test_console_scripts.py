import importlib
import tomllib

import pytest

with open("pyproject.toml", "rb") as f:
    SCRIPTS: dict[str, str] = tomllib.load(f)["project"]["scripts"]
# with none, the test below would be skipped for an empty parameter set rather than fail; this errors at collection
assert SCRIPTS, "pyproject.toml declares no console scripts"


@pytest.mark.parametrize("target", SCRIPTS.values(), ids=SCRIPTS.keys())
def test_entry_point_resolves(target: str):
    module_name, _, attr = target.partition(":")
    module = importlib.import_module(module_name)
    assert callable(getattr(module, attr, None)), f"{target} is not a callable"
