"""The default Serato folder, the package's logger, and the package's error classes, shared by every module."""

import logging
import os
from typing import Any

logger = logging.getLogger("serato-tools")

SERATO_DIR_NAME = "_Serato_"
SERATO_DIR = os.path.join(os.path.expanduser("~"), "Music", SERATO_DIR_NAME)
SERATO_DRIVE = os.path.splitdrive(SERATO_DIR)[0]


class DataTypeError(Exception):
    """A value whose type doesn't match the one its field holds."""

    def __init__(self, value: Any, expected_type: type, field: str | None):
        super().__init__(
            f"value must be {expected_type.__name__} when field is {field} (type: {type(value).__name__}) (value: {str(value)})"
        )


class NoCuesError(ValueError):
    """A track without a `Serato Markers2` tag, so no cues, such as one that hasn't been analyzed or given any."""


class NoBeatgridError(ValueError):
    """A track without a `Serato BeatGrid` tag, such as one Serato hasn't analyzed yet."""


class DeeplyNestedListError(Exception):
    """An entry list nested inside a flat one, such as a track's, which this package can't parse into objects."""

    def __init__(self):
        super().__init__("unexpected type, deeply nested list. if this occurs, need to implement code for it.")
