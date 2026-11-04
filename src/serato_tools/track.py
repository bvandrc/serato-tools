"""A track file's Serato tags, read from one open file and saved in one write. Needs the `track_tags` extra."""

from functools import cached_property

from serato_tools.track_autotags import TrackAutotags
from serato_tools.track_beatgrid import TrackBeatgrid
from serato_tools.track_cues_v1 import TrackCuesV1
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_gain import TrackGain
from serato_tools.track_waveform import TrackWaveform
from serato_tools.utils.track_tags import ID3FileOrPath, ID3FileTag, open_tagfile


class Track:
    """A track file's Serato tags, read from one open file and saved in one write.

    Each tag is read the first time it's used, then kept. Change tags through their own methods (e.g.
    `track.cues_v2.set_track_color(...)`), then call this class's `save()` once, rather than each tag's own `save()`,
    which writes the whole file every time. Only ID3 files (.mp3, .aiff, .aif) are currently supported.
    """

    # the cached_property names below, which save() looks through for the tags that have been read
    _TAG_NAMES = ("cues_v2", "cues_v1", "beatgrid", "autotags", "waveform", "gain")

    def __init__(self, file: ID3FileOrPath):
        """Opens the track file at `file`, or uses `file` if it's an already open mutagen file."""
        self.tagfile = open_tagfile(file)

    @cached_property
    def cues_v2(self) -> TrackCuesV2:
        """`Serato Markers2`: hot cues, loops, flips, track color, and beatgrid lock."""
        return TrackCuesV2(self.tagfile)

    @cached_property
    def cues_v1(self) -> TrackCuesV1:
        """`Serato Markers_`: the legacy equivalent of `cues_v2`."""
        return TrackCuesV1(self.tagfile)

    @cached_property
    def beatgrid(self) -> TrackBeatgrid:
        """`Serato BeatGrid`."""
        return TrackBeatgrid(self.tagfile)

    @cached_property
    def autotags(self) -> TrackAutotags:
        """`Serato Autotags`: BPM, autogain, and gain."""
        return TrackAutotags(self.tagfile)

    @cached_property
    def waveform(self) -> TrackWaveform:
        """`Serato Overview`; raises ValueError if Serato hasn't built the track's waveform yet."""
        return TrackWaveform(self.tagfile)

    @cached_property
    def gain(self) -> TrackGain:
        """The `RVA2:SeratoGain` frame: the gain set in Serato."""
        return TrackGain(self.tagfile)

    def set_track_color(self, color: TrackCuesV2.TrackColors, delete_tags_v1: bool = True):
        """Sets the track's color in memory; call `save()` to write it to the file.

        Serato stores the color in `Serato Markers2`, so this is `cues_v2.set_track_color`: see it for
        `delete_tags_v1`, and for a track whose tags have no color yet.
        """
        self.cues_v2.set_track_color(color, delete_tags_v1=delete_tags_v1)

    def save(self) -> bool:
        """Writes every tag's changes to the file in one write, and returns whether there were any to write."""
        tags: list[ID3FileTag] = [tag for name in self._TAG_NAMES if (tag := self.__dict__.get(name)) is not None]
        # a set built in full, not any() over a generator, so that every tag puts its changes in before the one write
        # pylint: disable-next=protected-access
        changed = {tag._write_to_tagfile() for tag in tags}
        if not any(changed):
            return False
        self.tagfile.save()
        return True
