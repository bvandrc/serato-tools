# Changelog

Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [5.2.0] - 2026-11-03

- Add `Library`, which renames or removes track files and updates the database, crates, and smart crates to match, so the track isn't left missing in Serato
  - It also speeds up an app that makes many library changes: each file is parsed only once, the first time it's needed, then kept for every later change. Use `library.database` for other database changes too, so they share that one parse
  - `DatabaseV2.rename_track_file` is deprecated in favor of `Library.rename_track_file`, and will be removed in the next major version. It now also updates smart crates, and looks for crates next to the database instead of in the default `_Serato_` folder
- Fix track paths resolving to a broken path on macOS and Linux
- Fix: `pip install serato-tools` no longer installs the optional deps (about 430 MB): they're only installed by the extra whose feature needs them, as the README always described
  - **If you use track tags (cues, beatgrid, waveform, etc.), the beatgrid analysis, or waveform drawing, install with the matching extra**, e.g. `pip install "serato-tools[track_tags]"`, or `pip install "serato-tools[all]"` for everything
  - `waveform_drawing` and `beatgrid_analysis` now also install `mutagen`, since they read the track's tags through it
- Fix the `serato_snap_cues_v2` command failing with `ImportError: cannot import name 'main'`
- Fix `TrackCuesV2.CueColors.LIMEGREEN3`, which held seafoam's `#00CC88` instead of `#00CC44`, so setting a cue to it gave it the wrong color, and `SEAFOAM` was missing when iterating over `CueColors`
- Add the MIT `LICENSE` file the package metadata already declared, with the notices of the projects it's derived from

## [5.1.2] - 2026-11-03

- Fix the README's examples, which had drifted from the current API, and add a table of contents
- Add a changelog link to the project's PyPI page

## [5.1.1] - 2026-11-03

- Printing or JSON-dumping a large database is faster: field display names are now looked up in a cached map
- Much faster USB export: Now scans each source directory once for `.serato-stems` files instead of globbing per track
  - Fixes a track name containing glob characters like `[` breaking the stem lookup
- Misc. edge-case fixes and clearer errors for cues, cue snapping, and beatgrids
- The tag classes' stored bytes (`SeratoTag.raw_data`) are now internal: the deprecated read-only `raw_data` getter will be removed in the next major version — parse, modify, and serialize through each tag's own methods instead
- Fix the USB export writing a corrupted crate order file on every export
- Fix smart crate rules: a rule's value is now stored in the value field its comparison expects, like Serato does — integer-comparison values set from the CLI were stored as text, and changing a rule's value type left both value fields in the rule

## [5.1.0] - 2026-11-03

- Adding tracks to a crate, `remove_duplicates`, and the USB export dedupe are much faster on a large library
- Add `add_tracks` and `remove_tracks` for batch changes in one pass; `add_track` and `remove_track` are deprecated in their favor, and will be removed in the next major version

## [5.0.2] - 2026-11-03

- `modify` on a database or regular crate now rejects smart crate rule fields, which moved from the shared `Fields` enum to the new `SmartCrate.RuleFields`

## [5.0.1] - 2026-11-03

- Fix smart crate rules with a value of `0` or empty text being read as having no value

## [5.0.0] - 2026-11-02

- Breaking: remove `raw_data` from databases and crates, deprecated in 4.1.0. Use `to_bytes()` instead
- Breaking: the `TrackCuesV2` and `TrackCuesV1` entry classes' `load()` and `dump()` are now internal. Read and change entries through `TrackCuesV2.modify_entries` (or a tag's `entries`), then `save()`

## [4.1.0] - 2026-11-02

- Editing a database or crate is now much faster
  - `raw_data` is now deprecated in favor of the new `to_bytes()`, and will be removed in 5.0
- `modify` is now much faster
  - Even faster when every rule is limited to certain `files`, such as when editing a single track
  - Add `files` parameter to `modify_tracks` to only pass the given tracks to `func`
- `modify`, `modify_tracks`, `change_track_path`, `filter_tracks`, `remove_track`, and `remove_duplicates` now return whether anything changed
- `modify_and_save`, `find_missing`, and `DatabaseV2.rename_track_file` now skip saving files that didn't change
- Loading a JSON file with an invalid value now raises an error right away instead of on save, and a failed save no longer leaves the file empty

## [4.0.4] - 2026-11-01

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

## [3.7.0] - 2026-01-23

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

## [1.5.1] - 2025-04-11

- Initial publish (pyproject.toml added). Serato library and track metadata modification.
