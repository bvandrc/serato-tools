import logging
import os
from typing import Iterable, TypeVar, Type, cast, Any
from enum import Enum

T = TypeVar("T")

logger = logging.getLogger("serato-tools")

SERATO_DIR_NAME = "_Serato_"
SERATO_DIR = os.path.join(os.path.expanduser("~"), "Music", SERATO_DIR_NAME)
SERATO_DRIVE = os.path.splitdrive(SERATO_DIR)[0]
# the folder the home library's track paths are relative to: the root of the drive it's on
HOME_TRACK_PATH_ROOT = os.path.join(SERATO_DRIVE, os.sep)


def get_track_path_root(file: str) -> str:
    """The folder that the track paths in a Serato library file are relative to.

    Serato stores track paths relative to the root of the drive its `_Serato_` folder is on: `E:\\` or `/Volumes/<drive>`
    for a library on an external drive, or the system drive's root for the home library (`~/Music/_Serato_`). A file
    outside any `_Serato_` folder is treated as part of the home library.
    """
    path = os.path.abspath(file)
    while os.path.basename(path).lower() != SERATO_DIR_NAME.lower():
        parent = os.path.dirname(path)
        if parent == path:
            return HOME_TRACK_PATH_ROOT
        path = parent
    # an external drive keeps its _Serato_ folder at the drive's root, while the home library keeps it in the user's
    # Music folder, so the folder holding _Serato_ is a mount point only for an external drive
    drive_root = os.path.dirname(path)
    if os.path.ismount(drive_root):
        return drive_root
    return os.path.join(os.path.splitdrive(path)[0], os.sep)


def get_key_from_value(value: T, dict: dict[str, T]) -> str:
    for key, v in dict.items():
        if v == value:
            return key
    raise ValueError(f"no key for value {value}")


def parse_cli_keys_and_values(args: list[str]):
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
    for member in enum_class:
        if member.value == value:
            return member.name
    raise ValueError(f"no key for value {value}")


def to_array(x: T | Iterable[T]) -> Iterable[T]:
    if isinstance(x, (str, bytes)):
        return cast(list[T], [x])
    if isinstance(x, Iterable):
        return x
    return [x]


class DataTypeError(Exception):
    def __init__(self, value: Any, expected_type: type | Iterable[type], field: str | None):
        super().__init__(
            f"value must be {' or '.join(e.__name__ for e in to_array(expected_type))} when field is {field} (type: {type(value).__name__}) (value: {str(value)})"
        )


class DeeplyNestedListError(Exception):
    def __init__(self):
        super().__init__("unexpected type, deeply nested list. if this occurs, need to implement code for it.")
