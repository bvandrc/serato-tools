"""The track values that live both in a track file's tags and in the library database, for `Library.set_track_tags`.

Needs the `track_tags` extra. Only ID3 files (.mp3, .aiff, .aif) are supported for now.
"""

from dataclasses import dataclass
from functools import cached_property
from typing import Any, Callable, TypedDict

from serato_tools.database_v2 import DatabaseV2
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils.track_tags import SeratoTrack
from serato_tools.utils import logger


class TrackTags(TypedDict, total=False):
    """Values to set on a track with `Library.set_track_tags`; a key that's left out is left unchanged."""

    color: TrackCuesV2.TrackColors
    beatgrid_locked: bool


class _TrackFile:
    """One track file, opened once so that setting several values reads and writes it only once."""

    def __init__(self, filepath: str, delete_tags_v1: bool):
        self.filepath = filepath
        self.delete_tags_v1 = delete_tags_v1
        self.tagfile = SeratoTrack(filepath).tagfile

    @cached_property
    def cues_v2(self) -> TrackCuesV2:
        return TrackCuesV2(self.tagfile)

    def save(self):
        # only the tags that were read can have changed
        if "cues_v2" in self.__dict__:
            self.cues_v2.save()


@dataclass(frozen=True)
class _TrackProperty[T]:
    db_field: DatabaseV2.Fields
    to_db: Callable[[T], SeratoBinFile.BasicValue]
    # sets the value in the file, returning False if the file has nowhere to put it yet
    write: Callable[[_TrackFile, T], bool]


def _write_color(file: _TrackFile, color: TrackCuesV2.TrackColors) -> bool:
    if file.cues_v2.get_track_color() is None:
        return False
    file.cues_v2.set_track_color(color, delete_tags_v1=file.delete_tags_v1)
    return True


def _write_beatgrid_locked(file: _TrackFile, locked: bool) -> bool:
    if not any(isinstance(entry, TrackCuesV2.BpmLockEntry) for entry in file.cues_v2.entries):
        return False
    file.cues_v2.set_beatgrid_locked(locked, delete_tags_v1=file.delete_tags_v1)
    return True


# keyed by TrackTags' keys
_TRACK_PROPERTIES: dict[str, _TrackProperty[Any]] = {
    # the database holds the color as 0xRRGGBB, the same bytes as the tags hold, as an int
    "color": _TrackProperty[TrackCuesV2.TrackColors](
        DatabaseV2.Fields.COLOR, lambda color: int.from_bytes(color.value, "big"), _write_color
    ),
    "beatgrid_locked": _TrackProperty[bool](
        DatabaseV2.Fields.BEATGRID_LOCKED, lambda locked: locked, _write_beatgrid_locked
    ),
}
assert set(_TRACK_PROPERTIES) == TrackTags.__optional_keys__, "every TrackTags key needs a property, and only those"


def check_track_tags(tags: TrackTags):
    """Raises ValueError if `tags` has a key that isn't one of TrackTags'."""
    unknown = set(tags) - TrackTags.__optional_keys__
    if unknown:
        raise ValueError(f"unknown track tags: {sorted(unknown)}, expected some of {sorted(_TRACK_PROPERTIES)}")


def write_file_tags(filepath: str, tags: TrackTags, delete_tags_v1: bool = True):
    """Sets `tags` in the track file's own tags, and saves it if anything changed.

    A value the file has nowhere to put yet, since Serato hasn't imported the track, is skipped with a warning.
    See TrackCuesV2.set_track_color for `delete_tags_v1`.
    """
    check_track_tags(tags)
    file = _TrackFile(filepath, delete_tags_v1)
    for key, value in tags.items():
        if not _TRACK_PROPERTIES[key].write(file, value):
            # TODO: create the missing tag or entry, once we know exactly what Serato writes for a new track
            logger.warning(
                f"no {key} in the file's {TrackCuesV2.GEOB_KEY} tag (track not yet imported to Serato?), "
                f"so it's only set in the database: {filepath}"
            )
    file.save()


def to_db_values(tags: TrackTags) -> dict[DatabaseV2.Fields, SeratoBinFile.BasicValue]:
    """The database fields and values that hold `tags`."""
    check_track_tags(tags)
    return {_TRACK_PROPERTIES[key].db_field: _TRACK_PROPERTIES[key].to_db(value) for key, value in tags.items()}
