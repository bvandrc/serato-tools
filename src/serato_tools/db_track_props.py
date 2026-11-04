"""The track values that live both in a track file's tags and in the library database, for `Library.set_track_tags`.

Needs the `track_tags` extra. Only ID3 files (.mp3, .aiff, .aif) are currently supported.
"""

from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from serato_tools.database_v2 import DatabaseV2
from serato_tools.track import Track
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils import logger


class DbTrackTags(TypedDict, total=False):
    """Values to set on a track with `Library.set_track_tags`; a key that's left out is left unchanged."""

    color: TrackCuesV2.TrackColors
    beatgrid_locked: bool


@dataclass(frozen=True)
class _TrackProperty[T]:
    db_field: DatabaseV2.Fields
    to_db: Callable[[T], SeratoBinFile.BasicValue]
    # sets the value in the track's tags (taking delete_tags_v1), returning False if the file has nowhere to put it yet
    write: Callable[[Track, T, bool], bool]


def _write_color(track: Track, color: TrackCuesV2.TrackColors, delete_tags_v1: bool) -> bool:
    if track.get_track_color() is None:
        return False
    track.set_track_color(color, delete_tags_v1=delete_tags_v1)
    return True


def _write_beatgrid_locked(track: Track, locked: bool, delete_tags_v1: bool) -> bool:
    # is_beatgrid_locked() is False both for an unlocked track and for one with no lock entry, so look for the entry
    if not any(isinstance(entry, TrackCuesV2.BpmLockEntry) for entry in track.cues_v2.entries):
        return False
    track.set_beatgrid_locked(locked, delete_tags_v1=delete_tags_v1)
    return True


# keyed by DbTrackTags' keys
_TRACK_PROPERTIES: dict[str, _TrackProperty[Any]] = {
    # the database holds the color as 0xRRGGBB, the same bytes as the tags hold, as an int
    "color": _TrackProperty[TrackCuesV2.TrackColors](
        DatabaseV2.Fields.COLOR, lambda color: int.from_bytes(color.value, "big"), _write_color
    ),
    "beatgrid_locked": _TrackProperty[bool](
        DatabaseV2.Fields.BEATGRID_LOCKED, lambda locked: locked, _write_beatgrid_locked
    ),
}
assert set(_TRACK_PROPERTIES) == DbTrackTags.__optional_keys__, "every DbTrackTags key needs a property, and only those"


def check_track_tags(tags: DbTrackTags):
    """Raises ValueError if `tags` has a key that isn't one of DbTrackTags'."""
    unknown = set(tags) - DbTrackTags.__optional_keys__
    if unknown:
        raise ValueError(f"unknown track tags: {sorted(unknown)}, expected some of {sorted(_TRACK_PROPERTIES)}")


def write_file_tags(filepath: str, tags: DbTrackTags, delete_tags_v1: bool = True):
    """Sets `tags` in the track file's own tags, and saves it if anything changed.

    A value the file has nowhere to put yet, since Serato hasn't imported the track, is skipped with a warning.
    See TrackCuesV2.set_track_color for `delete_tags_v1`.
    """
    check_track_tags(tags)
    # every property so far lives in Serato Markers2, so parse only that
    track = Track(filepath, cues_v1=False, beatgrid=False, autotags=False, gain=False)
    for key, value in tags.items():
        if not _TRACK_PROPERTIES[key].write(track, value, delete_tags_v1):
            # TODO: create the missing tag or entry, once we know exactly what Serato writes for a new track
            logger.warning(
                f"no {key} in the file's {TrackCuesV2.GEOB_KEY} tag (track not yet imported to Serato?), "
                f"so it's only set in the database: {filepath}"
            )
    track.save()


def to_db_values(tags: DbTrackTags) -> dict[DatabaseV2.Fields, SeratoBinFile.BasicValue]:
    """The database fields and values that hold `tags`."""
    check_track_tags(tags)
    return {_TRACK_PROPERTIES[key].db_field: _TRACK_PROPERTIES[key].to_db(value) for key, value in tags.items()}
