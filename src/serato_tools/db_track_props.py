"""The track values that live both in a track file's tags and in the library database: how each is written to the file,
and converted to the database's form.

Needs the `track_tags` extra (mutagen). Only ID3 files (.mp3, .aiff, .aif) are currently supported.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypedDict

from serato_tools.database_v2 import DatabaseV2
from serato_tools.track import Track
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_text_frames import TrackTextFrames
from serato_tools.utils.bin_file_base import DataTypeError, SeratoBinFile, expect_type


class DbTrackTags(TypedDict, total=False):
    """Values a track keeps both in its file's tags and in the library database; a key that's left out is unchanged."""

    color: TrackCuesV2.TrackColors
    beatgrid_locked: bool
    title: str
    artist: str
    album: str
    genre: str
    key: str
    grouping: str
    publisher: str
    composer: str
    year: str
    remixer: str
    track_number: int
    disc_number: int
    comment: str


@dataclass(frozen=True)
class _DbTrackProp[T]:
    db_field: DatabaseV2.Fields
    # the type DbTrackTags gives the value
    value_type: type[T]
    to_db_val: Callable[[T], SeratoBinFile.BasicValue]
    # sets the value in the track's tags
    write: Callable[[Track, T], None]


def _text_frame_prop[T](
    field: TrackTextFrames.Fields,
    value_type: type[T],
    to_db_val: Callable[[T], SeratoBinFile.BasicValue],
    to_frame_text: Callable[[T], str],
) -> _DbTrackProp[T]:
    # a value held in an ID3 text frame and in the database field of the same name, as TrackTextFrames.Fields names
    # them after DatabaseV2.Fields
    return _DbTrackProp(
        DatabaseV2.Fields[field.name],
        value_type,
        to_db_val,
        lambda track, value: track.text_frames.set(field, to_frame_text(value)),
    )


def _text_prop(field: TrackTextFrames.Fields) -> _DbTrackProp[str]:
    # the same text in the database and in the frame
    return _text_frame_prop(field, str, lambda text: text, lambda text: text)


def _int_prop(field: TrackTextFrames.Fields) -> _DbTrackProp[int]:
    # an int in the database, and its digits in the frame
    return _text_frame_prop(field, int, lambda number: number, str)


# keyed by DbTrackTags' keys
_DB_TRACK_PROPS: dict[str, _DbTrackProp] = {
    # the database holds the color as 0xRRGGBB, the same bytes as the tags hold, as an int
    "color": _DbTrackProp(
        DatabaseV2.Fields.COLOR,
        TrackCuesV2.TrackColors,
        lambda color: int.from_bytes(color.value, "big"),
        Track.set_track_color,
    ),
    "beatgrid_locked": _DbTrackProp(
        DatabaseV2.Fields.BEATGRID_LOCKED,
        bool,
        lambda locked: locked,
        Track.set_beatgrid_locked,
    ),
    "title": _text_prop(TrackTextFrames.Fields.TITLE),
    "artist": _text_prop(TrackTextFrames.Fields.ARTIST),
    "album": _text_prop(TrackTextFrames.Fields.ALBUM),
    "genre": _text_prop(TrackTextFrames.Fields.GENRE),
    "key": _text_prop(TrackTextFrames.Fields.KEY),
    "grouping": _text_prop(TrackTextFrames.Fields.GROUPING),
    "publisher": _text_prop(TrackTextFrames.Fields.PUBLISHER),
    "composer": _text_prop(TrackTextFrames.Fields.COMPOSER),
    "year": _text_prop(TrackTextFrames.Fields.YEAR),
    "remixer": _text_prop(TrackTextFrames.Fields.REMIXER),
    "track_number": _int_prop(TrackTextFrames.Fields.TRACK_NUMBER),
    "disc_number": _int_prop(TrackTextFrames.Fields.DISC_NUMBER),
    "comment": _text_prop(TrackTextFrames.Fields.COMMENT),
}
assert set(_DB_TRACK_PROPS) == DbTrackTags.__optional_keys__, "every DbTrackTags key needs a property, and only those"


def _check_db_track_tags(tags: DbTrackTags):
    """Raises ValueError if `tags` has a key that isn't one of DbTrackTags'."""
    unknown = set(tags) - DbTrackTags.__optional_keys__
    if unknown:
        raise ValueError(f"unknown track tags: {sorted(unknown)}, expected some of {sorted(_DB_TRACK_PROPS)}")


def write_db_track_tags_to_files(tracks: Mapping[str, DbTrackTags], delete_tags_v1: bool = True) -> list[str]:
    """Sets each track's values in its file's own tags, saving each file that changed, and returns those files' paths.

    `tracks` maps each file's path to its values. Every file is read and every value set before any file is saved, so
    a bad key or value, or a file that can't be read, raises without changing any file. See TrackCuesV2.save for
    `delete_tags_v1`.
    """
    for tags in tracks.values():
        _check_db_track_tags(tags)
    changed_tracks: list[tuple[str, Track]] = []
    for filepath, tags in tracks.items():
        if not tags:
            continue
        # every property lives in Serato Markers2 or a text frame, so parse only those
        track = Track(filepath, cues_v1=False, beatgrid=False, autotags=False, gain=False)
        for key, value in tags.items():
            _DB_TRACK_PROPS[key].write(track, value)
        changed_tracks.append((filepath, track))
    return [filepath for filepath, track in changed_tracks if track.save(delete_tags_v1)]


def to_db_values(tags: DbTrackTags) -> dict[DatabaseV2.Fields, SeratoBinFile.BasicValue]:
    """The database fields and values that hold `tags`.

    Raises DataTypeError for a value of the wrong type for its key, such as a color that isn't a
    TrackCuesV2.TrackColors.
    """
    _check_db_track_tags(tags)
    db_values: dict[DatabaseV2.Fields, SeratoBinFile.BasicValue] = {}
    for key, value in tags.items():
        prop = _DB_TRACK_PROPS[key]
        # a bool is an int, but True isn't a track number
        if prop.value_type is int and isinstance(value, bool):
            raise DataTypeError(value, int, key)
        db_values[prop.db_field] = prop.to_db_val(expect_type(value, prop.value_type, key))
    return db_values
