#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `Serato BeatGrid` tag, which holds a track's beatgrid as markers.

Also the CLIs that print it, or analyze and write one. Analyzing needs the `beatgrid_analysis` extra (librosa and
numpy).
"""

import collections
import io
import math
import struct
import sys
from dataclasses import dataclass
from typing import cast, overload

from mutagen._file import FileType
from mutagen.id3 import ID3

from serato_tools.utils import logger
from serato_tools.utils.track_tags import GeobKeys, NoBeatgridError, SeratoGeobTag


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

    type _EntryList[T] = tuple[*tuple[T, ...], "TrackBeatgrid.TerminalBeatgridMarker", "TrackBeatgrid.Footer"]
    type EntryList = _EntryList[NonTerminalBeatgridMarker]
    type EntryListEnhanced = _EntryList[NonTerminalBeatgridMarkerEnhanced]

    def __init__(self, file_or_data: SeratoGeobTag.FileOrData):
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
                self._validate_grid(self.entries)
                self.enhanced_entries = self._enhance_entries(self.entries)

        self.beats: list[TrackBeatgrid.BeatPoint] | None = None

    def __str__(self) -> str:
        if not self.entries:
            return ""
        if not self.enhanced_entries:
            raise ValueError("no enhanced_entries set")
        # unchecked, so that a grid set in memory prints even when it's invalid
        return "\n".join(str(marker) for marker in self.enhanced_entries[:-1])

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
        if rest := fp.read():
            raise ValueError(f"beatgrid has {len(rest)} bytes after its footer")

    @overload
    def _validate_grid(self) -> "TrackBeatgrid.EntryList": ...
    @overload
    def _validate_grid[T: "TrackBeatgrid._NonTerminalMarker"](self, entries: "_EntryList[T]") -> "_EntryList[T]": ...
    def _validate_grid[T: "TrackBeatgrid._NonTerminalMarker"](self, entries: "_EntryList[T] | None" = None):
        """Validates the grid in `entries`, or `self.entries`, and returns it.

        Raises NoBeatgridError if there are no entries, and ValueError if they aren't non-terminal markers, then one
        terminal marker, then one footer, or for a grid with markers out of order, a 0-beat segment, or no BPM.
        """
        if entries is None:
            entries = cast("TrackBeatgrid._EntryList[T]", self.entries)

        if not entries:
            raise NoBeatgridError(self.filename)

        if not isinstance(entries[-1], TrackBeatgrid.Footer):
            raise ValueError("a beatgrid's last entry must be its footer")
        if len(entries) < 2 or not isinstance(entries[-2], TrackBeatgrid.TerminalBeatgridMarker):
            raise ValueError("a beatgrid's footer must come right after its terminal marker")
        *nonterminal_markers, terminal_marker, _footer = entries
        if not all(
            isinstance(
                marker, (TrackBeatgrid.NonTerminalBeatgridMarker, TrackBeatgrid.NonTerminalBeatgridMarkerEnhanced)
            )
            for marker in nonterminal_markers
        ):
            raise ValueError("a beatgrid's entries before its terminal marker must be non-terminal markers")

        # Every grid Serato DJ Pro 2 was seen writing passes the checks below, so one that doesn't is a grid this class
        # may misread, or one Serato can't use. A negative position isn't rejected, since a grid whose first beat comes
        # before the track starts seems possible.
        for marker, end_s in self._marker_spans(nonterminal_markers, terminal_marker):
            if marker.beats_till_next_marker <= 0:
                raise ValueError(f"beatgrid marker at {marker.position_s} s has {marker.beats_till_next_marker} beats")
            if end_s <= marker.position_s:
                raise ValueError(f"beatgrid marker at {end_s} s doesn't come after the one at {marker.position_s} s")
        if math.isnan(terminal_marker.bpm) or terminal_marker.bpm <= 0:
            raise ValueError(f"beatgrid's last marker has a BPM of {terminal_marker.bpm}")

        return entries

    def _serialize(self):
        *nonterminal_markers, terminal_marker, footer = self._validate_grid()
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

    type _NonTerminalMarker = NonTerminalBeatgridMarker | NonTerminalBeatgridMarkerEnhanced

    @staticmethod
    def _marker_spans[T: "TrackBeatgrid._NonTerminalMarker"](
        nonterminal_markers: list[T], terminal_marker: "TrackBeatgrid.TerminalBeatgridMarker"
    ) -> list[tuple[T, float]]:
        """Each non-terminal marker's span: the marker, and the position in seconds where its beats end, at the next marker."""
        ends_s = [marker.position_s for marker in nonterminal_markers[1:]] + [terminal_marker.position_s]
        return list(zip(nonterminal_markers, ends_s))

    @staticmethod
    def _enhance_entries(raw_entries: "TrackBeatgrid.EntryList") -> "TrackBeatgrid.EntryListEnhanced":
        """`raw_entries` with each non-terminal marker's BPM, from its beats and the time to the next marker, added.

        Needs entries that `_validate_grid` accepts, so that no segment is zero seconds long.
        """
        *markers, terminal_marker, footer = raw_entries
        return (
            *(
                TrackBeatgrid.NonTerminalBeatgridMarkerEnhanced(
                    marker.position_s,
                    marker.beats_till_next_marker,
                    marker.beats_till_next_marker / (end_s - marker.position_s) * 60,
                )
                for marker, end_s in TrackBeatgrid._marker_spans(markers, terminal_marker)
            ),
            terminal_marker,
            footer,
        )

    def get_beat_position(self, position_ms: float) -> float:
        """How many beats into the grid `position_ms` is, from 0 at the first marker; fractional between beats."""
        position_s = position_ms / 1000.0
        # checked again, since entries may have been changed since they were parsed
        *nonterminal_markers, terminal_marker, _footer = self._validate_grid()

        cumulative_beats = 0.0
        for marker, end_s in self._marker_spans(nonterminal_markers, terminal_marker):
            if position_s < end_s:
                interval = (end_s - marker.position_s) / marker.beats_till_next_marker
                return cumulative_beats + (position_s - marker.position_s) / interval
            cumulative_beats += marker.beats_till_next_marker

        terminal_interval = 60.0 / terminal_marker.bpm
        return cumulative_beats + (position_s - terminal_marker.position_s) / terminal_interval

    BeatPoint = collections.namedtuple("BeatPoint", ("position_s", "bpm"))

    def get_beats(self) -> list["TrackBeatgrid.BeatPoint"]:
        """Every beat in the track, as a BeatPoint: its position in seconds, and the BPM there."""
        if not isinstance(self.tagfile, FileType):
            raise ValueError("no tagfile set, cannot determine track length")
        if not self.entries:
            return []
        if not self.enhanced_entries:
            raise ValueError("no enhanced_entries set")

        # enhanced_entries is only built from checked markers, but it's checked again rather than divide by a 0 beat
        # count or terminal BPM if it was set directly
        *nonterminal_markers, terminal_marker, _footer = self._validate_grid(self.enhanced_entries)

        beats: list[TrackBeatgrid.BeatPoint] = []

        for marker, end_s in self._marker_spans(nonterminal_markers, terminal_marker):
            interval = (end_s - marker.position_s) / marker.beats_till_next_marker
            for j in range(marker.beats_till_next_marker):
                pos = marker.position_s + j * interval
                beats.append(TrackBeatgrid.BeatPoint(position_s=pos, bpm=marker.bpm))

        if isinstance(self.tagfile, ID3):
            raise ValueError("ID3 tagfile not supported, must pass MP3() type or other that has .length attribute")
        track_length: float = self.tagfile.info.length
        if track_length > 60 * 60 * 3:  # 3 hours
            raise ValueError(f"Track length is too long: {track_length} seconds")
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
        tagfile = self._require_tagfile()

        from serato_tools.utils.beatgrid_analyze import analyze_beatgrid

        bpm = float(str(tagfile["TBPM"]))
        filename = cast(str, tagfile.filename)

        # Serato's beatgrid positions are times in audio as Serato's own MP3 decoder decodes it. Other decoders start
        # MP3s at a different point: Serato's times are about 26 ms (44.1 kHz) or 24 ms (48 kHz) late for FFmpeg or
        # libmad, and 12 to 60 ms late for CoreAudio. The analysis below doesn't correct for its decoder, so an MP3's
        # grid may be off by about that much.
        logger.info("Analyzing beat grid...")
        analyzed = analyze_beatgrid(filename, bpm_helper=bpm)
        if not analyzed.downbeats:
            raise ValueError("beatgrid analysis found no downbeats, cannot write beatgrid")

        logger.info("Writing tags...")
        raw_entries: TrackBeatgrid.EntryList = (
            *(TrackBeatgrid.NonTerminalBeatgridMarker(position_s, 4) for position_s in analyzed.downbeats[:-1]),
            TrackBeatgrid.TerminalBeatgridMarker(analyzed.downbeats[-1], bpm=bpm or analyzed.bpm),
            TrackBeatgrid.Footer(0),
        )

        # checked before replacing the old grid, so an analysis that gives an invalid one leaves it as it was, and
        # before _enhance_entries, which needs valid markers
        self._validate_grid(raw_entries)
        self.entries = raw_entries
        self.enhanced_entries = self._enhance_entries(self.entries)
        # the old grid's beats, which find_nearest_beat would otherwise still search
        self.beats = None

        self._serialize()
        self.save()


def main():
    """Prints a track's beatgrid markers, or with `--analyze`, analyzes the track and writes a new grid."""
    import argparse

    from serato_tools.utils.cli import open_tag_file_or_data

    @dataclass
    class Args:
        file: str
        analyze: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("-a", "--analyze", action="store_true", help="Analyze dynamic beatgrid and write to file")
    args = Args(**vars(parser.parse_args()))

    tags = open_tag_file_or_data(TrackBeatgrid, args.file)

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
