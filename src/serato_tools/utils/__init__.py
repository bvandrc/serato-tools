"""The default Serato folder, the package's logger, the Serato tags' GEOB keys, and the package's error classes, shared
by every module."""

import logging
import os
from enum import StrEnum
from typing import Any, ClassVar

logger = logging.getLogger("serato-tools")

SERATO_DIR_NAME = "_Serato_"
SERATO_DIR = os.path.join(os.path.expanduser("~"), "Music", SERATO_DIR_NAME)
SERATO_DRIVE = os.path.splitdrive(SERATO_DIR)[0]


class GeobKeys(StrEnum):
    """The GEOB frame key of each Serato tag in a track file, each tag class's `GEOB_KEY`."""

    AUTOTAGS = "Serato Autotags"
    BEATGRID = "Serato BeatGrid"
    CUES_V1 = "Serato Markers_"
    CUES_V2 = "Serato Markers2"
    WAVEFORM = "Serato Overview"


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

    GEOB_KEY: ClassVar[GeobKeys]

    def __init__(self, filename: str | None = None):
        """`filename` is the track's, or None for a tag read from bytes."""
        self.filename = filename
        super().__init__(f"no {self.GEOB_KEY} tag" + (f": {filename}" if filename else ""))


class NoCuesError(MissingTagError):
    """A track without a `Serato Markers2` tag, so no cues, such as one that hasn't been analyzed or given any."""

    GEOB_KEY = GeobKeys.CUES_V2


class NoBeatgridError(MissingTagError):
    """A track without a `Serato BeatGrid` tag, such as one Serato hasn't analyzed yet."""

    GEOB_KEY = GeobKeys.BEATGRID


class NoWaveformError(MissingTagError):
    """A track without a `Serato Overview` tag, the waveform, such as one Serato hasn't analyzed yet."""

    GEOB_KEY = GeobKeys.WAVEFORM


class DeeplyNestedListError(Exception):
    """An entry list nested inside a flat one, such as a track's, which this package can't parse into objects."""

    def __init__(self):
        super().__init__("unexpected type, deeply nested list. if this occurs, need to implement code for it.")
