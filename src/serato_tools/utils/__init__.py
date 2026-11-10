"""The default Serato folder, the package's logger, and the package's error classes, shared by every module."""

import logging
import os
from typing import Any, ClassVar

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


class MissingTagError(ValueError):
    """A track file without the Serato tag that was needed, such as one Serato hasn't analyzed yet.

    Catch a subclass to handle one tag's absence, without also catching other ValueErrors, such as a corrupt tag.
    """

    TAG_NAME: ClassVar[str]

    def __init__(self, filename: str | None = None):
        """`filename` is the track's, or None for a tag read from bytes."""
        self.filename = filename
        super().__init__(f"no {self.TAG_NAME} tag" + (f": {filename}" if filename else ""))


class NoCuesError(MissingTagError):
    """A track without a `Serato Markers2` tag, so no cues, such as one that hasn't been analyzed or given any."""

    TAG_NAME = "Serato Markers2"


class NoBeatgridError(MissingTagError):
    """A track without a `Serato BeatGrid` tag, such as one Serato hasn't analyzed yet."""

    TAG_NAME = "Serato BeatGrid"


class NoWaveformError(MissingTagError):
    """A track without a `Serato Overview` tag, the waveform, such as one Serato hasn't analyzed yet."""

    TAG_NAME = "Serato Overview"


class DeeplyNestedListError(Exception):
    """An entry list nested inside a flat one, such as a track's, which this package can't parse into objects."""

    def __init__(self):
        super().__init__("unexpected type, deeply nested list. if this occurs, need to implement code for it.")
