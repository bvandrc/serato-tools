"""The track values that live both in a track file's tags and in the library database: how each is written to the file,
and converted to the database's form.

Needs the `track_tags` extra. Only ID3 files (.mp3, .aiff, .aif) are currently supported.
"""

from dataclasses import dataclass
from typing import Any, Callable, Mapping, TypedDict

from serato_tools.database_v2 import DatabaseV2
from serato_tools.track import Track
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.utils.bin_file_base import SeratoBinFile


class DbTrackTags(TypedDict, total=False):
    """Values a track keeps both in its file's tags and in the library database; a key that's left out is unchanged."""

    color: TrackCuesV2.TrackColors
    beatgrid_locked: bool


@dataclass(frozen=True)
class _DbTrackProp[T]:
    db_field: DatabaseV2.Fields
    to_db_val: Callable[[T], SeratoBinFile.BasicValue]
    # sets the value in the track's tags, taking delete_tags_v1
    write: Callable[[Track, T, bool], None]


# keyed by DbTrackTags' keys
_DB_TRACK_PROPS: dict[str, _DbTrackProp[Any]] = {
    # the database holds the color as 0xRRGGBB, the same bytes as the tags hold, as an int
    "color": _DbTrackProp[TrackCuesV2.TrackColors](
        DatabaseV2.Fields.COLOR,
        lambda color: int.from_bytes(color.value, "big"),
        lambda track, color, delete_tags_v1: track.set_track_color(color, delete_tags_v1=delete_tags_v1),
    ),
    "beatgrid_locked": _DbTrackProp[bool](
        DatabaseV2.Fields.BEATGRID_LOCKED,
        lambda locked: locked,
        lambda track, locked, delete_tags_v1: track.set_beatgrid_locked(locked, delete_tags_v1=delete_tags_v1),
    ),
}
assert set(_DB_TRACK_PROPS) == DbTrackTags.__optional_keys__, "every DbTrackTags key needs a property, and only those"


def _check_db_track_tags(tags: DbTrackTags):
    """Raises ValueError if `tags` has a key that isn't one of DbTrackTags'."""
    unknown = set(tags) - DbTrackTags.__optional_keys__
    if unknown:
        raise ValueError(f"unknown track tags: {sorted(unknown)}, expected some of {sorted(_DB_TRACK_PROPS)}")


def write_db_track_tags_to_files(tracks: Mapping[str, DbTrackTags], delete_tags_v1: bool = True):
    """Sets each track's values in its file's own tags, saving each file that changed.

    `tracks` maps each file's path to its values. Every file is read and every value set before any file is saved, so
    a bad key or value, or a file that can't be read, raises without changing any file. See
    TrackCuesV2.set_track_color for `delete_tags_v1`.
    """
    for tags in tracks.values():
        _check_db_track_tags(tags)
    changed_tracks: list[Track] = []
    for filepath, tags in tracks.items():
        if not tags:
            continue
        # every property so far lives in Serato Markers2, so parse only that
        track = Track(filepath, cues_v1=False, beatgrid=False, autotags=False, gain=False)
        for key, value in tags.items():
            _DB_TRACK_PROPS[key].write(track, value, delete_tags_v1)
        changed_tracks.append(track)
    for track in changed_tracks:
        track.save()


def to_db_values(tags: DbTrackTags) -> dict[DatabaseV2.Fields, SeratoBinFile.BasicValue]:
    """The database fields and values that hold `tags`."""
    _check_db_track_tags(tags)
    return {_DB_TRACK_PROPS[key].db_field: _DB_TRACK_PROPS[key].to_db_val(value) for key, value in tags.items()}
