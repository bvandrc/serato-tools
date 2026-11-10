#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `Serato BeatGrid` tag, which holds a track's beatgrid as markers.

Also the CLIs that print it, or analyze and write one. Analyzing needs the `beatgrid_analysis` extra (librosa and
numpy).
"""

import collections
import io
import struct
import sys
from typing import cast, overload, TypeVar, Unpack
from dataclasses import dataclass

from mutagen._file import FileType
from mutagen.mp3 import HeaderNotFoundError
from mutagen.id3 import ID3


from serato_tools.utils import logger
from serato_tools.utils.track_tags import SeratoGeobTag, GeobKeys, NoBeatgridError

_T = TypeVar("_T")


class TrackBeatgrid(SeratoGeobTag):
    """The `Serato BeatGrid` tag, which holds a track's beatgrid.

    The grid is markers at beat positions, each giving the beats to the next, then a final BPM.

    `entries` holds the markers as stored, ending with the terminal marker and a footer, or None for a track without a
    grid. `enhanced_entries` adds each non-terminal marker's BPM.
    """

    GEOB_KEY = GeobKeys.BEATGRID
    VERSION = (0x01, 0x00)

    NonTerminalBeatgridMarker = collections.namedtuple(
        "NonTerminalBeatgridMarker",
        ("position_s", "beats_till_next_marker"),
    )
    TerminalBeatgridMarker = collections.namedtuple(
        "TerminalBeatgridMarker",
        ("position_s", "bpm"),
    )
    Footer = collections.namedtuple("Footer", ("unknown",))

    NonTerminalBeatgridMarkerEnhanced = collections.namedtuple(
        "NonTerminalBeatgridMarkerEnhanced",
        NonTerminalBeatgridMarker._fields + ("bpm",),
    )

    _EntryList = tuple[Unpack[tuple[_T, ...]], TerminalBeatgridMarker, Footer]
    type EntryList = _EntryList[NonTerminalBeatgridMarker]
    type EntryListEnhanced = _EntryList[NonTerminalBeatgridMarkerEnhanced]

    def __init__(self, file_or_data: SeratoGeobTag.FileOrData):
        self._raw_data: bytes | None = None
        super().__init__(file_or_data)

        self.entries: TrackBeatgrid.EntryList | None = None
        self.enhanced_entries: TrackBeatgrid.EntryListEnhanced | None = None

        if self._raw_data is not None:
            entries = tuple(self._parse(self._raw_data))
            if len(entries) == 1 and isinstance(entries[0], TrackBeatgrid.Footer):
                # sometimes happens from serato. There is no grid in this case.
                entries = None
            if entries:
                self.entries = cast(TrackBeatgrid.EntryList, entries)
                self._check_markers(*self._check_and_split(self.entries)[:2])
                self.enhanced_entries = self._enhance_entries(self.entries)

        self.beats: list[TrackBeatgrid.BeatPoint] | None = None

    def __str__(self) -> str:
        if not self.entries:
            return ""
        if not self.enhanced_entries:
            raise ValueError("no enhanced_entries set")
        nonterminal_markers, terminal_marker, _footer = self._check_and_split(self.enhanced_entries)
        return "\n".join(str(marker) for marker in (*nonterminal_markers, terminal_marker))

    def delete(self):
        """Deletes the tag in memory, returning whether the file had it; call `save()` to write the deletion."""
        was_deleted = super().delete()
        self.entries = None
        self.enhanced_entries = None
        self.beats = None
        return was_deleted

    def _parse(self, data: bytes):
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        num_markers = struct.unpack(">I", fp.read(4))[0]
        for i in range(num_markers):
            position_s = struct.unpack(">f", fp.read(4))[0]
            data = fp.read(4)
            if i == num_markers - 1:
                bpm = struct.unpack(">f", data)[0]
                yield TrackBeatgrid.TerminalBeatgridMarker(position_s, bpm)
            else:
                beats_till_next_marker = struct.unpack(">I", data)[0]
                yield TrackBeatgrid.NonTerminalBeatgridMarker(position_s, beats_till_next_marker)

        # The footer byte's meaning is unknown: it changes even when Serato's Edit Grid mode is entered and left
        # without any change, so it's kept only to write it back as read.
        footer_byte = fp.read(1)
        footer_value = struct.unpack("B", footer_byte)[0] if len(footer_byte) == 1 else 0
        yield TrackBeatgrid.Footer(footer_value)
        assert fp.read() == b""

    __SplitEntryList = tuple[list[_T], TerminalBeatgridMarker, Footer]

    @overload
    def _check_and_split(self) -> "__SplitEntryList[NonTerminalBeatgridMarker]": ...
    @overload
    def _check_and_split(self, entries: "_EntryList[_T]") -> "__SplitEntryList[_T]": ...
    def _check_and_split(self, entries: "_EntryList[_T] | None" = None):
        """Splits `entries`, or `self.entries`, into the non-terminal markers, the terminal marker, and the footer.

        Raises NoBeatgridError if there are none, and ValueError if they aren't in that order with one terminal marker
        and one footer.
        """
        if entries is None:
            entries = cast("TrackBeatgrid._EntryList[_T]", self.entries)

        if not entries:
            raise NoBeatgridError(self.filename)

        nonterminal_markers: list[_T] = []
        terminal_markers: list[TrackBeatgrid.TerminalBeatgridMarker] = []
        footers: list[TrackBeatgrid.Footer] = []

        for entry in entries:
            if isinstance(
                entry, (TrackBeatgrid.NonTerminalBeatgridMarker, TrackBeatgrid.NonTerminalBeatgridMarkerEnhanced)
            ):
                nonterminal_markers.append(cast(_T, entry))
            elif isinstance(entry, TrackBeatgrid.TerminalBeatgridMarker):
                terminal_markers.append(entry)
            elif isinstance(entry, TrackBeatgrid.Footer):
                footers.append(entry)
            else:
                raise TypeError(f"unexpected value type {entry}")

        assert len(terminal_markers) == 1, f"should only be 1 terminal marker, but #: {len(terminal_markers)}"
        assert len(footers) == 1, f"should only be 1 footer, but #: {len(footers)}"
        assert isinstance(entries[-1], TrackBeatgrid.Footer), "last item should be a footer"
        assert isinstance(entries[-2], TrackBeatgrid.TerminalBeatgridMarker), "last item should be a terminal marker"
        return (nonterminal_markers, terminal_markers[0], footers[0])

    @staticmethod
    def _check_markers(
        nonterminal_markers: "list[TrackBeatgrid.NonTerminalBeatgridMarker]",
        terminal_marker: "TrackBeatgrid.TerminalBeatgridMarker",
    ):
        """Raises ValueError for a grid with markers out of order, a 0-beat segment, or no BPM."""
        # Every grid Serato DJ Pro 2 was seen writing passes these checks, so one that doesn't is a grid this class may
        # misread, or one Serato can't use. A negative position isn't rejected, since a grid whose first beat comes
        # before the track starts seems possible.
        previous_position_s = None
        for marker in nonterminal_markers:
            if marker.beats_till_next_marker <= 0:
                raise ValueError(f"beatgrid marker at {marker.position_s} s has {marker.beats_till_next_marker} beats")
        for marker in (*nonterminal_markers, terminal_marker):
            if previous_position_s is not None and marker.position_s <= previous_position_s:
                raise ValueError(
                    f"beatgrid marker at {marker.position_s} s doesn't come after the one at {previous_position_s} s"
                )
            previous_position_s = marker.position_s
        if not terminal_marker.bpm > 0:
            raise ValueError(f"beatgrid's last marker has a BPM of {terminal_marker.bpm}")

    def _serialize(self):
        entries = self._check_and_split()
        nonterminal_markers, terminal_marker, footer = entries
        self._check_markers(nonterminal_markers, terminal_marker)
        markers = (*nonterminal_markers, terminal_marker)

        fp = io.BytesIO()
        # Write version
        fp.write(self._pack_version())

        # Write markers
        fp.write(struct.pack(">I", len(markers)))
        for marker in markers:
            fp.write(struct.pack(">f", marker.position_s))
            if isinstance(marker, TrackBeatgrid.TerminalBeatgridMarker):
                fp.write(struct.pack(">f", marker.bpm))
            elif isinstance(marker, TrackBeatgrid.NonTerminalBeatgridMarker):
                fp.write(struct.pack(">I", marker.beats_till_next_marker))
            else:
                raise TypeError(f"Unexpected marker type: {type(marker)}")

        # Write footer
        fp.write(struct.pack("B", footer.unknown))

        # Set to self._raw_data
        fp.seek(0)
        self._raw_data = fp.getvalue()

    @staticmethod
    def _enhance_entries(raw_entries: "TrackBeatgrid.EntryList") -> "TrackBeatgrid.EntryListEnhanced":
        """`raw_entries` with each non-terminal marker's BPM, from its beats and the time to the next marker, added."""
        *markers, footer = raw_entries
        enhanced: list[TrackBeatgrid.NonTerminalBeatgridMarkerEnhanced | TrackBeatgrid.TerminalBeatgridMarker] = []
        for i, marker in enumerate(markers):
            if isinstance(marker, TrackBeatgrid.NonTerminalBeatgridMarker):
                next_marker = markers[i + 1]
                time_diff = next_marker.position_s - marker.position_s
                if time_diff == 0:
                    bpm = float("nan")  # mark invalid BPM when segment has zero duration
                else:
                    bpm = marker.beats_till_next_marker / time_diff * 60
                enhanced.append(
                    TrackBeatgrid.NonTerminalBeatgridMarkerEnhanced(
                        marker.position_s,
                        marker.beats_till_next_marker,
                        bpm,
                    )
                )
            else:
                enhanced.append(marker)
        return cast(TrackBeatgrid.EntryListEnhanced, (*enhanced, footer))

    def get_beat_position(self, position_ms: float) -> float:
        """How many beats into the grid `position_ms` is, from 0 at the first marker; fractional between beats."""
        position_s = position_ms / 1000.0
        nonterminal_markers, terminal_marker, _footer = self._check_and_split()

        cumulative_beats = 0.0
        for i, marker in enumerate(nonterminal_markers):
            next_pos = (
                nonterminal_markers[i + 1].position_s
                if i + 1 < len(nonterminal_markers)
                else terminal_marker.position_s
            )
            if position_s < next_pos:
                if marker.beats_till_next_marker <= 0 or next_pos <= marker.position_s:
                    raise ValueError(
                        f"invalid beatgrid: zero-length or zero-beat segment at {marker.position_s}s (beats_till_next_marker={marker.beats_till_next_marker}, next marker at {next_pos}s)"
                    )
                interval = (next_pos - marker.position_s) / marker.beats_till_next_marker
                return cumulative_beats + (position_s - marker.position_s) / interval
            cumulative_beats += marker.beats_till_next_marker

        if terminal_marker.bpm <= 0:
            raise ValueError(f"invalid terminal marker bpm: {terminal_marker.bpm}")
        terminal_interval = 60.0 / terminal_marker.bpm
        return cumulative_beats + (position_s - terminal_marker.position_s) / terminal_interval

    BeatPoint = collections.namedtuple(
        "BeatInfo",
        ("position_s", "bpm"),
    )

    def get_beats(self) -> list["TrackBeatgrid.BeatPoint"]:
        """Return a list of BeatInfo(position_s, bpm, index) for all beats in the track."""
        if not isinstance(self.tagfile, FileType):
            raise ValueError("no tagfile set, cannot determine track length")
        if not self.entries:
            return []
        if not self.enhanced_entries:
            raise ValueError("no enhanced_entries set")

        nonterminal_markers, terminal_marker, _footer = self._check_and_split(self.enhanced_entries)

        beats: list[TrackBeatgrid.BeatPoint] = []

        for i, marker in enumerate(nonterminal_markers):
            next_pos = (
                nonterminal_markers[i + 1].position_s
                if i + 1 < len(nonterminal_markers)
                else terminal_marker.position_s
            )
            if marker.beats_till_next_marker <= 0:
                raise ValueError(
                    f"invalid beatgrid: marker at {marker.position_s}s has beats_till_next_marker={marker.beats_till_next_marker}"
                )
            interval = (next_pos - marker.position_s) / marker.beats_till_next_marker
            for j in range(marker.beats_till_next_marker):
                pos = marker.position_s + j * interval
                beats.append(TrackBeatgrid.BeatPoint(position_s=pos, bpm=marker.bpm))

        if isinstance(self.tagfile, ID3):
            raise ValueError("ID3 tagfile not supported, must pass MP3() type or other that has .length attribute")
        track_length: float = self.tagfile.info.length
        if track_length > 60 * 60 * 3:  # 3 hours
            raise ValueError(f"Track length is too long: {track_length} seconds")
        if terminal_marker.bpm <= 0:
            raise ValueError(f"invalid terminal marker bpm: {terminal_marker.bpm}")
        terminal_interval = 60.0 / terminal_marker.bpm
        pos = terminal_marker.position_s
        while pos <= track_length:
            beats.append(TrackBeatgrid.BeatPoint(position_s=pos, bpm=terminal_marker.bpm))
            pos += terminal_interval

        if not beats:
            raise ValueError("No beats found")
        if len(beats) < 5:
            raise ValueError(f"More beats should be found... num beats: {len(beats)}")

        self.beats = beats
        return beats

    def find_nearest_beat(self, position_ms: int, tolerance_beats: float) -> float | None:
        """The position in ms of the beat nearest `position_ms`, or None if it's on a beat or none is within tolerance.

        `tolerance_beats` is a fraction of a beat. Needs the tag read from an audio file, for the track's length.
        Raises NoBeatgridError for a track without a beatgrid.
        """
        if not self.entries:
            raise NoBeatgridError(self.filename)
        position_s = position_ms / 1000.0

        nearest_beat: TrackBeatgrid.BeatPoint | None = None
        nearest_distance_beats: float | None = None

        beats = self.beats or self.get_beats()
        for i, beat in enumerate(beats):
            if position_s == beat.position_s:
                return None

            bpm_for_interval = beats[i - 1].bpm if i > 0 and position_s < beat.position_s else beat.bpm
            interval_s = 60.0 / bpm_for_interval
            distance_beats = abs(position_s - beat.position_s) / interval_s

            if distance_beats > tolerance_beats:
                continue

            if nearest_distance_beats is None or distance_beats < nearest_distance_beats:
                nearest_distance_beats = distance_beats
                nearest_beat = beat

        return None if nearest_beat is None else nearest_beat.position_s * 1000.0

    def get_snapped_position(self, position_ms: int, tolerance_beats: float, min_ms_change: int = 2) -> int | None:
        """The whole ms position to snap a cue at `position_ms` to, or None if it shouldn't move.

        It shouldn't move when no beat is within `tolerance_beats` (a fraction of a beat), or the nearest one is less
        than `min_ms_change` away. The default of 2 leaves 1 ms differences alone: Serato stores cues in whole ms, often
        1 ms off the rounded beat. Needs the tag read from an audio file, for the track's length. Raises
        NoBeatgridError for a track without a beatgrid.
        """
        snapped_ms = self.find_nearest_beat(position_ms, tolerance_beats)
        if snapped_ms is None:  # NOTE: don't do `if not`, 0.0 is valid
            return None
        snapped_ms = int(round(snapped_ms))
        return snapped_ms if abs(snapped_ms - position_ms) >= min_ms_change else None

    def analyze_and_write(self):
        """Replaces the grid with one found by analyzing the track's audio, then saves it to the file.

        A marker goes on each downbeat found, 4 beats apart, and the last takes the BPM in the file's tags. Needs the
        `beatgrid_analysis` extra (librosa and numpy), and takes seconds. An MP3's grid may be off by tens of ms, since
        the analysis decodes it differently than Serato does.
        """
        if not self.tagfile:
            raise Exception("No tagfile set")

        from serato_tools.utils.beatgrid_analyze import analyze_beatgrid

        bpm = float(str(self.tagfile["TBPM"]))
        filename = cast(str, self.tagfile.filename)

        # Serato's beatgrid positions are times in audio as Serato's own MP3 decoder decodes it. Other decoders start
        # MP3s at a different point: Serato's times are about 26 ms (44.1 kHz) or 24 ms (48 kHz) late for FFmpeg or
        # libmad, and 12 to 60 ms late for CoreAudio. The analysis below doesn't correct for its decoder, so an MP3's
        # grid may be off by about that much.
        logger.info("Analyzing beat grid...")
        analyzed_breatgrid = analyze_beatgrid(filename, bpm_helper=bpm)
        if not analyzed_breatgrid.downbeats:
            raise ValueError("beatgrid analysis found no downbeats, cannot write beatgrid")

        logger.info("Writing tags...")
        raw_entries: TrackBeatgrid.EntryList = (
            *(
                TrackBeatgrid.NonTerminalBeatgridMarker(position_s, 4)
                for position_s in analyzed_breatgrid.downbeats[:-1]
            ),
            TrackBeatgrid.TerminalBeatgridMarker(analyzed_breatgrid.downbeats[-1], bpm=bpm or analyzed_breatgrid.bpm),
            TrackBeatgrid.Footer(0),
        )

        self.entries = raw_entries
        self.enhanced_entries = self._enhance_entries(self.entries)

        self._serialize()
        self.save()


def main():
    """Prints a track's beatgrid markers, or with `--analyze`, analyzes the track and writes a new grid."""
    import argparse

    @dataclass
    class Args:
        file: str
        analyze: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("-a", "--analyze", action="store_true", help="Analyze dynamic beatgrid and write to file")
    args = Args(**vars(parser.parse_args()))

    try:
        tags = TrackBeatgrid(args.file)
    except HeaderNotFoundError:
        with open(args.file, mode="rb") as fp:
            data = fp.read()
        tags = TrackBeatgrid(data)

    if args.analyze and tags.tagfile:
        tags.analyze_and_write()
    else:
        if not tags.entries:
            sys.exit(str(NoBeatgridError(tags.filename)))
        for entry in tags.entries:
            print(entry)


def main_analyze():
    """The `serato_analyze_beatgrid` CLI: analyzes a track's audio and writes a new beatgrid to its tags."""
    import argparse

    @dataclass
    class Args:
        file: str

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = Args(**vars(parser.parse_args()))
    tags = TrackBeatgrid(args.file)
    tags.analyze_and_write()


if __name__ == "__main__":
    main()
