# Changelog

Each release groups its changes by the part of the package they're in. Within each part, **[BREAKING]** changes come first, each with how to upgrade past it.

## [6.0.0] - 2026-11-10

### Database / Crates / Track Tags

- **[BREAKING]** `save()` on the library database, crates, and smart crates skips writing to the file's own path when it hasn't changed since it was loaded or last saved, as the track tag classes' `save()` does, and returns whether it wrote. Saving to another path always writes. It serializes the file once, to check it and to write it, so `Library.save` does too.
  - **Upgrading:** Pass `force=True` to write anyway, e.g. to overwrite a file changed on disk since it was loaded.
- **[BREAKING]** `save()` on `TrackCuesV1`, `TrackBeatgrid`, `TrackAutotags`, and `TrackWaveform` skips writing when the tag hasn't changed since it was read or last saved, as every other tag class's `save()` already does. Every tag class's `save()` now also returns whether it wrote, as `Track.save()` and the database's and crates' `save()` do.
  - **Upgrading:** Pass `force=True` to write anyway. If you pass in a tagfile with other unsaved changes, such as frames you set on it, and relied on one of these four classes' `save()` to write them, save the tagfile yourself when `save()` returns False (`tagfile.save()`), or pass `force=True`.
- **[BREAKING]** A database, crate, or Serato tag that's cut off or malformed raises only `ValueError`, no longer also `AssertionError`, and a number too big or negative for its field raises only `ValueError`, no longer also `struct.error`.
  - **Upgrading:** Catch `ValueError`, as 5.7.0 deprecated catching the others.
- **[BREAKING]** `serato_tools.utils.ui` is renamed `serato_tools.utils.cli`.
  - **Upgrading:** Import from `serato_tools.utils.cli`.

### Library

- **[BREAKING]** `Library.set_db_tracks_tags` and `set_db_track_tags` return a `DbTrackTagsResult` rather than a bool: `database_changed`, as the bool was, and `files_written`, the paths of the track files whose tags changed, so were written.
  - **Upgrading:** Read `.database_changed` where you used the bool, since the result is always truthy.
- **[BREAKING]** `Library.rename_track_file` returns the paths of the database, crates, and smart crates it changed, rather than a bool, and raises `FileExistsError` when a different file already exists at `dest`, rather than logging an error and returning False. The list is empty when none held the track, such as a file Serato hasn't imported.
  - **Upgrading:** Catch `FileExistsError` where you checked for False. It renamed the file whenever it returns, so a check for True can go.
- **Feature:** `Library.set_db_track_tags` / `set_db_tracks_tags` also set a track's metadata in its ID3 text frames and the database: `title`, `artist`, `album`, `genre`, `key`, `grouping`, `publisher`, `composer`, `year`, `remixer`, `track_number`, `disc_number`, and `comment`. An empty value removes it from both, as Serato does when a tag is cleared.
- **Feature:** Add `Library.save`, which writes each of the library's parsed files that has changed, once, and returns their paths. It saves changes made through `library.database`'s or the crates' own methods, such as `modify`.
- **Feature:** Add `Library.batch()`, a context manager: inside `with library.batch():`, `rename_track_file`, `remove_track_files`, and `set_db_tracks_tags` hold back writing the database and crates, and each changed file is written once when the block ends, instead of once per track. The track files themselves still change right away, so it saves even if the block raises.
- **Feature:** `Library.remove_track_files` returns a `RemoveTrackFilesResult`: `files_deleted`, the track files it deleted, and `library_files_changed`, the paths of the database, crates, and smart crates it changed.
- **Fix:** `Library.set_db_track_tags` / `set_db_tracks_tags` raise `DataTypeError` for a value of the wrong type, such as a color that isn't a `TrackColors`, before changing any file. Before, a color given as text raised `AttributeError`, and another wrong type, such as `beatgrid_locked="yes"`, was written to the track file before saving the database failed.

### Database / Crates

- **[BREAKING]** A database or crate track's `get_full_path()` is now its `full_path` property.
  - **Upgrading:** Replace `track.get_full_path()` with `track.full_path`.
- **[BREAKING]** `DataTypeError` and `DeeplyNestedListError` move from `serato_tools.utils` to `serato_tools.utils.bin_file_base`, next to the database and crate code that raises them.
  - **Upgrading:** Import them from `serato_tools.utils.bin_file_base`.
- **[BREAKING]** A database's or crate's `entries` and `version` are now internal.
  - **Upgrading:** Change a file through its methods (`modify_tracks`, `modify`, `add_tracks`, `set_rule`, ...), and read it through `get_entries`, `get_tracks`, or `to_json_object`. Its version is the `vrsn` entry `get_entries` gives.
- **[BREAKING]** A database or crate file with a number field that isn't the 2 or 4 bytes its type holds raises `ValueError`, as other malformed files do, rather than `struct.error`.
  - **Upgrading:** Catch `ValueError`.
- **[BREAKING]** A database or crate file with no version entry, such as an empty one, raises `ValueError`, as other malformed files do, rather than `AttributeError`.
  - **Upgrading:** Catch `ValueError`.
- **[BREAKING] Removed:** `DatabaseV2.rename_track_file`, deprecated in 5.2.0.
  - **Upgrading:** Use `Library.rename_track_file`, which also updates the crates and smart crates.
- **[BREAKING] Removed:** `add_track` and `remove_track`, deprecated in 5.1.0.
  - **Upgrading:** Use `add_tracks` and `remove_tracks`.
- **[BREAKING] Removed:** `get_entries_filtered(track_matcher)` on the database, crates, and smart crates.
  - **Upgrading:** Use `get_entries(track_matcher)`.
- **[BREAKING] Removed (CLI):** `serato_smartcrate`'s `--set_rules`.
  - **Upgrading:** Pass the rule options directly, without it.
- **Feature (CLI):** `serato_smartcrate` now takes each rule field as its own option, e.g. `serato_smartcrate Dubstep.scrate --grouping str_is UNTAGGED --year DELETE`.
  - `--help` lists the fields and comparisons.
  - A bad field, comparison, value, or number of arguments is rejected before any crate is changed.
  - A crate whose rules the options leave as they were isn't rewritten.
- **Feature:** `SmartCrate.delete_rule` returns whether the crate had a rule on that field to remove.
- **Feature:** A database or crate track's, or a smart crate rule's, `set_value` raises `DataTypeError` for a value that isn't the type its field holds, and `ValueError` for a number too big or negative for it, when it's set rather than only when the file is saved. `modify_tracks`, and so `modify`, checks the tracks it changes the same way.
- **Feature:** A smart crate rule's `comparison` is typed as `str` and its `field` as `int`, rather than as any value an entry can hold.
- **Feature:** Support libraries on an external drive (e.g. `E:\_Serato_` or `/Volumes/USB/_Serato_`): their track paths are relative to that drive's root, as Serato stores them, instead of the home library's drive.
  - Each database and crate finds that root from where its file is, in `track_path_root`, and `get_relative_path` / `get_full_path` take it as an optional `root`.
- **Fix:** A database or crate track's `relpath` and `full_path`, and a smart crate rule's `comparison`, `field`, and `value`, read the track's or rule's current entries, so they no longer keep a value set through `set_value` or removed through `remove_field`. In particular, the rules of one `modify()` call after one that changes a track's path are passed its new path, not its old one.
- **Fix:** `modify_tracks`, and so `modify`, change no track when `func` raises for one, rather than keeping the changes to the tracks before it.
- **Fix:** A crate's `add_tracks`, and so `add_tracks_from_dir`, skip a track already in the crate in another case, and `remove_duplicates` removes a repeat of a track's path in another case, as `remove_tracks` and `modify` match paths whatever their case. Before, a crate could hold one track twice, under paths differing only in case, and `add_tracks_from_dir` with `replace` removed a track held in another case than its file's name, then added it again.

### Track Tags

- **[BREAKING]** `TrackBeatgrid.find_nearest_beat` raises `NoBeatgridError` without a beatgrid, rather than returning None, which read as "no beat nearby".
  - **Upgrading:** Catch `NoBeatgridError` where you checked for None.
- **[BREAKING] Removed:** The tag classes' read-only `raw_data`, deprecated in 5.1.1.
  - **Upgrading:** Parse, modify, and serialize through each tag's own methods.
- **[BREAKING] Removed:** The `SeratoTrack` and `SeratoTag` names in `serato_tools.utils.track_tags`.
  - **Upgrading:** Use `ID3FileTag` and `SeratoGeobTag`.
- **[BREAKING] Removed:** `TrackCuesV2.modified`, deprecated in 5.6.0.
  - **Upgrading:** Use `has_changed`.
- **[BREAKING] Removed:** `TrackCuesV2` no longer reads the beatgrid from its own file for cue snapping, so that each tag class reads only its own tag. Its methods that did are removed: `snap_positions_to_beat`, `snap_positions_to_beat_rule`, `get_snapped_beat_ms`, and `get_beat_position`.
  - **Upgrading:**
    - For `snap_positions_to_beat` and `snap_positions_to_beat_rule`, use `Track.snap_cues_to_beats`, or `TrackCuesV2.snap_cues_to_beats(beatgrid, ...)` with a beatgrid you pass it. Both return the moves rather than printing them. There's no rule to pass to `modify_entries`: snap, then make any other edits, before saving.
    - For `get_snapped_beat_ms`, use `TrackBeatgrid.get_snapped_position` (e.g. `track.beatgrid.get_snapped_position`).
    - For `get_beat_position(entry)`, use `beatgrid.get_beat_position(entry.position)`.
- **[BREAKING] Removed (CLI):** The CLIs' edit modes: `-e` / `--edit` on `serato_snap_cues_v2`, `python -m serato_tools.track_cues_v1`, and `python -m serato_tools.track_autotags`. Each still prints the tag's entries or values. `TrackCuesV2.parse_entries_file`, which read the text the edit mode wrote, is removed with them.
  - **Upgrading:** Change a tag through its class's methods instead, such as `TrackCuesV2.modify_entries`, `set_track_color`, and `snap_cues_to_beats`, or `TrackAutotags.set`.
- **Feature:** Add `TrackTextFrames` (`serato_tools.track_text_frames`), which reads and sets a track file's ID3 text frames, and `Track.text_frames`. Setting a frame to `""` removes it, as Serato does when a tag is cleared.
  - `TrackTextFrames.Fields` names the frames Serato shows a column for (`Fields.TITLE`, `Fields.GENRE`, ...), as `DatabaseV2.Fields` does, to pass to `get` and `set` in place of the frame ID.
  - `Fields.COMMENT` gets and sets the track's comment the way Serato reads and writes it, so Serato shows the comment you set.
- **Feature:** Add `Track.snap_cues_to_beats(tolerance_beats)`, which snaps a track's cues to its beatgrid in memory and returns each move, as a `SnappedCue`. It needs the `Track`'s `cues_v2` and `beatgrid` parsed (the default).
  - `TrackCuesV2.snap_cues_to_beats(beatgrid, tolerance_beats)` does the same with the `TrackBeatgrid` passed to it.
  - `TrackBeatgrid.get_snapped_position` gives the position a single cue would snap to.
- **Feature (CLI):** `serato_snap_cues_v2 --snap_cues` now says which cue each move was for, and which tag is missing for a track without cues or a beatgrid. Its options are unchanged.
- **Fix (CLI):** `serato_tagdump` exits saying a file has no tags, rather than with a traceback.
- **Deprecated:** Passing `delete_tags_v1` to an edit (`TrackCuesV2.modify_entries`, `set_track_color`, and `set_beatgrid_locked`, and `Track.set_track_color` and `set_beatgrid_locked`) isn't removed yet: it stays deprecated until a future major release, in favor of passing it to `save()`.

### USB Export

- **Feature:** Add `source_serato_dir` to `copy_crates_to_usb`, and `serato_dir` to `get_crate_files`, for a library on another drive. Each defaults to the home library.
- **Feature (CLI):** Add `--source` to `serato_usb_export`, the `_Serato_` folder of a library on another drive to export from instead of the home library.
- **Fix:** `copy_crates_to_usb` stores tracks' paths relative to the drive when `dest_tracks_dir` is an absolute path on it. Before, on macOS, `/Volumes/USB/Tracks` was stored as `Volumes/USB/Tracks/...`.

## [5.7.0] - 2026-11-15

### Database / Crates / Track Tags

- **Feature:** A cut-off or malformed database, crate, or tag now raises `ValueError` saying what's wrong. It's still an `AssertionError` too.
- **Feature:** A number too big or negative for its field now raises `ValueError` naming the field. It's still a `struct.error` too.
- **Feature:** Errors that were a bare `Exception` are now a `ValueError`, `TypeError`, `FileNotFoundError`, or `ImportError` saying what's wrong.
- **Deprecated:** Catching a malformed file's error as `AssertionError`, or an out-of-range number's as `struct.error`, is deprecated, but still works: catch `ValueError`, which is all they'll be in 6.0.

### USB Export

- **Fix:** USB export now keeps the database entries of the track whose file it copies, when tracks share a filename. Before, the copy could show another track's metadata.
- **Fix:** USB export now copies only a track's own stems file. Before, `B Extended.serato-stems` beside `B.mp3` stopped the export partway. NOTE: Using stems via USB is still completely untested.
- **Fix:** USB export now writes each smart crate as a regular crate of its tracks, which `Crate` can open.

### Database / Crates

- **Feature:** Add `SmartCrate.to_regular_crate(file)`, which gives a regular crate of a smart crate's tracks, sort, and columns.
- **Feature:** Add `SeratoBinFile.check_value(field, value)`, which raises for a value the field can't hold.
- **Feature:** Methods that took a list of track paths or rules now take any collection of them, such as a `set` or `tuple`, not just a `list`.
- **Fix:** `remove_tracks` and `Library.remove_track_files` now match a track's path whatever its case.
- **Fix:** `add_tracks_from_dir` now skips subfolders and hidden files, such as `.DS_Store`.

### Track Tags

- **Feature:** Add `GeobKeys`, each Serato tag's GEOB key.
- **Feature:** A track missing a tag that's needed, such as one Serato hasn't analyzed yet, now raises `NoCuesError`, `NoBeatgridError`, or `NoWaveformError`, naming the tag and file. They're `MissingTagError`s, in `serato_tools.utils.track_tags`, and still `ValueError`s.
- **Feature (CLI):** The tag CLIs now read a file of the tag's own bytes, such as one `serato_tagdump` writes.
- **Feature (CLI):** `serato_beatgrid` now prints which tag is missing, rather than a traceback.
- **Fix:** A track's Serato tags can now be read and saved in a file whose ID3 tags have no frames.
- **Fix:** After `TrackBeatgrid.analyze_and_write`, `find_nearest_beat` now uses the new grid.
- **Fix:** `TrackBeatgrid.analyze_and_write` now keeps the old grid when the analysis gives one Serato wouldn't write, such as downbeats out of order.
- **Fix (CLI):** `serato_snap_cues_v2 -e` now keeps an entry you leave unchanged after the editor fails or the content is invalid, and works on Windows, where the editor couldn't open its file.

### Library

- **Fix:** `Library.set_db_track_tags` / `set_db_tracks_tags` now raise for a value the database can't hold before changing any file.

## [5.6.1] - 2026-11-10

### Database / Crates

- **Feature:** Add `remove_field(field)` to a track entry (e.g. `DatabaseV2.Track`), which removes a field and returns whether it was there. It raises ValueError for the track's path.
- **Fix:** Setting a track's field to `""`, through `modify()`, `modify_and_save()`, or a track entry's `set_value`, removes the field, as Serato does when a tag is cleared, rather than storing it empty.

### Documentation

- **Docs:** Add docstrings to each source module, and to all classes and functions whose use wasn't clear.

## [5.6.0] - 2026-11-09

### Database / Crates / Track Tags

- **Feature:** Add a read-only `has_changed` property to the library database, crates, smart crates, each track tag class, and `Track`, which says whether saving would write a change, without saving.
  - NOTE: For the database and crates, each check serializes the file for `has_changed`, as saving does, which takes time over many files.

### Track Tags

- **[BREAKING]** Any write of `Serato Markers2` now deletes `Serato Markers_` by default, not only one after `modify_entries`, `set_track_color`, `set_beatgrid_locked`, or `snap_positions_to_beat`: that includes the `serato_snap_cues_v2 --edit` CLI, a forced save, and saving a deleted `Serato Markers2`.
  - **Upgrading:** Pass `delete_tags_v1=False` to `save()` where you need `Serato Markers_` kept.
- **[BREAKING] Deprecated:** `TrackCuesV2.modified` is deprecated in favor of `has_changed`, and will be removed in the next major version. Until then it's read-only and returns `has_changed`, so an edit that changes nothing no longer resets it.
  - **Upgrading:** Stop assigning `modified`, which now raises, and read `has_changed` instead.
- **Feature:** `TrackCuesV2.save()` and `Track.save()` take `delete_tags_v1` (default True), which deletes the legacy `Serato Markers_` tag when `Serato Markers2` is written, since a stale one stops the change from appearing in Serato. `Library.set_db_track_tags` and `set_db_tracks_tags` pass theirs to it.
- **Fix:** Fix `TrackCuesV2.save()` skipping the save, and losing a change, when an edit that changed nothing followed one that did.
- **Fix:** Fix `TrackCuesV1` failing to serialize a tag with an unset cue or loop position, as every `Serato Markers_` tag Serato writes has.
- **Fix:** `TrackCuesV2` deletes the `Serato Markers_` tag only when it writes a change to `Serato Markers2`. An edit that changed nothing, or was changed back, used to delete it from the file in memory, and saving another tag in the same file would write the deletion.
- **Deprecated:** Passing `delete_tags_v1` to `TrackCuesV2.modify_entries`, `set_track_color`, or `set_beatgrid_locked`, or to `Track.set_track_color` or `set_beatgrid_locked`, is deprecated in favor of passing it to `save()`, and will be removed in the next major version. Until then, passing False still keeps `Serato Markers_` at the next save, unless another edit since the last save didn't pass False.

## [5.5.0] - 2026-11-06

### Library

- **Feature:** Add `Library.set_db_track_tags` and `set_db_tracks_tags`, which set a track's color and beatgrid lock in its tags and in the database at once, so Serato shows the change right away, without rescanning file tags. Only ID3 files (.mp3, .aiff, .aif) are currently supported.
- **Feature:** `Library.rename_track_file` returns whether it renamed the file. It returns False when a different file already exists at `dest`, which it still only logs.

### Database / Crates

- **Feature:** Add `ModifyFunc` (e.g. `DatabaseV2.ModifyFunc`), the type of a `ModifyRule`'s `func`, to annotate your own functions with.

### Track Cues

- **[BREAKING] Fix:** `TrackCuesV2` raises ValueError for a `COLOR`, `BPMLOCK`, `CUE`, or `LOOP` entry unlike any Serato writes (e.g. a nonzero byte where Serato always writes `00`), rather than risk rewriting one it doesn't understand. That includes a cue past 8, which Serato ignores since it only has 8 cue pads, and it raises on saving one too.
  - **Upgrading:** Catch `ValueError` when reading tags you don't control, and remove any cue past 8 before saving.
- **Fix:** Changing a track's cues keeps its BPM lock before its flips, the order Serato writes them in.
- **Fix:** `TrackCuesV2` writes the `Serato Markers2` tag byte for byte as Serato does: its base64 ends as Serato's does, and it keeps the size the tag already had rather than shrinking it. A tag whose cues no longer fit grows in 512-byte steps past 470 bytes, as Serato grows it.
- **Fix:** Fix a saved loop's `color` (`TrackCuesV2.LoopEntry.color`) reading and setting the wrong byte: it's now the loop's color, as 3 bytes like a cue's.
- **Fix:** Fix setting a cue to `CueColors.LIMEGREEN3` giving it the sea foam color instead of lime green.

## [5.4.1] - 2026-11-04

### Track Tags

- **Fix:** Fix `TrackCuesV2.set_track_color` and `set_beatgrid_locked` doing nothing on a track whose tags don't have a color or lock yet: they now add the entry, and the `Serato Markers2` tag, as Serato writes them.

## [5.4.0] - 2026-11-04

### Track Tags

- **Feature:** Add `Track` (`serato_tools.track`), which reads a track file's Serato tags (`cues_v2`, `cues_v1`, `beatgrid`, `autotags`, `gain`, and, if asked for, `waveform`) from one open file, and saves all of their changes in a single write, skipping it when nothing changed.
- **Feature:** Add `TrackCuesV2.set_beatgrid_locked`, which locks or unlocks the track's beatgrid.
- **Fix:** Updates to `TrackGain` setting, saving, and deleting.

## [5.3.2] - 2026-11-04

### Packaging

- **Fix:** Fix type checkers (pyright, mypy, etc.) ignoring the package's type hints: it now ships the `py.typed` marker that tells them the hints are there.

## [5.3.1] - 2026-11-04

### Track Cues

- **Fix:** Fix cue snapping moving almost every cue by 1 ms: 5.1.1 started snapping cues exactly `min_ms_change` away, and the default of 1 caught the 1 ms gap Serato commonly leaves between a cue and the rounded beat. The default `min_ms_change` is now 2, so 1 ms differences are left alone again, and passing less than 2 warns.

## [5.3.0] - 2026-11-03

### Database / Crates

- **Feature:** Name more database track fields, so they're printed with a name instead of `Unknown Field`, and can be used in `DatabaseV2.modify`: `COMMENT`, `REMIXER`, `TRACK_NUMBER`, `DISC_NUMBER`, `PLAY_COUNT`, `COLOR` (the track color, as `0xRRGGBB`), `CORRUPT_REASON`, `READ_ONLY`, and `OVERVIEW_BUILT` (waveform created).
  - The smart crate field holding the on/off value of "match all" and "live update" is named too: `SmartCrate.RuleFields.SETTING_VALUE`.
- **Feature:** Add `DatabaseV2.get_corrupt_tracks`, and `--list_corrupt` to the database CLI, which list the tracks Serato marked corrupt along with the reason Serato gives.

## 5.2.1 - 2026-11-03

### Track Gain Tags

- **[BREAKING] Fix:** Fix `TrackGain`, which never read or wrote anything: Serato stores a track's gain as an `RVA2` ID3 frame named `SeratoGain`, not the `replaygain_SeratoGain_gain` / `_peak` keys we had before.
  - **Upgrading:** If you delete gain when `gain` or `peak` isn't `None`, check that code: Serato writes the frame on most analyzed tracks, with a gain of `0.0` unless one was set, so it's now `0.0` rather than `None` for them.

### USB Export

- **Fix:** Fix USB export crate matchers: a glob like `house*` was treated as a regex, so it also matched crates like `housing`; matchers are now tried as globs first, falling back to regex.
  - Also, only actual crate files are matched (a stray file like `.DS_Store` crashed the export), and a missing `Subcrates` or `SmartCrates` folder means no crates of that kind instead of an error.

## [5.2.0] - 2026-11-03

### Packaging

- **[BREAKING] Fix:** `pip install serato-tools` no longer installs the optional deps (about 430 MB): they're only installed by the extra whose feature needs them, as the README always described.
  - `waveform_drawing` and `beatgrid_analysis` now also install `mutagen`, since they read the track's tags through it.
  - **Upgrading:** If you use track tags (cues, beatgrid, waveform, etc.), the beatgrid analysis, or waveform drawing, install with the matching extra, e.g. `pip install "serato-tools[track_tags]"`, or `pip install "serato-tools[all]"` for everything.
- **Docs:** Add the MIT `LICENSE` file the package metadata already declared, with the notices of the projects it's derived from.

### Library

- **Feature:** Add `Library`, which renames or removes track files and updates the database, crates, and smart crates to match, so the track isn't left missing in Serato.
  - **Performance:** It also speeds up an app that makes many library changes: each file is parsed only once, the first time it's needed, then kept for every later change. Use `library.database` for other database changes too, so they share that one parse.

### Database / Crates

- **Fix:** Fix track paths resolving to a broken path on macOS and Linux.
- **Deprecated:** `DatabaseV2.rename_track_file` is deprecated in favor of `Library.rename_track_file`, and will be removed in the next major version. It now also updates smart crates, and looks for crates next to the database instead of in the default `_Serato_` folder.

### Track Cues

- **Fix:** Fix the `serato_snap_cues_v2` command failing with `ImportError: cannot import name 'main'`.

## [5.1.2] - 2026-11-03

### Documentation

- **Docs:** Fix the README's examples, which had drifted from the current API, and add a table of contents.
- **Docs:** Add a changelog link to the project's PyPI page.

## [5.1.1] - 2026-11-03

### USB Export

- **Performance:** Much faster USB export: Now scans each source directory once for `.serato-stems` files instead of globbing per track.
  - **Fix:** Fixes a track name containing glob characters like `[` breaking the stem lookup.
- **Fix:** Fix the USB export writing a corrupted crate order file on every export.

### Database / Crates

- **Performance:** Printing or JSON-dumping a large database is faster: field display names are now looked up in a cached map.
- **Fix:** Fix smart crate rules: a rule's value is now stored in the value field its comparison expects, like Serato does — integer-comparison values set from the CLI were stored as text, and changing a rule's value type left both value fields in the rule.

### Track Tags

- **Fix:** Misc. edge-case fixes and clearer errors for cues, cue snapping, and beatgrids.
- **Deprecated:** The tag classes' stored bytes (`SeratoTag.raw_data`) are now internal: the deprecated read-only `raw_data` getter will be removed in the next major version — parse, modify, and serialize through each tag's own methods instead.

## [5.1.0] - 2026-11-03

### Database / Crates

- **Feature:** Add `add_tracks` and `remove_tracks` for batch changes in one pass.
- **Performance:** Adding tracks to a crate, `remove_duplicates`, and the USB export dedupe are much faster on a large library.
- **Deprecated:** `add_track` and `remove_track` are deprecated in favor of `add_tracks` and `remove_tracks`, and will be removed in the next major version.

## [5.0.2] - 2026-11-03

### Database / Crates

- **[BREAKING]** `modify` on a database or regular crate now rejects smart crate rule fields, which moved from the shared `Fields` enum to the new `SmartCrate.RuleFields`.
  - **Upgrading:** Name a smart crate rule field through `SmartCrate.RuleFields` rather than `Fields`.

## 5.0.1 - 2026-11-03

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

## 3.6.1 - 2025-10-28

### General

- **Fix:** Misc. bug fixes.

## [3.5.3] - 2025-08-19

### Smart Crates

- **[BREAKING]** Smart crate add rule improvements: `SmartCrate.modify_rules(func)` is replaced by `set_rule(field, comparison, value)` and `delete_rule(field)`.
  - **Upgrading:** Set or delete each rule through `set_rule` and `delete_rule`, rather than changing rules in a function passed to `modify_rules`.

## [3.4.3] - 2025-08-19

### Smart Crates

- **[BREAKING]** Convert smart crate rules from objects to enums.

## 3.4.0 - 2025-06-11

### Crates

- **Feature:** Modify smart crate rules.
- **Feature:** Add `serato_smartcrate` and `serato_crate` entry points.

## [1.5.1] - 2025-04-11

- Initial publish (pyproject.toml added). Serato library and track metadata modification.

[6.0.0]: https://github.com/bvandrc/serato-tools/compare/v5.7.0...v6.0.0
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
[3.7.0]: https://github.com/bvandrc/serato-tools/compare/v3.5.3...v3.7.0
[3.5.3]: https://github.com/bvandrc/serato-tools/compare/v3.4.3...v3.5.3
[3.4.3]: https://github.com/bvandrc/serato-tools/compare/v1.5.1...v3.4.3
[1.5.1]: https://github.com/bvandrc/serato-tools/releases/tag/v1.5.1
