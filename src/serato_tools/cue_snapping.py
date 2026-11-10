#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Snapping a track's cues in `Serato Markers2` to the beats of its `Serato BeatGrid`.

Takes the two tags, e.g. a `Track`'s `cues_v2` and `beatgrid`, and changes the cues through
`TrackCuesV2.modify_entries`. Needs the `track_tags` extra (mutagen).
"""

import dataclasses
import os
import warnings

from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v2 import TrackCuesV2

# the package's folder: the min_ms_change warning skips its frames, to point at the caller's code even when it came
# through another of the package's functions (TrackCuesV2's deprecated snapping methods)
_PACKAGE_DIR = os.path.dirname(__file__) + os.sep


@dataclasses.dataclass(frozen=True)
class SnappedCue:
    """A cue that snapping moved: its index (from 0) and its position in ms before and after."""

    index: int
    old_position: int
    new_position: int


def _check_min_ms_change(min_ms_change: int):
    """Warns if `min_ms_change` is below 2, which moves nearly every cue Serato placed."""
    if min_ms_change < 2:
        warnings.warn(
            f"min_ms_change={min_ms_change} snaps cues that are 1 ms off the beat, which is most cues Serato placed",
            skip_file_prefixes=(_PACKAGE_DIR,),
        )


def _snapped_position(
    beatgrid: TrackBeatgrid, position_ms: int, tolerance_beats: float, min_ms_change: int
) -> int | None:
    """As `get_snapped_position`, without checking `min_ms_change`."""
    snapped_ms = beatgrid.find_nearest_beat(position_ms, tolerance_beats)
    if snapped_ms is None:  # NOTE: don't do `if not`, 0.0 is valid
        return None
    snapped_ms = int(round(snapped_ms))
    return snapped_ms if abs(snapped_ms - position_ms) >= min_ms_change else None


def get_snapped_position(
    beatgrid: TrackBeatgrid, position_ms: int, tolerance_beats: float, min_ms_change: int = 2
) -> int | None:
    """The ms position to snap `position_ms` to, or None if it shouldn't move.

    It shouldn't move when no beat of `beatgrid` is within `tolerance_beats` (a fraction of a beat), or the nearest one
    is less than `min_ms_change` away. The default of 2 leaves 1 ms differences alone: Serato stores cues in whole ms,
    often 1 ms off the rounded beat. Below 2, it warns, since that moves nearly every cue Serato placed. `beatgrid` has
    to be read from an audio file, for the track's length.
    """
    _check_min_ms_change(min_ms_change)
    return _snapped_position(beatgrid, position_ms, tolerance_beats, min_ms_change)


def _snap(
    track: TrackCuesV2.TrackCuesInfo,
    beatgrid: TrackBeatgrid,
    tolerance_beats: float,
    min_ms_change: int,
    snapped: list[SnappedCue],
) -> TrackCuesV2.TrackCuesInfo | None:
    """`track` with its cues snapped, adding each move to `snapped`, or None if none moved."""
    new_cues: list[TrackCuesV2.CueEntry] = []
    for cue in track.cues:
        new_ms = _snapped_position(beatgrid, cue.position, tolerance_beats, min_ms_change)
        if new_ms is None:
            new_cues.append(cue)
        else:
            snapped.append(SnappedCue(cue.index, cue.position, new_ms))
            new_cues.append(dataclasses.replace(cue, position=new_ms))
    return dataclasses.replace(track, cues=new_cues) if new_cues != track.cues else None


def snap_cues_rule(
    beatgrid: TrackBeatgrid, tolerance_beats: float, min_ms_change: int = 2
) -> TrackCuesV2.ModifyCallback:
    """A `TrackCuesV2.modify_entries` callback that moves each cue to its nearest beat, as `get_snapped_position` decides.

    Use it to snap cues along with other changes to the entries; `snap_cues` snaps them on their own.
    """
    _check_min_ms_change(min_ms_change)
    return lambda track: _snap(track, beatgrid, tolerance_beats, min_ms_change, [])


def snap_cues(
    cues: TrackCuesV2, beatgrid: TrackBeatgrid, tolerance_beats: float, min_ms_change: int = 2
) -> list[SnappedCue]:
    """Moves each of `cues`' cues to its nearest beat in memory, as `get_snapped_position` decides, and returns the moves.

    Raises ValueError if `cues` has no entries. Call `save()` on `cues`, or on the `Track` holding it, to write the change
    to the file.
    """
    if not cues.entries:
        raise ValueError("No entries set")
    _check_min_ms_change(min_ms_change)
    snapped: list[SnappedCue] = []
    cues.modify_entries(lambda track: _snap(track, beatgrid, tolerance_beats, min_ms_change, snapped))
    return snapped
