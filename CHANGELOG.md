# Changelog

Each release groups its changes by the part of the package they're in. Within each part, **[BREAKING]** changes come first, each with how to upgrade past it.

## [6.0.0] - 2026-11-10

### Database / Crates / Track Tags

- **[BREAKING]** `save()` on the database, crates, and smart crates skips writing when the file hasn't changed, and returns whether it wrote. Saving to another path always writes.
  - **Upgrading:** Pass `force=True` to write anyway.
- **[BREAKING]** `save()` on `TrackCuesV1`, `TrackBeatgrid`, `TrackAutotags`, and `TrackWaveform` skips writing when the tag hasn't changed. Every tag class's `save()` now returns whether it wrote.
  - **Upgrading:** Pass `force=True` to write anyway. If you relied on `save()` to also write other changes to a tagfile you passed in, call `tagfile.save()` when it returns False.
- **[BREAKING]** A malformed database, crate, or tag, or a number out of range for its field, raises only `ValueError`, no longer `AssertionError` or `struct.error`.
  - **Upgrading:** Catch `ValueError`.
- **[BREAKING]** `serato_tools.utils.ui` is renamed `serato_tools.utils.cli`.
  - **Upgrading:** Import from `serato_tools.utils.cli`.

### Library

- **[BREAKING]** `Library.set_db_track_tags` / `set_db_tracks_tags` return a `DbTrackTagsResult` (`database_changed`, `files_written`) rather than a bool.
  - **Upgrading:** Read `.database_changed` where you used the bool; the result itself is always truthy.
- **[BREAKING]** `Library.rename_track_file` returns the paths of the library files it changed, rather than a bool, and raises `FileExistsError` when a different file is at `dest`, rather than returning False.
  - **Upgrading:** Catch `FileExistsError` where you checked for False.
- **[BREAKING]** `Library.set_db_track_tags` / `set_db_tracks_tags` raise only `DataTypeError` for a bad color, no longer `AttributeError`.
  - **Upgrading:** Catch `DataTypeError`.
- **Feature:** `Library.set_db_track_tags` / `set_db_tracks_tags` also set `title`, `artist`, `album`, `genre`, `key`, `grouping`, `publisher`, `composer`, `year`, `remixer`, `track_number`, `disc_number`, and `comment`, in both the file and the database. An empty value removes it.
- **Feature:** Add `Library.save()`, which writes each changed library file and returns their paths.
- **Feature:** Add `Library.batch()`: inside `with library.batch():`, `rename_track_file`, `remove_track_files`, and `set_db_tracks_tags` write each changed database and crate file once, when the block ends, rather than once per call.
- **Feature:** `Library.remove_track_files` returns a `RemoveTrackFilesResult` (`files_deleted`, `library_files_changed`).
- **Feature:** Add `Library.crate_files`, the paths of the library's crates and smart crates, without parsing them.

### Database / Crates

- **[BREAKING]** `DataTypeError` and `DeeplyNestedListError` move from `serato_tools.utils` to `serato_tools.utils.bin_file_base`.
  - **Upgrading:** Import them from `serato_tools.utils.bin_file_base`.
- **[BREAKING]** A database's or crate's `entries` and `version` are now internal.
  - **Upgrading:** Change a file through its methods (`modify_tracks`, `modify`, `add_tracks`, `set_rule`, ...), and read it through `get_entries`, `get_tracks`, or `to_json_object`. The version is the `vrsn` entry.
- **[BREAKING]** A file with a number field of the wrong size, or with no version entry (such as an empty file), raises `ValueError`, rather than `struct.error` or `AttributeError`.
  - **Upgrading:** Catch `ValueError`.
- **[BREAKING] Removed:** The deprecated `DatabaseV2.rename_track_file`, `add_track`, `remove_track`, a track's `get_full_path()`, and `get_entries_filtered`.
  - **Upgrading:** Use `Library.rename_track_file`, `add_tracks`, `remove_tracks`, `full_path`, and `get_entries(track_matcher)`.
- **[BREAKING] Removed (CLI):** `serato_smartcrate`'s `--set_rules`.
  - **Upgrading:** Pass the rule options directly, without it.
- **Feature (CLI):** `serato_smartcrate` takes each rule field as its own option, e.g. `serato_smartcrate Dubstep.scrate --grouping str_is UNTAGGED --year DELETE` (`--help` lists them), and checks every option before changing any crate.
- **Feature:** A track's or smart crate rule's `set_value` raises `DataTypeError` for a value of the wrong type, and `ValueError` for an out-of-range number, when it's set rather than on save. `modify_tracks` and `modify` check the tracks they change too.
- **Feature:** A smart crate rule's `comparison` is typed `str` and its `field` `int`.

### Track Tags

- **[BREAKING]** `TrackBeatgrid.find_nearest_beat` raises `NoBeatgridError` without a beatgrid, rather than returning None.
  - **Upgrading:** Catch `NoBeatgridError` where you checked for None.
- **[BREAKING] Removed:** The tag classes' `raw_data`, `TrackCuesV2.modified`, and the `SeratoTrack` and `SeratoTag` names.
  - **Upgrading:** Use each tag's own methods, `has_changed`, and `ID3FileTag` / `SeratoGeobTag`.
- **[BREAKING] Removed:** `TrackCuesV2`'s methods that read the beatgrid from its own file: `snap_positions_to_beat`, `snap_positions_to_beat_rule`, `get_snapped_beat_ms`, and `get_beat_position`.
  - **Upgrading:**
    - To snap cues, use `Track.snap_cues_to_beats`, or `TrackCuesV2.snap_cues_to_beats(beatgrid, ...)`. Both return the moves rather than printing them, and have no rule form: snap before or after your other edits.
    - For `get_snapped_beat_ms`, use `TrackBeatgrid.get_snapped_position`.
    - For `get_beat_position(entry)`, use `beatgrid.get_beat_position(entry.position)`.
- **[BREAKING] Removed:** The `FIELDS` tuple on `TrackCuesV2`'s entry classes.
  - **Upgrading:** Use `dataclasses.fields`, e.g. `[f.name for f in dataclasses.fields(TrackCuesV2.CueEntry)]`.
- **[BREAKING] Removed (CLI):** The `-e` / `--edit` mode of `serato_snap_cues_v2`, `python -m serato_tools.track_cues_v1`, and `python -m serato_tools.track_autotags`, and `TrackCuesV2.parse_entries_file`, which read its text.
  - **Upgrading:** Change a tag through its class's methods, such as `TrackCuesV2.modify_entries` or `TrackAutotags.set`.
- **Feature:** Add `TrackTextFrames` (`serato_tools.track_text_frames`) and `Track.text_frames`, which read and set a track's ID3 text frames, and its comment as Serato does. `TrackTextFrames.Fields` names the frames Serato shows (`Fields.TITLE`, ...), and `""` removes a frame.
- **Feature:** Add `Track.snap_cues_to_beats(tolerance_beats)` and `TrackCuesV2.snap_cues_to_beats(beatgrid, tolerance_beats)`, which snap cues to the beatgrid in memory and return each move as a `SnappedCue`, and `TrackBeatgrid.get_snapped_position` for a single position.
- **Feature (CLI):** `serato_snap_cues_v2 --snap_cues` says which cue each move was for, and which tag a track is missing.
- **Deprecated:** Passing `delete_tags_v1` to an edit method, rather than to `save()`, stays deprecated until a future major release.

### USB Export

- **[BREAKING]** `get_crate_files` and `serato_usb_export --crate_matcher` match a pattern against the crate's name without its `.crate` or `.scrate` extension.
  - **Upgrading:** Drop the extension: `"house*"` rather than `"house*.crate"`.

## [5.8.0] - 2026-11-18

### Database / Crates

- **Feature:** `get_entries` takes an optional `track_matcher` regex, giving only the tracks whose path it matches, ignoring case.
  - **Deprecated:** `get_entries_filtered(track_matcher)`, in favor of `get_entries(track_matcher)`.
- **Feature:** Add a track's `full_path` property.
  - **Deprecated:** A track's `get_full_path()`, in favor of `full_path`.
- **Feature:** `SmartCrate.delete_rule` returns whether there was a rule to remove.
- **Fix:** A track's `relpath`, and a smart crate rule's `comparison`, `field`, and `value`, now reflect changes made through `set_value` or `remove_field`, so a `modify()` rule after a path change gets the new path. They're now read-only, since assigning one never changed the file.
- **Fix:** Setting a track's path to a value that isn't text, through `set_value`, raises `DataTypeError`.
- **Fix:** `modify_tracks` and `modify` change nothing when `func` raises, rather than keeping the changes made before it.
- **Fix:** A crate's `add_tracks`, `add_tracks_from_dir`, and `remove_duplicates` treat paths differing only in case as one track, as `remove_tracks` and `modify` do.

### Track Tags

- **Feature:** `TrackBeatgrid`'s markers, `Footer`, and `BeatPoint` are typed `NamedTuple`s, so type checkers know their fields.
- **Fix:** `TrackBeatgrid.analyze_and_write` keeps the old grid when the analysis gives one Serato wouldn't write.
- **Fix (CLI):** `serato_snap_cues_v2 -e` keeps entries you left unchanged when the editor fails or the content is invalid, and works on Windows.
- **Fix (CLI):** `serato_tagdump` says a file has no tags, rather than giving a traceback.

### Library

- **Fix:** `Library.set_db_track_tags` / `set_db_tracks_tags` raise `DataTypeError` for a color that isn't a `TrackCuesV2.TrackColors`, before changing any file. It's still an `AttributeError` too.
  - **Deprecated:** Catching it as `AttributeError`.

## [5.7.0] - 2026-11-15

### Database / Crates / Track Tags

- **Feature:** A malformed database, crate, or tag raises `ValueError` saying what's wrong. It's still an `AssertionError` too.
- **Feature:** A number out of range for its field raises `ValueError` naming the field. It's still a `struct.error` too.
- **Feature:** Errors that were a bare `Exception` are now a more specific `ValueError`, `TypeError`, `FileNotFoundError`, or `ImportError`.
- **Deprecated:** Catching these as `AssertionError` or `struct.error`; catch `ValueError`.

### USB Export

- **Fix:** When tracks share a filename, USB export keeps the database entry of the one it copies, rather than possibly another's.
- **Fix:** USB export copies only a track's own stems file: `B Extended.serato-stems` beside `B.mp3` stopped the export partway. NOTE: Stems over USB are still untested.
- **Fix:** USB export writes each smart crate as a regular crate of its tracks, which `Crate` can open.

### Database / Crates

- **Feature:** Add `SmartCrate.to_regular_crate(file)`, a regular crate of a smart crate's tracks, sort, and columns.
- **Feature:** Add `SeratoBinFile.check_value(field, value)`, which raises for a value the field can't hold.
- **Feature:** Methods that took a list of track paths or rules take any collection, such as a `set` or `tuple`.
- **Fix:** `remove_tracks` and `Library.remove_track_files` match a track's path whatever its case.
- **Fix:** `add_tracks_from_dir` skips subfolders and hidden files, such as `.DS_Store`.

### Track Tags

- **Feature:** Add `GeobKeys`, each Serato tag's GEOB key.
- **Feature:** A track missing a needed tag, such as one Serato hasn't analyzed, raises `NoCuesError`, `NoBeatgridError`, or `NoWaveformError` (`MissingTagError`s, in `serato_tools.utils.track_tags`, and still `ValueError`s).
- **Feature (CLI):** The tag CLIs read a file of the tag's own bytes, such as one `serato_tagdump` writes.
- **Feature (CLI):** `serato_beatgrid` says which tag is missing, rather than giving a traceback.
- **Fix:** A track's Serato tags can be read and saved in a file whose ID3 tags have no frames.
- **Fix:** After `TrackBeatgrid.analyze_and_write`, `find_nearest_beat` uses the new grid.

### Library

- **Fix:** `Library.set_db_track_tags` / `set_db_tracks_tags` raise for a value the database can't hold before changing any file.

## [5.6.1] - 2026-11-10

### Database / Crates

- **Feature:** Add a track's `remove_field(field)`, which removes a field and returns whether it was there.
- **Fix:** Setting a track's field to `""` removes it, as Serato does, rather than storing it empty.

### Documentation

- **Docs:** Add docstrings to each source module, and to the classes and functions whose use wasn't clear.

## [5.6.0] - 2026-11-09

### Database / Crates / Track Tags

- **Feature:** Add a read-only `has_changed` to the database, crates, smart crates, each tag class, and `Track`: whether saving would write a change.
  - NOTE: For the database and crates, each check serializes the file, which takes time over many files.

### Track Tags

- **[BREAKING]** Any write of `Serato Markers2` deletes `Serato Markers_` by default, including through the `serato_snap_cues_v2 --edit` CLI, a forced save, or deleting `Serato Markers2`.
  - **Upgrading:** Pass `delete_tags_v1=False` to `save()` where you need `Serato Markers_` kept.
- **[BREAKING] Deprecated:** `TrackCuesV2.modified`, in favor of `has_changed`. It's now read-only.
  - **Upgrading:** Read `has_changed`; assigning `modified` now raises.
- **Feature:** `TrackCuesV2.save()` and `Track.save()` take `delete_tags_v1` (default True), which deletes the legacy `Serato Markers_` tag, since a stale one hides the change in Serato. `Library.set_db_track_tags` and `set_db_tracks_tags` pass theirs to it.
- **Fix:** `TrackCuesV2.save()` no longer loses a change when an edit that changed nothing follows it.
- **Fix:** `TrackCuesV1` serializes a tag with an unset cue or loop position, as every one Serato writes has.
- **Fix:** `TrackCuesV2` deletes `Serato Markers_` only when it writes a change to `Serato Markers2`, so an edit that changed nothing can't delete it through another tag's save.
- **Deprecated:** Passing `delete_tags_v1` to `modify_entries`, `set_track_color`, or `set_beatgrid_locked` (on `TrackCuesV2` or `Track`), in favor of passing it to `save()`.

## [5.5.0] - 2026-11-06

### Library

- **Feature:** Add `Library.set_db_track_tags` and `set_db_tracks_tags`, which set a track's color and beatgrid lock in both its tags and the database, so Serato shows it without a rescan. ID3 files (.mp3, .aiff, .aif) only.
- **Feature:** `Library.rename_track_file` returns whether it renamed the file (False when a different file is at `dest`).

### Database / Crates

- **Feature:** Add `ModifyFunc` (e.g. `DatabaseV2.ModifyFunc`), the type of a `ModifyRule`'s `func`.

### Track Cues

- **[BREAKING] Fix:** `TrackCuesV2` raises ValueError for a color, BPM lock, cue, or loop entry unlike any Serato writes, including a cue past 8, rather than risk rewriting it.
  - **Upgrading:** Catch `ValueError` when reading tags you don't control, and remove any cue past 8 before saving.
- **Fix:** Changing a track's cues keeps its BPM lock before its flips, as Serato orders them.
- **Fix:** `TrackCuesV2` writes `Serato Markers2` byte for byte as Serato does, including its base64 ending and its size.
- **Fix:** A saved loop's `color` (`TrackCuesV2.LoopEntry.color`) reads and sets the right bytes.
- **Fix:** `CueColors.LIMEGREEN3` gives lime green, not sea foam.

## [5.4.1] - 2026-11-04

### Track Tags

- **Fix:** `TrackCuesV2.set_track_color` and `set_beatgrid_locked` work on a track whose tags don't have a color or lock yet.

## [5.4.0] - 2026-11-04

### Track Tags

- **Feature:** Add `Track` (`serato_tools.track`), which reads a track's Serato tags from one open file and saves all their changes in one write.
- **Feature:** Add `TrackCuesV2.set_beatgrid_locked`.
- **Fix:** Updates to `TrackGain` setting, saving, and deleting.

## [5.3.2] - 2026-11-04

### Packaging

- **Fix:** Type checkers (pyright, mypy, etc.) now see the package's type hints: it ships the `py.typed` marker.

## [5.3.1] - 2026-11-04

### Track Cues

- **Fix:** Cue snapping no longer moves almost every cue by 1 ms: the default `min_ms_change` is now 2, so Serato's usual 1 ms gap is left alone, and passing less than 2 warns.

## [5.3.0] - 2026-11-03

### Database / Crates

- **Feature:** Name more database track fields, for printing and `DatabaseV2.modify`: `COMMENT`, `REMIXER`, `TRACK_NUMBER`, `DISC_NUMBER`, `PLAY_COUNT`, `COLOR` (as `0xRRGGBB`), `CORRUPT_REASON`, `READ_ONLY`, and `OVERVIEW_BUILT`, plus `SmartCrate.RuleFields.SETTING_VALUE`.
- **Feature:** Add `DatabaseV2.get_corrupt_tracks`, and the database CLI's `--list_corrupt`, which list the tracks Serato marked corrupt, with its reason.

### Track Gain Tags

- **[BREAKING] Fix:** `TrackGain` reads and writes Serato's gain, its `RVA2:SeratoGain` frame; before, it never read or wrote anything.
  - **Upgrading:** Serato writes the frame on most analyzed tracks, so `gain` is now `0.0` rather than `None` for them: check code that deletes gain when it isn't `None`.

### USB Export

- **Fix:** A crate matcher like `house*` is tried as a glob before a regex, so it no longer also matches `housing`.
  - Also, files that aren't crates, such as `.DS_Store`, are ignored, and a missing `Subcrates` or `SmartCrates` folder no longer errors.

## [5.2.0] - 2026-11-03

### Packaging

- **[BREAKING] Fix:** `pip install serato-tools` no longer installs the optional deps (about 430 MB), only the extras do. `waveform_drawing` and `beatgrid_analysis` now also install `mutagen`.
  - **Upgrading:** Install the extra for what you use, e.g. `pip install "serato-tools[track_tags]"`, or `"serato-tools[all]"` for everything.
- **Docs:** Add the MIT `LICENSE` file, with the notices of the projects it's derived from.

### Library

- **Feature:** Add `Library`, which renames or removes track files and updates the database, crates, and smart crates to match.
  - **Performance:** Each file is parsed once, on first use, and kept, so many changes are faster. Use `library.database` for other database changes to share it.

### Database / Crates

- **Fix:** Track paths resolve correctly on macOS and Linux.
- **Deprecated:** `DatabaseV2.rename_track_file`, in favor of `Library.rename_track_file`. It now also updates smart crates, and finds crates next to the database.

### Track Cues

- **Fix:** The `serato_snap_cues_v2` command no longer fails with `ImportError: cannot import name 'main'`.

## [5.1.2] - 2026-11-03

### Documentation

- **Docs:** Fix the README's examples, which had drifted from the API, and add a table of contents.
- **Docs:** Add a changelog link to the PyPI page.

## [5.1.1] - 2026-11-03

### USB Export

- **Performance:** Much faster USB export: each source folder is scanned once for stems, not once per track.
  - **Fix:** A track name containing glob characters like `[` no longer breaks the stem lookup.
- **Fix:** USB export no longer writes a corrupted crate order file.

### Database / Crates

- **Performance:** Printing or JSON-dumping a large database is faster.
- **Fix:** A smart crate rule's value is stored in the field its comparison expects, as Serato does, and changing its type no longer leaves both value fields set.

### Track Tags

- **Fix:** Misc. edge-case fixes and clearer errors for cues, cue snapping, and beatgrids.
- **Deprecated:** The tag classes' `raw_data`, now internal. Parse, modify, and serialize through each tag's own methods.

## [5.1.0] - 2026-11-03

### Database / Crates

- **Feature:** Add `add_tracks` and `remove_tracks` for batch changes in one pass.
- **Performance:** Adding tracks to a crate, `remove_duplicates`, and the USB export dedupe are much faster on a large library.
- **Deprecated:** `add_track` and `remove_track` are deprecated in favor of `add_tracks` and `remove_tracks`, and will be removed in the next major version.

## [5.0.2] - 2026-11-03

### Database / Crates

- **[BREAKING]** `modify` on a database or regular crate now rejects smart crate rule fields, which moved from the shared `Fields` enum to the new `SmartCrate.RuleFields`.
  - **Upgrading:** Name a smart crate rule field through `SmartCrate.RuleFields` rather than `Fields`.

### Smart Crates

- **Fix:** Fix smart crate rules with a value of `0` or empty text being read as having no value.

## [5.0.0] - 2026-11-02

### Database / Crates

- **[BREAKING] Removed:** `raw_data` on databases and crates, deprecated in 4.1.0.
  - **Upgrading:** Use `to_bytes()`.

### Track Cues

- **[BREAKING]** The `TrackCuesV2` and `TrackCuesV1` entry classes' `load()` and `dump()` are now internal.
  - **Upgrading:** Read and change entries through `TrackCuesV2.modify_entries` (or a tag's `entries`), then `save()`.

## [4.1.0] - 2026-11-02

### Database / Crates

- **Performance:** Editing a database or crate is now much faster.
- **Performance:** `modify` is now much faster, and even faster when every rule is limited to certain `files`, such as when editing a single track.
- **Feature:** Add a `files` parameter to `modify_tracks`, to only pass the given tracks to `func`.
- **Feature:** `modify`, `modify_tracks`, `change_track_path`, `filter_tracks`, `remove_track`, and `remove_duplicates` now return whether anything changed.
- **Fix:** `modify_and_save`, `find_missing`, and `DatabaseV2.rename_track_file` now skip saving files that didn't change.
- **Fix:** Loading a JSON file with an invalid value now raises an error right away instead of on save, and a failed save no longer leaves the file empty.
- **Deprecated:** `raw_data` is deprecated in favor of the new `to_bytes()`, and will be removed in 5.0.

## [4.0.4] - 2026-11-01

### Database / Crates

- **Fix:** `modify_tracks` (and so `modify()`) no longer re-encodes the file when no track changed.

## [4.0.3] - 2026-10-31

### Database / Crates

- **Fix:** `DatabaseV2.rename_track_file` only rewrites crates that contain the track, instead of every crate.
- **Fix:** Fix `get_full_path` dropping the drive from a path that has one, so it resolved against the current drive instead.

## [4.0.2] - 2026-08-17

### Database / Crates

- **Fix:** Deep copy `DEFAULT_ENTRIES` when creating a crate whose file does not exist, so instances no longer share the class-level nested sublists.

## [4.0.1] - 2026-02-27

### Track Tags

- **Fix:** Misc. beatgrid and cues fixes.

## [4.0.0] - 2026-02-27

### Track Cues

- **[BREAKING]** Significant refactor to track cues: more readable classes, pass whole track cue information to modifier function.
  - **Upgrading:** `TrackCuesV2.modify_entries` takes a callback rather than a dict of rules (`EntryModifyRules`): it's passed the track's cues as a `TrackCuesInfo`, and returns a changed one (e.g. through `dataclasses.replace`), or None for no change.

## [3.8.2] - 2026-02-27

### Track Cues

- **Feature:** Add `serato_snap_cues_v2` entry point.

## [3.7.1] - 2026-02-26

### Database / Crates

- **[BREAKING]** Rename `get_serato_crate_files` to `get_crate_files`, check file extension.
  - **Upgrading:** Call `get_crate_files` (e.g. `Crate.get_crate_files()`).

## [3.7.0] - 2026-01-23

### Database / Crates

- **Feature:** Add `get_tracks` to the database and crates.

## [3.6.2] - 2025-12-06

### Database / Crates

- **[BREAKING]** Renames: a database's or crate's `data` is now `entries` (and a subclass's `DEFAULT_DATA` is `DEFAULT_ENTRIES`), a track's `path` is `relpath`, `StructCls` is `EntryListCls` (its `to_struct()` is `to_entries()`), `format_filepath` is `get_relative_path`, and `DeeplyNestedStructError` is `DeeplyNestedListError`.
  - **Upgrading:** Use the new names.
- **[BREAKING]** `to_entries(track_matcher)` is split into `get_entries()` and `get_entries_filtered(track_matcher)`, a crate's `list_dir()`, which printed the crate files, is replaced by `get_serato_crate_files()`, which returns them, and a track's `set_path` takes a full path.
  - **Upgrading:** Call the new methods, print the crate files yourself, and pass `set_path` the track's full path.
- **Feature:** The database and crates refuse a file of a version that hasn't been tested, so one this package may misparse can't be written back.
- **Feature:** `modify` and `modify_and_save` now work on crates and smart crates, `change_track_path(src, dest)` is added, and `DatabaseV2.rename_track_file` also updates the crates.
- **Feature:** Add `find_missing()` to the database and crates, which asks for the new location of each track whose file is missing.
- **Feature:** The database and crates can be written to and loaded from JSON.

### USB Export

- **Fix:** USB export writes each track's path in the crates relative to the drive, and with forward slashes in the database. Before, the crates' paths included the drive's mount point on macOS and Linux, and the database's used backslashes on Windows.

### Packaging

- **Feature:** `mutagen`, `numpy`, `librosa`, and `pillow` are now installed with the package, rather than only with its extras.

## [3.5.3] - 2025-08-19

### Smart Crates

- **[BREAKING]** `SmartCrate.modify_rules(func)` is replaced by `set_rule(field, comparison, value)` and `delete_rule(field)`.
  - **Upgrading:** Call `set_rule` and `delete_rule`.

## [3.4.3] - 2025-08-19

### Database / Crates

- **[BREAKING] Removed (CLI):** The crate and smart crate CLIs' `-o` / `--output` option, which saved the crate to another file.
  - **Upgrading:** Call the crate's `save(file)`.
- **Feature (CLI):** Add the `serato_crate` and `serato_smartcrate` commands, which take a crate file, a folder of crates, or `--all`.

### Smart Crates

- **[BREAKING]** Smart crate rule fields and comparisons are now the `SmartCrate.RuleField` and `SmartCrate.RuleComparison` enums, rather than the `RULE_FIELD` and `RULE_COMPARISON` dicts.
  - **Upgrading:** Use e.g. `SmartCrate.RuleField.GENRE` for `SmartCrate.RULE_FIELD["genre"]`.
- **Feature:** Add `set_field` and `set_comparison` to a smart crate's `Rule`, and its `set_value` takes the value alone.
- **Feature (CLI):** `serato_smartcrate --set_rules` sets the value of the rules on each field it's given, e.g. `--set_rules --grouping UNTAGGED`.
- **Fix:** Fix reading a smart crate rule that doesn't hold every kind of value.

## [3.3.0] - 2025-06-11

### Smart Crates

- **Feature:** Add `SmartCrate.modify_rules(func)`, which passes each rule to `func` as a `SmartCrate.Rule` and keeps the rule it returns.
  - NOTE: In this version, it raises `AttributeError` for every rule Serato writes. 3.4.3 fixes it.

## [3.2.10] - 2025-06-11

### USB Export

- **Feature:** Add USB export: the `serato_usb_export` command copies the crates and smart crates you choose, and their tracks, to a drive, copying only the track files that changed since the last export, with their stems.
  - NOTE: It replaces the drive's existing `_Serato_` folder, crates included, though not its track files.

### Database / Crates

- **[BREAKING]** Renames: `SERATO_FOLDER` is now `SERATO_DIR`, a crate's `FOLDER` (a full path) is replaced by `DIR` (the folder's name), and a crate's `tracks()`, `list_folder()`, and `add_tracks_from_folder()` are now `get_track_paths()`, `list_dir()`, and `add_tracks_from_dir()`. A crate's `track_dir` is removed.
  - **Upgrading:** Use the new names, and `os.path.join(SERATO_DIR, Crate.DIR)` for a crate folder's path.
- **[BREAKING]** `str()` of a crate gives its entries rather than its tracks, and the crate CLIs print them by default, without `-d`.
  - **Upgrading:** Use `get_track_paths()`, or the CLI's `-l`, for the tracks.
- **Feature:** Add `get_track_paths()`, `modify_tracks(func)`, `filter_tracks(func)`, `remove_track(filepath)`, and `remove_duplicates()` to the database, crates, and smart crates.
- **Fix:** Fix creating and saving a crate whose file doesn't exist yet.

### Track Tags

- **Fix (CLI):** Fix the beatgrid analysis command, which failed to start, now named `serato_analyze_beatgrid`.

## [3.1.0] - 2025-05-14

### Database / Crates

- **[BREAKING]** `DatabaseV2`'s `filepath` argument is renamed `file`, and its `data` is a list rather than a generator that could be read once.
  - **Upgrading:** Pass `file=`, or the path positionally.
- **Fix:** Fix saving a smart crate, the default Serato folder on macOS and Linux, and `DatabaseV2.modify` skipping fields stored before the track's path.

## [3.0.1] - 2025-05-14

### Database / Crates

- **[BREAKING]** Field names are now each class's `Fields` StrEnum (e.g. `DatabaseV2.Fields.FILE_PATH` for `"pfil"`), replacing `FIELDNAMES`, `FIELDNAME_KEYS`, and `TRACK_FIELD`, and a database's entries no longer hold each field's length.
  - **Upgrading:** Use `Fields`, and unpack one fewer value from the database's entries.
- **Feature:** Add `DatabaseV2.remove_duplicates()`.

### Track Cues

- **[BREAKING]** `TrackCuesV2.CUE_COLORS` and `TRACK_COLORS` are now the `CueColors` and `TrackColors` enums, with uppercase names, which `set_track_color` takes and `color` rules are given.
  - **Upgrading:** Use e.g. `TrackCuesV2.TrackColors.PINK` for `TRACK_COLORS["pink"]` or `"pink"`.

## [2.6.0] - 2025-05-14

### Database / Crates

- **Feature:** Add `list_folder()` to `Crate` and `SmartCrate`, which prints the library's crates, and `SERATO_FOLDER`, the default `_Serato_` folder.

## [2.5.0] - 2025-05-14

### Packaging

- **[BREAKING]** Requires Python 3.12 or later.
  - **Upgrading:** Upgrade to Python 3.12 or later.

### Database / Crates / Track Tags

- **[BREAKING]** Renames: `to_dicts()` is now `to_entries()`, which yields tuples, `Crate.include_tracks_from_folder` is `add_tracks_from_folder`, `SeratoBinDb` is `SeratoBinFile` (in `serato_tools.utils.bin_file_base`), and the type aliases drop their `Type` suffix (e.g. `ValueType` is `Value`).
  - **Upgrading:** Use the new names.

### Smart Crates

- **Feature:** Add `SmartCrate` (`serato_tools.smart_crate`), which reads and saves a smart crate, with a CLI that prints it.

## [2.4.0] - 2025-05-13

### Packaging

- **Fix:** Fix importing the package on Python before 3.13.

## [2.3.1] - 2025-05-13

### Database / Crates

- **[BREAKING]** Renames: `DatabaseV2.write_file` and `modify_file` are now `save` and `modify_and_save`, `Crate.save_to_file` is `save`, and a crate's `path`, `filename`, and `track_path` are `dir`, `filepath`, and `track_dir`. `DatabaseV2.parse()` and `Crate.load_from_file()` are removed, since each reads its file when constructed.
  - **Upgrading:** Use the new names, and construct a new object to reread a file.
- **[BREAKING]** `Crate.add_track` takes a track's full path, and stores it as Serato does.
  - **Upgrading:** Pass the full path.
- **Fix:** Fix track paths on macOS and Linux.

## [2.2.1] - 2025-05-13

### Database / Crates / Track Tags

- **[BREAKING] Removed:** The `print_changes` arguments, and `print_data()` on the database and crates. Changes are logged to the `serato-tools` logger instead.
  - **Upgrading:** Drop `print_changes`, and configure logging (e.g. `logging.basicConfig(level=logging.INFO)`) to see changes.

### Track Tags

- **Feature:** Add `TrackCuesV2.get_track_color()`.
- **Feature:** The tag classes open `.aiff` files too.

## [2.1.0] - 2025-05-08

### Track Tags

- **Feature:** Add `delete()` to each tag class, which removes the tag without saving the file.

## [2.0.0] - 2025-05-08

### Track Tags

- **[BREAKING]** Each tag module's functions are replaced by a class (`TrackCuesV2`, `TrackCuesV1`, `TrackBeatgrid`, `TrackAutotags`, `TrackWaveform`, and `TrackGain`), constructed from a file or the tag's bytes, and the module's constants move onto it.
  - **Upgrading:** Use the tag's class, e.g. `TrackCuesV2(file).modify_entries(rules)` and then `save()` for `modify_file_entries(file, rules)`.
- **[BREAKING] (CLI)** `python -m serato_tools.track_beatgrid` prints the beatgrid, and analyzes the track only with `--analyze`.
  - **Upgrading:** Pass `--analyze`.
- **Fix:** Fix `is_beatgrid_locked` always returning None.

## [1.18.0] - 2025-04-30

### Database / Crates / Track Cues

- **[BREAKING]** `DataTypeError` moves to `serato_tools.utils`, and cue rules raise it for a value of the wrong type.
  - **Upgrading:** Import it from `serato_tools.utils`.

## [1.17.3] - 2025-04-28

### Packaging

- **[BREAKING]** `mutagen` moves to the new `track_tags` extra.
  - **Upgrading:** Install with `pip install "serato-tools[track_tags]"`.

### Database / Crates

- **[BREAKING]** `DatabaseV2.to_objects()` and `print_items()` are renamed `to_dicts()` and `print_data()`, and `modify_file` rejects two rules on one field.
  - **Upgrading:** Use the new names, and combine a field's rules into one.
- **Feature:** Add `DatabaseV2.rename_track_file(src, dest)`, which renames a track's file and updates its path in the database.
- **Fix:** Fix database text outside Latin-1 being garbled.

### Track Tags

- **[BREAKING]** `serato_tools.utils.tags` is renamed `serato_tools.utils.track_tags`.
  - **Upgrading:** Update the import.

## [1.15.0] - 2025-04-22

### Database

- **[BREAKING]** `serato_tools.database_v2`'s functions move onto a new `DatabaseV2` class.
  - **Upgrading:** Use e.g. `DatabaseV2(file).modify_file(rules)` for `modify_file(rules, file)`.

### Crates

- **[BREAKING]** `Crate.include_tracks_from_folder` keeps the crate's other tracks, unless passed `replace=True`.
  - **Upgrading:** Pass `replace=True` to replace them.

## [1.14.2] - 2025-04-19

### Database / Track Tags

- **[BREAKING]** The `database` and `track` subpackages are removed, and their modules move back to the top of the package.
  - **Upgrading:** Import e.g. `serato_tools.database_v2` and `serato_tools.track_cues_v2`.

### Crates

- **Feature:** Add `Crate` (`serato_tools.crate`), which reads, changes, and saves a crate.

### Track Tags

- **Feature:** Add `modify_file_entries` and `set_track_color` to `track_cues_v2`, which change and save a track's cues or color.
- **Feature:** Add beatgrid analysis (`track_beatgrid.analyze_and_write`, with the `beatgrid_analysis` extra), which writes a beatgrid from the track's detected beats.

## [1.8.1] - 2025-04-11

### Database / Track Tags

- **[BREAKING]** The modules move into `database` and `track` subpackages, and the tag modules are renamed after what they hold (e.g. `serato_markers2` is `track_cues_v2`).
  - **Upgrading:** Import e.g. `serato_tools.database.database_v2` and `serato_tools.track.track_cues_v2`.

## [1.7.0] - 2025-04-11

### Database

- **[BREAKING]** `modify_file` takes `rules` first, and `file` defaults to the library's database.
  - **Upgrading:** Pass `rules` first, or pass both by keyword.

## [1.6.2] - 2025-04-11

### Database

- **Feature:** A `modify_file` rule takes an optional `files` list, to change only those tracks.

## [1.5.2] - 2025-04-11

### Packaging

- **Fix:** Fix the package not being importable as `serato_tools`.

## [1.5.1] - 2025-04-11

### General

- **Feature:** First release on PyPI, for changing Serato's library database and track metadata.

[6.0.0]: https://github.com/bvandrc/serato-tools/compare/v5.8.0...v6.0.0
[5.8.0]: https://github.com/bvandrc/serato-tools/compare/v5.7.0...v5.8.0
[5.7.0]: https://github.com/bvandrc/serato-tools/compare/v5.6.1...v5.7.0
[5.6.1]: https://github.com/bvandrc/serato-tools/compare/v5.6.0...v5.6.1
[5.6.0]: https://github.com/bvandrc/serato-tools/compare/v5.5.0...v5.6.0
[5.5.0]: https://github.com/bvandrc/serato-tools/compare/v5.4.1...v5.5.0
[5.4.1]: https://github.com/bvandrc/serato-tools/compare/v5.4.0...v5.4.1
[5.4.0]: https://github.com/bvandrc/serato-tools/compare/v5.3.2...v5.4.0
[5.3.2]: https://github.com/bvandrc/serato-tools/compare/v5.3.1...v5.3.2
[5.3.1]: https://github.com/bvandrc/serato-tools/compare/v5.3.0...v5.3.1
[5.3.0]: https://github.com/bvandrc/serato-tools/compare/v5.2.0...v5.3.0
[5.2.0]: https://github.com/bvandrc/serato-tools/compare/v5.1.2...v5.2.0
[5.1.2]: https://github.com/bvandrc/serato-tools/compare/v5.1.1...v5.1.2
[5.1.1]: https://github.com/bvandrc/serato-tools/compare/v5.1.0...v5.1.1
[5.1.0]: https://github.com/bvandrc/serato-tools/compare/v5.0.2...v5.1.0
[5.0.2]: https://github.com/bvandrc/serato-tools/compare/v5.0.0...v5.0.2
[5.0.0]: https://github.com/bvandrc/serato-tools/compare/v4.1.0...v5.0.0
[4.1.0]: https://github.com/bvandrc/serato-tools/compare/v4.0.4...v4.1.0
[4.0.4]: https://github.com/bvandrc/serato-tools/compare/v4.0.3...v4.0.4
[4.0.3]: https://github.com/bvandrc/serato-tools/compare/v4.0.2...v4.0.3
[4.0.2]: https://github.com/bvandrc/serato-tools/compare/v4.0.1...v4.0.2
[4.0.1]: https://github.com/bvandrc/serato-tools/compare/v4.0.0...v4.0.1
[4.0.0]: https://github.com/bvandrc/serato-tools/compare/v3.8.2...v4.0.0
[3.8.2]: https://github.com/bvandrc/serato-tools/compare/v3.7.1...v3.8.2
[3.7.1]: https://github.com/bvandrc/serato-tools/compare/v3.7.0...v3.7.1
[3.7.0]: https://github.com/bvandrc/serato-tools/compare/v3.6.2...v3.7.0
[3.6.2]: https://github.com/bvandrc/serato-tools/compare/v3.5.3...v3.6.2
[3.5.3]: https://github.com/bvandrc/serato-tools/compare/v3.4.3...v3.5.3
[3.4.3]: https://github.com/bvandrc/serato-tools/compare/v3.3.0...v3.4.3
[3.3.0]: https://github.com/bvandrc/serato-tools/compare/v3.2.10...v3.3.0
[3.2.10]: https://github.com/bvandrc/serato-tools/compare/v3.1.0...v3.2.10
[3.1.0]: https://github.com/bvandrc/serato-tools/compare/v3.0.1...v3.1.0
[3.0.1]: https://github.com/bvandrc/serato-tools/compare/v2.6.0...v3.0.1
[2.6.0]: https://github.com/bvandrc/serato-tools/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/bvandrc/serato-tools/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/bvandrc/serato-tools/compare/v2.3.1...v2.4.0
[2.3.1]: https://github.com/bvandrc/serato-tools/compare/v2.2.1...v2.3.1
[2.2.1]: https://github.com/bvandrc/serato-tools/compare/v2.1.0...v2.2.1
[2.1.0]: https://github.com/bvandrc/serato-tools/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/bvandrc/serato-tools/compare/v1.18.0...v2.0.0
[1.18.0]: https://github.com/bvandrc/serato-tools/compare/v1.17.3...v1.18.0
[1.17.3]: https://github.com/bvandrc/serato-tools/compare/v1.15.0...v1.17.3
[1.15.0]: https://github.com/bvandrc/serato-tools/compare/v1.14.2...v1.15.0
[1.14.2]: https://github.com/bvandrc/serato-tools/compare/v1.8.1...v1.14.2
[1.8.1]: https://github.com/bvandrc/serato-tools/compare/v1.7.0...v1.8.1
[1.7.0]: https://github.com/bvandrc/serato-tools/compare/v1.6.2...v1.7.0
[1.6.2]: https://github.com/bvandrc/serato-tools/compare/v1.5.2...v1.6.2
[1.5.2]: https://github.com/bvandrc/serato-tools/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/bvandrc/serato-tools/releases/tag/v1.5.1
