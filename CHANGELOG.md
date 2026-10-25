# Changelog

Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [4.0.3] - 2026-10-25

- Cue snapping: a snapped position of 0 ms counts as a valid beat, and `min_ms_change` is inclusive as the name implies
- `TrackCuesV2.modify_entries` only deletes the v1 tag once the callback actually returns a change
- Beatgrid analysis: the downbeat window offset is correct near the track start, and confidence no longer goes negative for tempos far from 120
- Various error-throwing improvements: clear errors instead of crashes or corrupt writes for degenerate beatgrid markers, cue dumps without a trailing Color entry, and cue CLIs run on tracks with no cue tag yet

## [4.0.2] - 2026-08-17

- Deep copy `DEFAULT_ENTRIES` when creating a crate whose file does not exist, so instances no longer share the class-level nested sublists

## [4.0.1] - 2026-02-27

- Misc. Beatgrid and Cues fixes.

## [4.0.0] - 2026-02-27

- Significant refactor to track cues: more readable classes, pass whole track cue information to modifier function

## [3.8.2] - 2026-02-27

- Add `serato_snap_cues_v2` entry point

## [3.7.1] - 2026-02-26

- Rename `get_serato_crate_files` to `get_crate_files`, check file extension

## [3.7.0] - 2026-01-20

- `get_tracks` to bin_file

## [3.6.1] - 2025-10-28

- bugfix

## [3.5.3] - 2025-08-19

- Smart crate add rule improvements

## [3.4.3] - 2025-08-19

- Convert smartcrate rules from objects to enums

## [3.4.0] - 2025-06-11

- Modify smartcrate rules
- Add `serato_smartcrate` and `serato_crate` entry points

## [1.5.1] - 2025-04-10

- Initial publish (pyproject.toml added). Serato library and track metadata modification.
