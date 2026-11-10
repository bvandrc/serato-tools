"""Shared helpers: the default Serato folder, the package's logger, and small CLI and error utilities."""

import logging
import os
from typing import Any

logger = logging.getLogger("serato-tools")

SERATO_DIR_NAME = "_Serato_"
SERATO_DIR = os.path.join(os.path.expanduser("~"), "Music", SERATO_DIR_NAME)
SERATO_DRIVE = os.path.splitdrive(SERATO_DIR)[0]


def parse_cli_keys_and_values(args: list[str]):
    """Groups CLI arguments by the `--key` before them, e.g. `--a 1 2 --b` gives `{"a": ["1", "2"], "b": []}`.

    Arguments before the first key are dropped.
    """
    keys_and_values: dict[str, list[str | int]] = {}
    key = None
    for arg in args:
        if arg.startswith("--"):
            key = arg.lstrip("-")
            keys_and_values[key] = []
        elif key:
            keys_and_values[key].append(arg)

    # pairs[key] = True  # default to True if no value follows
    return keys_and_values


class DataTypeError(Exception):
    """A value whose type doesn't match the one its field holds."""

    def __init__(self, value: Any, expected_type: type, field: str | None):
        super().__init__(
            f"value must be {expected_type.__name__} when field is {field} (type: {type(value).__name__}) (value: {str(value)})"
        )


class DeeplyNestedListError(Exception):
    """An entry list nested inside a flat one, such as a track's, which this package can't parse into objects."""

    def __init__(self):
        super().__init__("unexpected type, deeply nested list. if this occurs, need to implement code for it.")
