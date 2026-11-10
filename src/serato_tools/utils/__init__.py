"""Shared helpers: the default Serato folder, the package's logger, and small enum, CLI, and error utilities."""

import logging
import os
from typing import Iterable, TypeVar, Type, cast, Any
from enum import Enum

T = TypeVar("T")

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


def get_enum_key_from_value(value: str | bytes | int, enum_class: Type[Enum]):
    """The name of the `enum_class` member whose value is `value`; raises ValueError if there's none."""
    return enum_class(value).name


def to_array(x: T | Iterable[T]) -> Iterable[T]:
    """`x` itself if it's an iterable other than a str or bytes, or else `x` in a one-item list."""
    if isinstance(x, (str, bytes)):
        return cast(list[T], [x])
    if isinstance(x, Iterable):
        return x
    return [x]


class DataTypeError(Exception):
    """A value whose type doesn't match the one its field holds."""

    def __init__(self, value: Any, expected_type: type | Iterable[type], field: str | None):
        super().__init__(
            f"value must be {' or '.join(e.__name__ for e in to_array(expected_type))} when field is {field} (type: {type(value).__name__}) (value: {str(value)})"
        )


class DeeplyNestedListError(Exception):
    """An entry list nested inside a flat one, such as a track's, which this package can't parse into objects."""

    def __init__(self):
        super().__init__("unexpected type, deeply nested list. if this occurs, need to implement code for it.")
