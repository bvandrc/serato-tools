# Changelog

Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [4.1.0] - 2026-10-02

- `TrackGain` now reads and writes the `RVA2:SeratoGain` ID3 frame Serato actually uses; it previously read nothing and crashed on write
- `SeratoTag.delete()` followed by `save()` now persists the deletion instead of silently re-adding the deleted tag
- USB export writes `neworder.pref` with line breaks again instead of collapsing it to one line, raises when the destination drive doesn't exist, and no longer skips the export when the local order file is missing
- USB export crate matchers are tried as globs first, so glob patterns like `house*` are no longer silently treated as regexes
- `SeratoTrack` raises a clear "unsupported file type" error for non-mp3/aiff paths (and now accepts `.aif`)
- `TrackWaveform` rejects untested tag versions at construction time and its parsed data can be read repeatedly
- A duplicated field inside a database/crate track entry now raises instead of being silently corrupted on round-trip
- Smart crate rules: integer value `0` no longer reads back as `None`, changing a rule's value type replaces the old value field instead of keeping both, and integer comparisons set from the CLI are stored as integers
- `TrackCuesV1` refuses to dump entries without a trailing Color entry (previously wrote a corrupt tag)
- `TrackAutotags` raises a clear error when dumping with unset values instead of `TypeError`
- Cue CLIs no longer crash on tracks that have no cue tag yet
- `DatabaseV2.rename_track_file` no longer silently overwrites an existing destination file on non-Windows systems
- Misc: beatgrid zero-division guards, `write_json` no longer truncates the destination before validating, `modify()` no longer mutates caller's rule dicts, `add_track` re-dumps as documented

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
