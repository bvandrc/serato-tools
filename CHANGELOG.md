# Changelog

Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [5.0.3] - 2026-11-03

- Adding tracks to a crate, `remove_duplicates`, and the USB export dedupe no longer re-scan a list per track, which makes them much faster on a large library

## [5.0.2] - 2026-11-03

- `modify` on a database or regular crate now rejects smart crate rule fields, which moved from the shared `Fields` enum to the new `SmartCrate.RuleFields`

## [5.0.1] - 2026-11-03

- Fix smart crate rules with a value of `0` or empty text being read as having no value

## [5.0.0] - 2026-11-02

- Breaking: remove `raw_data` from databases and crates, deprecated in 4.1.0. Use `to_bytes()` instead
- Breaking: the `TrackCuesV2` and `TrackCuesV1` entry classes' `load()` and `dump()` are now internal. Read and change entries through `TrackCuesV2.modify_entries` (or a tag's `entries`), then `save()`

## [4.1.0] - 2026-11-01

- Editing a database or crate is now much faster
  - `raw_data` is now deprecated in favor of the new `to_bytes()`, and will be removed in 5.0
- `modify` is now much faster
  - Even faster when every rule is limited to certain `files`, such as when editing a single track
  - Add `files` parameter to `modify_tracks` to only pass the given tracks to `func`
- `modify`, `modify_tracks`, `change_track_path`, `filter_tracks`, `remove_track`, and `remove_duplicates` now return whether anything changed
- `modify_and_save`, `find_missing`, and `DatabaseV2.rename_track_file` now skip saving files that didn't change
- Loading a JSON file with an invalid value now raises an error right away instead of on save, and a failed save no longer leaves the file empty

## [4.0.4] - 2026-10-31

- `modify_tracks` (and so `modify()`) no longer re-encodes the file when no track changed

## [4.0.3] - 2026-10-31

- `DatabaseV2.rename_track_file` only rewrites crates that contain the track, instead of every crate
- Fix `get_full_path` dropping the drive from a path that has one, so it resolved against the current drive instead

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
