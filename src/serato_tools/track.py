"""A track file's Serato tags, read from one open file and saved in one write.

Also what needs more than one of them, such as snapping the cues to the beatgrid. Needs the `track_tags` extra
(mutagen).
"""

import dataclasses
import warnings

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import ID3FileOrPath, ID3FileTag, open_tagfile


class Track:
    """A track file's Serato tags, read from one open file and saved in one write.

    Change tags through their own methods (e.g. `track.cues_v2.set_beatgrid_locked(...)`), then call this class's
    `save()` once, rather than each tag's own `save()`, which writes the whole file every time. Only ID3 files (.mp3,
    .aiff, .aif) are currently supported.
    """

    @dataclasses.dataclass(frozen=True)
    class SnappedCue:
        """A cue that `snap_cues_to_beats` moved: its index (from 0) and its position in ms before and after."""

        index: int
        old_position: int
        new_position: int

    def __init__(
        self,
        file: ID3FileOrPath,
        *,
        cues_v2: bool = True,
        cues_v1: bool = True,
        beatgrid: bool = True,
        autotags: bool = True,
        waveform: bool = False,
        gain: bool = True,
    ):
        """Opens the track file at `file`, or uses `file` if it's an already open mutagen file, and parses its tags.

        Each tag passed False isn't parsed or saved, and using it raises ValueError. `waveform` is False by default,
        since it's display data that's rarely changed, and it raises ValueError if Serato hasn't built it yet.
        """
        self.tagfile = open_tagfile(file)
        self._cues_v2 = TrackCuesV2(self.tagfile) if cues_v2 else None
        self._cues_v1 = TrackCuesV1(self.tagfile) if cues_v1 else None
        self._beatgrid = TrackBeatgrid(self.tagfile) if beatgrid else None
        self._autotags = TrackAutotags(self.tagfile) if autotags else None
        self._waveform = TrackWaveform(self.tagfile) if waveform else None
        self._gain = TrackGain(self.tagfile) if gain else None

    @staticmethod
    def _parsed[T](tag: T | None, name: str) -> T:
        if tag is None:
            raise ValueError(f"the track's {name} wasn't parsed: pass {name}=True to Track")
        return tag

    @property
    def cues_v2(self) -> TrackCuesV2:
        """`Serato Markers2`: hot cues, loops, flips, track color, and beatgrid lock."""
        return self._parsed(self._cues_v2, "cues_v2")

    @property
    def cues_v1(self) -> TrackCuesV1:
        """`Serato Markers_`: the legacy equivalent of `cues_v2`."""
        return self._parsed(self._cues_v1, "cues_v1")

    @property
    def beatgrid(self) -> TrackBeatgrid:
        """`Serato BeatGrid`."""
        return self._parsed(self._beatgrid, "beatgrid")

    @property
    def autotags(self) -> TrackAutotags:
        """`Serato Autotags`: BPM, autogain, and gain."""
        return self._parsed(self._autotags, "autotags")

    @property
    def waveform(self) -> TrackWaveform:
        """`Serato Overview`."""
        return self._parsed(self._waveform, "waveform")

    @property
    def gain(self) -> TrackGain:
        """The `RVA2:SeratoGain` frame: the gain set in Serato."""
        return self._parsed(self._gain, "gain")

    def get_track_color(self) -> bytes | None:
        """The track's color as the bytes of a `TrackCuesV2.TrackColors` value, or None if its tags have none yet.

        Serato stores the color in `Serato Markers2`, so this is `cues_v2.get_track_color`.
        """
        return self.cues_v2.get_track_color()

    def set_track_color(self, color: TrackCuesV2.TrackColors, delete_tags_v1: bool | None = None):
        """Sets the track's color in memory; call `save()` to write it to the file.

        Serato stores the color in `Serato Markers2`, so this is `cues_v2.set_track_color`: see it for a track whose
        tags have no color yet, and for the deprecated `delete_tags_v1`.
        """
        self.cues_v2.set_track_color(color, delete_tags_v1=delete_tags_v1)

    def is_beatgrid_locked(self) -> bool:
        """Whether the track's beatgrid is locked.

        Serato stores the lock in `Serato Markers2`, not `Serato BeatGrid`, so this is `cues_v2.is_beatgrid_locked`.
        """
        return self.cues_v2.is_beatgrid_locked()

    def set_beatgrid_locked(self, locked: bool, delete_tags_v1: bool | None = None):
        """Locks or unlocks the track's beatgrid in memory; call `save()` to write it to the file.

        Serato stores the lock in `Serato Markers2`, so this is `cues_v2.set_beatgrid_locked`: see it for a track
        whose tags have no lock yet, and for the deprecated `delete_tags_v1`.
        """
        self.cues_v2.set_beatgrid_locked(locked, delete_tags_v1=delete_tags_v1)

    def snap_cues_to_beats(self, tolerance_beats: float, min_ms_change: int = 2) -> list[SnappedCue]:
        """Moves each cue to its nearest beat in memory, as `beatgrid.get_snapped_position` decides; returns the moves.

        Call `save()` to write the change to the file. Raises ValueError if the track has no `Serato Markers2` entries.
        A `min_ms_change` below 2 warns, since that moves nearly every cue Serato placed. Needs `cues_v2` and
        `beatgrid` parsed.
        """
        # both read up front, so a tag that wasn't parsed raises whether or not there are cues to move
        cues_v2, beatgrid = self.cues_v2, self.beatgrid
        if not cues_v2.entries:
            raise ValueError("No entries set")
        if min_ms_change < 2:
            warnings.warn(
                f"min_ms_change={min_ms_change} snaps cues that are 1 ms off the beat, which is most cues Serato placed",
                stacklevel=2,
            )
        snapped: list[Track.SnappedCue] = []

        def rule(track: TrackCuesV2.TrackCuesInfo) -> TrackCuesV2.TrackCuesInfo | None:
            new_cues: list[TrackCuesV2.CueEntry] = []
            for cue in track.cues:
                new_ms = beatgrid.get_snapped_position(cue.position, tolerance_beats, min_ms_change)
                if new_ms is None:
                    new_cues.append(cue)
                else:
                    snapped.append(Track.SnappedCue(cue.index, cue.position, new_ms))
                    new_cues.append(dataclasses.replace(cue, position=new_ms))
            return dataclasses.replace(track, cues=new_cues) if snapped else None

        cues_v2.modify_entries(rule)
        return snapped

    def _parsed_tags(self) -> list[ID3FileTag]:
        parsed = (self._cues_v2, self._cues_v1, self._beatgrid, self._autotags, self._waveform, self._gain)
        return [tag for tag in parsed if tag is not None]

    @property
    def has_changed(self) -> bool:
        """Whether any parsed tag has changes, so that `save()` would write the file."""
        return any(tag.has_changed for tag in self._parsed_tags())

    def save(self, delete_tags_v1: bool = True) -> bool:
        """Writes every tag's changes to the file in one write, and returns whether there were any to write.

        See `TrackCuesV2.save` for `delete_tags_v1`, which applies when `cues_v2` has changes.
        """
        # a set built in full, not any() over a generator, so that every tag puts its changes in before the one write
        # pylint: disable=protected-access
        changed = {
            tag._write_to_tagfile(delete_tags_v1) if isinstance(tag, TrackCuesV2) else tag._write_to_tagfile()
            for tag in self._parsed_tags()
        }
        # pylint: enable=protected-access
        if not any(changed):
            return False
        self.tagfile.save()
        return True
