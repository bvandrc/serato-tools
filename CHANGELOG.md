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

## [3.6.2] - 2025-12-06

### Database / Crates

- **[BREAKING]** A database's or crate's `data` is renamed `entries`, and a subclass's `DEFAULT_DATA` is renamed `DEFAULT_ENTRIES`. The `dir` attribute is removed.
  - **Upgrading:** Read `entries` where you read `data`, and use `os.path.dirname(x.filepath)` for `dir`.
- **[BREAKING]** A track's `path` (the `Track` passed to `modify_tracks` and `filter_tracks`) is renamed `relpath`, and `set_path` now takes a full path, storing it without its drive and with forward slashes, as Serato does. `StructCls` is renamed `EntryListCls`, its `to_struct()` is renamed `to_entries()`, and a track's `track_path_key` is renamed `path_key`.
  - **Upgrading:** Read `track.relpath` where you read `track.path`, call `to_entries()` where you called `to_struct()`, and use `track.get_full_path()` for the track's full path.
- **[BREAKING]** `to_entries(track_matcher=None)` is split into `get_entries()` and `get_entries_filtered(track_matcher)`, which works where `to_entries`' `track_matcher` raised `TypeError`. Values are now given as stored, rather than as their `repr()` text, so printing a database or crate no longer quotes strings.
  - **Upgrading:** Call `get_entries()`, or `get_entries_filtered(track_matcher)` to keep only the tracks whose path matches a regex.
- **[BREAKING]** `format_filepath` is renamed `get_relative_path`.
  - **Upgrading:** Call `get_relative_path` (e.g. `Crate.get_relative_path(path)`).
- **[BREAKING]** A crate's or smart crate's `list_dir()`, which printed the crate files, is replaced by `get_serato_crate_files(file_or_dir=None)`, which returns them: the files in its Serato folder, or in the folder given, or the file given.
  - **Upgrading:** Print them yourself, e.g. `print("\n".join(Crate.get_serato_crate_files()))`.
- **[BREAKING]** `DeeplyNestedStructError` in `serato_tools.utils` is renamed `DeeplyNestedListError`.
  - **Upgrading:** Import and catch `DeeplyNestedListError`.
- **Feature:** The database, crates, and smart crates now refuse a file whose version hasn't been tested (their `TESTED_VERSIONS`), raising `ValueError` when it's loaded, so a format this package may misparse can't be written back.
- **Feature:** `modify` and `modify_and_save` now work on crates and smart crates too, not only the database.
- **Feature:** Add `change_track_path(src, dest)` to the database and crates, which changes a track's path without saving.
- **Feature:** `DatabaseV2.rename_track_file` now also changes the track's path in every crate, so the renamed file isn't missing from them. Smart crates aren't changed.
- **Feature:** Add `find_missing()` to the database and crates, which goes through the tracks whose file doesn't exist, asks for each one's new location (or a folder to look for it and the rest in, or `s` to skip), and saves.
- **Feature (CLI):** Add `--find_missing` to `serato_crate` and `python -m serato_tools.database_v2`.
- **Feature:** The database and crates can be written to JSON with `to_json_object()` and `write_json(file)`, with bytes base64-encoded, and loaded back by passing the `.json` file's path to the constructor.
- **Feature:** Add `get_track_paths(include_drive=True)`, `Track.get_full_path()`, and `get_full_path(path)`, which give a track's full path, with the drive the Serato folder is on (`SERATO_DRIVE` in `serato_tools.utils`).
- **Feature:** Add `print_track_paths(filenames_only=False)` to crates and smart crates.
- **Feature (CLI):** `serato_crate` and `serato_smartcrate`'s `-l` and `-f` now print each track's full path, with its drive.
- **Feature:** `remove_track` now takes a track's full path too, not only the path as the file stores it.

### USB Export

- **Fix:** USB export now writes each track's path in the crates relative to the drive, as in the database (`Tracks/<file>`), and with forward slashes in the database. Before, on macOS and Linux the crates' paths included the drive's mount point, and on Windows the database's used backslashes.

### Packaging

- **Feature:** `mutagen`, `numpy`, `librosa`, and `pillow` are now installed with the package, rather than only with the `track_tags`, `waveform_drawing`, and `beatgrid_analysis` extras, which are still accepted. On Python 3.14 and later, `audioread` 3.1.0 or later is installed too.

## [3.5.3] - 2025-08-19

### Smart Crates

- **[BREAKING]** Smart crate add rule improvements: `SmartCrate.modify_rules(func)` is replaced by `set_rule(field, comparison, value)` and `delete_rule(field)`.
  - **Upgrading:** Set or delete each rule through `set_rule` and `delete_rule`, rather than changing rules in a function passed to `modify_rules`.

## [3.4.3] - 2025-08-19

### Database / Crates

- **[BREAKING] Removed (CLI):** The `-o` / `--output` option of `python -m serato_tools.crate` and `python -m serato_tools.smart_crate`, which saved the crate to another file.
  - **Upgrading:** Call the crate's `save(file)`.
- **Feature (CLI):** Add the `serato_crate` and `serato_smartcrate` commands, which take a crate file, a folder of crates, or `--all` for every crate or smart crate in the Serato library.

### Smart Crates

- **[BREAKING]** Smart crate rule fields and comparisons are now the `SmartCrate.RuleField` and `SmartCrate.RuleComparison` enums, rather than the `RULE_FIELD` and `RULE_COMPARISON` dicts.
  - **Upgrading:** Replace `SmartCrate.RULE_FIELD["genre"]` with `SmartCrate.RuleField.GENRE`, and `SmartCrate.RULE_COMPARISON["STR_IS"]` with `SmartCrate.RuleComparison.STR_IS`.
- **Feature:** Add `set_field` and `set_comparison` to a smart crate's `Rule`, and its `set_value` takes the value alone, storing it in the value field for its type.
- **Feature (CLI):** `serato_smartcrate --set_rules` sets the value of the rules on each field it's given, e.g. `--set_rules --grouping UNTAGGED`.
- **Fix:** Fix reading a smart crate rule that doesn't hold every kind of value.

### Track Tags

- **Fix:** A `TrackAutotags` of a file without the tag gives None for `bpm`, `autogain`, and `gaindb`, rather than raising `AttributeError`.
- **Fix:** A tag's `save()` no longer raises for a file that has no such tag and no data to write for it.

### USB Export

- **Feature (CLI):** `serato_usb_export` takes `-r` as short for `--root_crate`.

## [3.3.0] - 2025-06-11

### Crates

- **Feature:** Add `DIR_PATH` to `Crate` and `SmartCrate`, the full path of the folder Serato keeps them in (e.g. `~/Music/_Serato_/Subcrates`).

### Smart Crates

- **Feature:** Add `SmartCrate.modify_rules(func)`, which passes each of the crate's rules to `func` as a `SmartCrate.Rule` and keeps the rule it returns. A `Rule` gives its `field`, `comparison`, and `value`, and changes through `set_value(field, value)`.
  - NOTE: In this version, it raises `AttributeError` for a rule without all three rule value fields, which is every rule Serato writes. 3.4.3 fixes it.

## [3.2.10] - 2025-06-11

### USB Export

- **Feature:** Add USB export: the `serato_usb_export` console script (and `copy_crates_to_usb` in `serato_tools.usb_export`) copies the crates and smart crates you choose to a drive, with all their tracks in one `Tracks` folder, deduplicated by filename. It copies only the track files that changed since the last export, along with each track's `.serato-stems` file, unlike Serato's own sync.
  - `--drive` (`-d`) is the drive, e.g. `E` on Windows.
  - `--crate_matcher` (`-c`) takes one or more glob or regex patterns for the crate filenames to export, e.g. `"*house*"`. Pass `"*"` for all of them.
  - `--root_crate` puts every exported crate inside one crate on the drive.
  - It writes the drive's database and crates with the tracks' new paths, each smart crate as a regular crate, the crate order, and Serato's Stems crate, and clears each track's played flag.
  - NOTE: It replaces the drive's existing `_Serato_` folder, crates included, though not its track files.

### Database / Crates

- **[BREAKING]** `SERATO_FOLDER` in `serato_tools.utils` is renamed `SERATO_DIR`.
  - **Upgrading:** Import `SERATO_DIR`.
- **[BREAKING]** `Crate.FOLDER` and `SmartCrate.FOLDER`, the full path of the crates' folder, are replaced by `DIR`, its name in the Serato folder (`"Subcrates"` and `"SmartCrates"`).
  - **Upgrading:** Use `os.path.join(SERATO_DIR, Crate.DIR)`.
- **[BREAKING]** A crate's `tracks()`, `list_folder()`, and `add_tracks_from_folder(folder_path, replace)` are renamed `get_track_paths()`, `list_dir()`, and `add_tracks_from_dir(dir, replace)`.
  - **Upgrading:** Call the new names.
- **[BREAKING]** `str()` of a crate or smart crate now gives its entries, as its `print()` printed them, rather than its number of tracks and their paths. `print()` prints the same.
  - **Upgrading:** Use `get_track_paths()` for the tracks' paths.
- **[BREAKING]** A crate's `remove_track` no longer raises `ValueError` for a track the crate doesn't have.
  - **Upgrading:** Check `get_track_paths()` first where you need to know.
- **[BREAKING] Removed:** A crate's `track_dir`, the folder holding its `_Serato_` folder.
  - **Upgrading:** Use `os.path.dirname(os.path.dirname(crate.dir))`.
- **[BREAKING] Removed:** `DatabaseV2.find_missing` and `python -m serato_tools.database_v2 --find_missing`, which only raised `NotImplementedError`.
  - **Upgrading:** Nothing replaces them, since they never worked.
- **[BREAKING] Removed (CLI):** `-d` / `--data` on `python -m serato_tools.crate` and `python -m serato_tools.smart_crate`, since printing the crate's entries is now the default.
  - **Upgrading:** Drop `-d`, and pass `-l` (`--list_tracks`) for the tracks' paths, the old default, or `-l -f` for their filenames.
- **Feature:** Add `get_track_paths()`, `modify_tracks(func)`, `filter_tracks(func)`, `remove_track(filepath)`, and `remove_duplicates()` to the database, crates, and smart crates. `modify_tracks` passes each track to `func` as a `Track` (with its `path`, `get_value`, `set_value`, and `set_path`) and keeps the one it returns, and `filter_tracks` keeps the tracks `func` returns True for.
- **Feature:** Add `Fields.HAS_STEMS` (`bstm`) and `Fields.PLAYED` (`bply`).
- **Fix:** A crate or smart crate whose file doesn't exist yet can now be created and saved. Before, its default entries raised `DataTypeError`.

### Track Tags

- **[BREAKING] (CLI)** `python -m serato_tools.track_beatgrid`'s `-e` (`--analyze`) is now `-a`.
  - **Upgrading:** Pass `-a` or `--analyze`.
- **Fix:** `TrackCuesV2` now reads a `Serato Markers2` tag with no null padding after its data, rather than raising `ValueError`.
- **Fix (CLI):** The beatgrid analysis console script, which failed to start, is now `serato_analyze_beatgrid "track.mp3"`, which analyzes the track and writes its beatgrid.

## [3.1.0] - 2025-05-14

### Database / Crates

- **[BREAKING]** `DatabaseV2`'s constructor argument `filepath` is renamed `file`, as the crates' is.
  - **Upgrading:** Pass `file=`, or pass the path positionally.
- **[BREAKING]** A database's `data` is now a list, rather than a generator that could be read only once, and holds each track's entries as a list rather than a tuple, as a crate's does.
  - **Upgrading:** Check for `list` where you checked for `tuple`.
- **Fix:** `DatabaseV2.modify` now applies rules to fields stored before the track's path, such as `ttyp` (file type), which it skipped before.
- **Fix:** Saving a smart crate no longer raises `ValueError`. Before, the crates' writer couldn't write its rule entries.
- **Fix:** The default Serato folder (`SERATO_FOLDER`), and so the default database file and crate folders, now resolve on macOS and Linux, where the path had a backslash in it (`~/Music\_Serato_`).

## [3.0.1] - 2025-05-14

### Database / Crates

- **[BREAKING]** Field names are now the `Fields` StrEnum on the database and crates (`DatabaseV2.Fields`, `Crate.Fields`, and `SmartCrate.Fields`), e.g. `DatabaseV2.Fields.FILE_PATH` for `"pfil"`, replacing `FIELDNAMES`, `FIELDNAME_KEYS`, and `TRACK_FIELD`. Each is equal to its 4-character key, so a rule giving its field as a string still works. A field's readable name (`get_field_name`, and the printed database and crates) now comes from the enum, so some read differently, e.g. `tsng` is "Title" rather than "Song Title".
  - **Upgrading:** Use `Fields` (e.g. `Crate.Fields.TRACK` for `TRACK_FIELD`), `FIELDS` for the list of keys, and `get_field_name(field)` for a field's readable name.
- **[BREAKING]** A database's entries no longer hold each field's length: `data` gives `(field, value)` rather than `(field, length, value)`, and `to_entries()` gives `(field, name, value)` rather than `(field, name, value, length)`. Printing the database no longer shows each field's size.
  - **Upgrading:** Unpack two values from `data` and three from `to_entries()`.
- **Feature:** Add `DatabaseV2.remove_duplicates()`, which removes each track whose path repeats an earlier track's.

### Track Cues

- **[BREAKING]** `TrackCuesV2.CUE_COLORS` and `TRACK_COLORS` are now the `CueColors` and `TrackColors` enums, named in uppercase (`TrackColors.PINK` for `TRACK_COLORS["pink"]`), and `get_track_color_name()` gives the uppercase name.
  - **Upgrading:** Use e.g. `TrackCuesV2.TrackColors.PINK`, and its `.value` for the color's bytes.
- **[BREAKING]** `TrackCuesV2.set_track_color` takes a `TrackColors` member, and no longer a color's name.
  - **Upgrading:** Pass e.g. `TrackCuesV2.TrackColors.PINK` for `"pink"`.
- **[BREAKING]** A `color` rule passed to `TrackCuesV2.modify_entries` is now given the color as a `CueColors` or `TrackColors` member (bytes only for a color neither has), and can return one. `ColorModifyRule` is split into `CueColorModifyRule` and `TrackColorModifyRule`.
  - **Upgrading:** Compare the color with a member (e.g. `color == TrackCuesV2.CueColors.RED`), and type rules with `CueColorModifyRule` or `TrackColorModifyRule`.

## [2.6.0] - 2025-05-14

### Database / Crates

- **Feature:** Add `Crate.list_folder()` and `SmartCrate.list_folder()`, which print the path of each crate or smart crate in the Serato library's `Subcrates` or `SmartCrates` folder (`Crate.FOLDER` and `SmartCrate.FOLDER`).
- **Feature:** Add `SERATO_FOLDER` (`serato_tools.utils`), the default `_Serato_` folder, in which `DatabaseV2.DEFAULT_DATABASE_FILE` and the crate folders are found.
- **Feature (CLI):** `python -m serato_tools.crate` and `python -m serato_tools.smart_crate` without a file now list the crates or smart crates to choose from, rather than failing.

## [2.5.0] - 2025-05-14

### Packaging

- **[BREAKING]** Requires Python 3.12 or later (`requires-python >= 3.12`), since the package's type aliases are now `type` statements.
  - **Upgrading:** Upgrade to Python 3.12 or later, or stay on 2.4.0.

### Database / Crates / Track Tags

- **[BREAKING]** The type aliases drop their `Type` suffix: `DatabaseV2.ValueType`, `ParsedType`, and `ValueOrNoneType` are now `Value`, `Parsed`, and `ValueOrNone`, `TrackCuesV2.ValueType` is `TrackCuesV2.Value`, and `SeratoTrack.TagfileType` and `FileArgType` and `SeratoTag.FileOrDataType` are `Tagfile`, `FileArg`, and `FileOrData`. A crate's `ValueType`, `StructType`, and `ValueOrNoneType` are now `Value`, `Struct`, and `ValueOrNone`, defined on its new base class, `CrateBase` (`serato_tools.utils.crate_base`).
  - **Upgrading:** Rename them where you annotate with them.

### Database / Crates

- **[BREAKING]** `to_dicts()` on the database and crates is renamed `to_entries()`, and yields tuples rather than dicts: `(field, field_name, value, size_bytes)` for the database, and `(field, field_name, value)` for a crate, with nested entries in the same form.
  - **Upgrading:** Call `to_entries()` and unpack each tuple, e.g. `for field, field_name, value in crate.to_entries():`.
- **[BREAKING]** `Crate.include_tracks_from_folder` is renamed `add_tracks_from_folder`.
  - **Upgrading:** Call `add_tracks_from_folder`.
- **[BREAKING]** `SeratoBinDb` (`serato_tools.utils.database`), the base class of the database and crates, is renamed `SeratoBinFile` and moves to `serato_tools.utils.bin_file_base`.
  - **Upgrading:** Import `SeratoBinFile` from `serato_tools.utils.bin_file_base`.

### Smart Crates

- **Feature:** Add `SmartCrate` (`serato_tools.smart_crate`), which reads a smart crate (`.scrate`): its tracks through `tracks()`, and its entries, rules included, through `print()`, which names each rule's field and comparison (`SmartCrate.RULE_FIELD` and `SmartCrate.RULE_COMPARISON`). Its `save()` writes it back. Changing its rules isn't supported yet.
- **Feature (CLI):** Add `python -m serato_tools.smart_crate`, which prints a smart crate's tracks, or its entries with `-d` / `--data`.

## [2.4.0] - 2025-05-13

### Packaging

- **Feature:** Declare support for Python 3.9 and later (`requires-python >= 3.9`), and stop using syntax newer than that, such as `X | Y` unions evaluated at runtime. On Python 3.9 and 3.10, it also needs `typing_extensions`, which isn't installed with it.
- **Fix:** Fix `serato_tools.database_v2` failing to import on Python before 3.13 (`TypeError: Too few arguments for typing.Generator`), and `serato_tools.crate` before 3.12 (`SyntaxError`).

### Database / Crates

- **Fix:** Fix `repr()` of a database or crate raising `TypeError`. It now gives the file's raw bytes.

### Track Gain Tags

- **Feature:** Add `TrackGain.save()`, which saves the track's file, such as after `delete()`.

## [2.3.1] - 2025-05-13

### Database / Crates

- **[BREAKING]** Saving methods are renamed: `DatabaseV2.write_file(out_file)` is now `save(file)`, `DatabaseV2.modify_file(rules, out_file)` is `modify_and_save(rules, file)`, and `Crate.save_to_file(fname)` is `save(file)`, which raises `ValueError` for a path that doesn't end in `.crate`.
  - **Upgrading:** Call `save` and `modify_and_save`.
- **[BREAKING] Removed:** `DatabaseV2.parse()` and `Crate.load_from_file()`. Each reads its file when it's constructed.
  - **Upgrading:** Construct a new `DatabaseV2` or `Crate` to read the file again.
- **[BREAKING]** A database's or crate's entries are now printed by its `print()` method, rather than given by `repr()`.
  - **Upgrading:** Call `db.print()` or `crate.print()` in place of `print(repr(...))`.
- **[BREAKING]** `Crate.add_track` and `include_tracks_from_folder` take a track's full path, and store it as Serato does: from the root of its drive, with `/` separators. Before, `add_track` took a path relative to the folder holding `_Serato_`, and stored it that way, with the OS's separators, and `include_tracks_from_folder` stored only the folder's name and the file's.
  - **Upgrading:** Pass the track's full path. `remove_track` takes the path as the crate stores it, as `tracks()` gives it.
- **[BREAKING]** A crate's `path`, `filename`, and `track_path` attributes are replaced by `filepath` (the crate file's full path), `dir` (its folder), and `track_dir`.
  - **Upgrading:** Read `filepath`, `dir`, or `track_dir`.
- **[BREAKING]** A crate's boolean entries, such as its sort's `brev` (reverse order), are read as `bool` rather than as raw bytes, and must be a `bool` to save.
  - **Upgrading:** Compare them with `True` or `False`, and set them to a `bool`.
- **[BREAKING]** `remove_drive_from_filepath(path)` on the database and crates, which returned `(path, drive)`, is renamed `format_filepath(path)`, and returns the path alone, as Serato stores it.
  - **Upgrading:** Call `format_filepath`, and `os.path.splitdrive` for the drive.
- **Fix:** Fix a database rule's `files` never matching a track on macOS and Linux, and a track path set through a rule on `pfil` (as `rename_track_file` does) being stored with a leading `/` there, or with `\` separators on Windows. Paths are now stored as Serato stores them: from the root of the drive, with `/` separators.

## [2.2.1] - 2025-05-13

### Database / Crates / Track Tags

- **[BREAKING] Removed:** The `print_changes` argument of `DatabaseV2.modify`, `modify_file`, and `rename_track_file`, and of `TrackCuesV2.modify_entries` and `set_track_color`. Each change is logged instead, at `INFO` level to the `serato-tools` logger, which Python doesn't show unless logging is configured to.
  - **Upgrading:** Drop the argument. To see the changes, configure logging, e.g. `logging.basicConfig(level=logging.INFO)`.
- **Feature:** Messages are logged to the `serato-tools` logger (`serato_tools.utils.logger`) rather than printed, so they can be hidden, e.g. with `logging.getLogger("serato-tools").setLevel(logging.ERROR)`.

### Database / Crates

- **[BREAKING] Removed:** `DatabaseV2.print_data()` and `Crate.print_data()`.
  - **Upgrading:** `print(repr(db))` or `print(repr(crate))` prints the same.

### Track Tags

- **Feature:** Add `TrackCuesV2.get_track_color()`, the track's color as bytes, or None for a track without one, and `get_track_color_name()`, its key in `TrackCuesV2.TRACK_COLORS`.
- **Feature:** The tag classes open an `.aiff` file by its path, as they did an `.mp3`, and take any open mutagen ID3 file or bare `ID3` tags, not just an `MP3` or `AIFF`.

## [2.1.0] - 2025-05-08

### Track Tags

- **Feature:** Add `delete()` to each tag class and to `TrackGain`, which removes the tag from the open file without saving it. A tag class's `delete()` returns whether the tag was there. Save the file through its `tagfile` (`tags.tagfile.save()`) to write the deletion.

## [2.0.0] - 2025-05-08

### Database / Crates

- **[BREAKING]** `DatabaseV2.data_bin` is renamed `raw_data`.
  - **Upgrading:** Read `raw_data`.

### Track Tags

- **[BREAKING]** Each tag module's functions are replaced by a class: `TrackCuesV2`, `TrackCuesV1`, `TrackBeatgrid`, `TrackAutotags`, `TrackWaveform`, and `TrackGain`. Each is constructed from a file path (an `.mp3`), an open mutagen `MP3` or `AIFF`, or, except `TrackGain`, the tag's raw bytes, and reads its tag when constructed. A tag class's `save()` writes the tag back to the file, and its `GEOB_KEY` and `VERSION` are class attributes.
  - **Upgrading:**
    - `track_cues_v2`: `modify_file_entries(file, rules)` is now `TrackCuesV2(file).modify_entries(rules)`, and `set_track_color(file, color)` is `TrackCuesV2(file).set_track_color(color)`. Call `save()` after them, since they no longer save. `CUE_COLORS`, `TRACK_COLORS`, the entry classes (`CueEntry`, `ColorEntry`, ...), the rule types, and `parse_entries_file` move onto `TrackCuesV2` (e.g. `TrackCuesV2.TRACK_COLORS`). A tag's parsed entries are its `entries`, in place of `parse(data)`, and `is_beatgrid_locked(entries)` is `TrackCuesV2(file).is_beatgrid_locked()`.
    - `track_cues_v1`: Read `TrackCuesV1(file).entries` in place of `parse(fp)`. `Entry`, `Color`, and `EntryType` move onto `TrackCuesV1`.
    - `track_beatgrid`: Read `TrackBeatgrid(file).entries` in place of `parse(fp)`, and call `TrackBeatgrid(file).analyze_and_write()` in place of `analyze_and_write(file)`. The marker types move onto `TrackBeatgrid`.
    - `track_autotags`: Read `bpm`, `autogain`, and `gaindb` from `TrackAutotags(file)` in place of `parse(fp)`, and change them with `set(bpm=..., autogain=..., gaindb=...)` and then `save()`, in place of `dump(...)`.
    - `track_waveform`: Call `TrackWaveform(file).draw_image()` in place of `draw_waveform(parse(fp))`.
    - `track_gain`: Read `gain` and `peak` from `TrackGain(file)`, and set them with `set_and_save(gain, peak)`, in place of the `REPLAY_GAIN_GAIN_KEY` and `REPLAY_GAIN_PEAK_KEY` constants.
- **[BREAKING] Removed:** `get_geob`, `tag_geob`, `del_geob`, `del_tag`, `check_version`, and `pack_version` in `serato_tools.utils.track_tags`, which the tag classes now handle themselves.
  - **Upgrading:** Read and write each tag through its class. To delete a frame, delete it through mutagen, e.g. `del tagfile["GEOB:Serato Markers_"]`.
- **[BREAKING] (CLI)** `python -m serato_tools.track_beatgrid` now prints a track's beatgrid markers, and analyzes and writes a new beatgrid only with `-e` / `--analyze`. Before, it always analyzed an audio file.
  - **Upgrading:** Pass `--analyze` to analyze the track.
- **Feature:** `TrackCuesV2.set_track_color` also takes a key of `TrackCuesV2.TRACK_COLORS`, such as `"purple"`, and `TrackCuesV2.save()` writes only when the cues changed, unless passed `force=True`.
- **Fix:** Fix `is_beatgrid_locked` returning None for every track. It now returns whether the track's beatgrid is locked.

## [1.18.0] - 2025-04-30

### Database / Crates / Track Cues

- **[BREAKING]** `DataTypeError` moves to `serato_tools.utils`, from a class nested in the database and crate classes (`DatabaseV2.DataTypeError` and `Crate.DataTypeError`).
  - **Upgrading:** Import it with `from serato_tools.utils import DataTypeError`.

### Track Cues

- **Feature:** Add typed rules for `modify_file_entries`: `CueIndexModifyRule`, `ColorModifyRule`, and `CueNameModifyRule`, whose `func` takes and returns an `int`, `bytes`, or `str`.
- **Feature:** A rule on a cue's or the track's `color`, or on a cue's `index` or `name`, raises `DataTypeError` when its `func` returns a value of the wrong type, rather than writing it.

## [1.17.3] - 2025-04-28

### Packaging

- **[BREAKING]** `mutagen` is no longer installed with the package. It's in the new `track_tags` extra, which anything reading or writing a track's tags needs (cues, beatgrid, autotags, gain, and waveform).
  - **Upgrading:** Install with `pip install "serato-tools[track_tags]"`.
- **Docs:** Add the repository and issue tracker links to the project's PyPI page, and an installation section to the README that lists the optional dependencies each feature needs.

### Database / Crates

- **[BREAKING]** `DatabaseV2.to_objects()` and `print_items()` are renamed `to_dicts()` and `print_data()`.
  - **Upgrading:** Call `to_dicts()` and `print_data()`.
- **[BREAKING]** `DatabaseV2.modify_file` raises for two rules on one field (`AssertionError`), or for a rule on a field it doesn't know, one not in `DatabaseV2.FIELDNAMES` (`ValueError`). It also prints each change by default.
  - **Upgrading:** Combine a field's rules into one `func`, and pass `print_changes=False` to keep it quiet.
- **[BREAKING]** `DatabaseV2.data` yields `(field, length, value)` for each entry, without the entry's raw bytes.
  - **Upgrading:** Unpack three values rather than four.
- **Feature:** Add `DatabaseV2.rename_track_file(src, dest)`, which renames a track's file and changes its path in the database to match, so the track isn't left missing in Serato.
- **Feature:** Add `DatabaseV2.modify(rules)`, which changes the database in memory, and `write_file(out_file=None)`, which saves it. `modify_file` does both.
- **Feature:** A `modify_file` rule now also sets a field the track doesn't have yet, adding it, with None passed to `func` as the previous value. A rule on the track's path (`pfil`) raises `FileNotFoundError` for a file that doesn't exist, and stores the path without its drive.
- **Feature:** Writing a database value of the wrong type for its field raises `DataTypeError` naming the field, as crates already did.
- **Feature:** `Crate.print_data()` prints each entry with its field's name, rather than the raw nested data, and the new `Crate.to_dicts()` gives the entries as dicts with their field names.
- **Feature (CLI):** `python -m serato_tools.crate` takes `-d` / `--data` to print the crate's entries.
- **Fix:** Fix the database's text fields reading and writing characters outside Latin-1 (such as Japanese or Cyrillic) as garbled text. They're now read and written as the UTF-16 Serato stores.

### Track Tags

- **[BREAKING]** `serato_tools.utils.tags` is renamed `serato_tools.utils.track_tags`.
  - **Upgrading:** Import `get_geob`, `tag_geob`, `del_geob`, and `del_tag` from `serato_tools.utils.track_tags`.
- **[BREAKING]** A tag of an unexpected version raises `ValueError` naming the expected and given versions, rather than `AssertionError`.
  - **Upgrading:** Catch `ValueError`.
- **[BREAKING]** Each tag module's `FMT_VERSION` is removed, and the cue entry classes' `FMT` (`FlipEntry`'s `FMT1` to `FMT3`) is renamed `FORMAT` (`FORMAT1` to `FORMAT3`).
  - **Upgrading:** Use `FORMAT`, `VERSION_FORMAT` in `serato_tools.utils.track_tags`, or the module's `VERSION_BYTES`, its tag's version.
- **[BREAKING] (CLI)** `python -m serato_tools.track_tagdump` takes the audio file first and the output folder second, and the folder is optional: without it, each tag's value is printed rather than written to a file.
  - **Upgrading:** Swap the arguments: `python -m serato_tools.track_tagdump <file> <output_dir>`.
- **Feature:** `del_geob` and `del_tag` return whether the tag was there to delete.

### Track Cues

- **[BREAKING]** `modify_entry`, and so `modify_file_entries`, raises `AssertionError` for two rules on one field, rather than applying both.
  - **Upgrading:** Combine a field's rules into one `func`.
- **Fix:** `modify_file_entries` and `set_track_color` no longer save a file when every rule returned the value already there. `modify_entry` prints each change by default, as `modify_file_entries` already did.

## [1.15.0] - 2025-04-22

### Database

- **[BREAKING]** `serato_tools.database_v2`'s functions move onto a new `DatabaseV2` class, which parses the file when it's constructed. `DatabaseV2(filepath)` defaults to the library's `database V2`, and raises `FileNotFoundError` when the file doesn't exist.
  - **Upgrading:** Replace `modify_file(rules, file)` with `DatabaseV2(file).modify_file(rules)`, and `parse_to_objects(file)` with `DatabaseV2(file).to_objects()`. `FIELDNAMES`, `ModifyRule`, and `DATABASE_FILE` are now `DatabaseV2.FIELDNAMES`, `DatabaseV2.ModifyRule`, and `DatabaseV2.DEFAULT_DATABASE_FILE`.
- **[BREAKING] Removed:** The module-level `parse` and `modify`, which are now internal to `DatabaseV2`.
  - **Upgrading:** Read the database through `DatabaseV2.to_objects()`, and change it through `DatabaseV2.modify_file`.
- **Feature:** `DatabaseV2.modify_file` takes an `out_file`, to write the changed database to another file rather than over its own.
- **Feature:** Add `DatabaseV2.print_items`, which prints each entry with its field name and size, as the `database_v2` CLI does.

### Crates

- **[BREAKING]** `Crate.track_path()` is now a `track_path` attribute, and `Crate.crate_path` and `Crate.name` are renamed `path` and `filename`.
  - **Upgrading:** Replace `crate.track_path()` with `crate.track_path`, `crate.crate_path` with `crate.path`, and `crate.name` with `crate.filename`.
- **[BREAKING]** `Crate.remove_track` raises `ValueError` when the track isn't in the crate, rather than returning False, and `Crate.add_track` returns None rather than whether it added the track.
  - **Upgrading:** Catch `ValueError` where you checked `remove_track`'s result. To know whether `add_track` will add a track, check whether it's in `crate.tracks()` first.
- **[BREAKING]** `Crate.include_tracks_from_folder` only adds the folder's tracks, and no longer removes the crate's other tracks unless passed `replace=True`.
  - **Upgrading:** Pass `replace=True` to make the crate hold only the folder's tracks, as before.
- **Feature:** Saving a crate with a value of the wrong type for its field raises `Crate.DataTypeError`.
- **Feature (CLI):** `python -m serato_tools.crate` takes `-o` / `--output`, to save the crate to another file.

## [1.14.2] - 2025-04-19

### Database / Track Tags

- **[BREAKING]** The `database` and `track` subpackages are removed, and their modules move back to the top of the package, as before 1.8.1.
  - **Upgrading:** Import `serato_tools.database_v2` in place of `serato_tools.database.database_v2`, and `serato_tools.<module>` in place of `serato_tools.track.<module>` (e.g. `serato_tools.track_cues_v2`).

### Database

- **Feature:** `modify_file` and `modify` take `print_changes`, to print each value they change.

### Crates

- **Feature:** Add crates: `serato_tools.crate`'s `Crate` reads a `.crate` file, or starts a new one, and saves it (`save_to_file`). It also lists the crate's tracks (`tracks()`), and adds and removes them (`add_track`, `remove_track`, and `include_tracks_from_folder`).
- **Feature (CLI):** `python -m serato_tools.crate <file>` prints a crate's tracks, or only their filenames with `-f` / `--filenames_only`.

### Track Tags

- **[BREAKING]** In `track_cues_v2`, `change_entry` is renamed `modify_entry`, and its rules' type `EntryModifyCriteria` is renamed `EntryModifyRule`, with its `value_modify` key renamed `func`. `modify_entry` returns None when no rule changed the entry.
  - **Upgrading:** Call `modify_entry` with rules of `{"field": ..., "func": ...}`, and keep the original entry when it returns None.
- **[BREAKING] (CLI)** `python -m serato_tools.track_beatgrid <file>` given an audio file analyzes the track and overwrites its beatgrid, rather than printing it. Given a file that isn't audio, such as a dumped tag, it still prints the markers.
  - **Upgrading:** To print an audio file's beatgrid, dump its tags with `python -m serato_tools.track_tagdump <output_dir> <file>`, then pass the dumped `Serato BeatGrid` file to `track_beatgrid`.
- **Feature:** Add `modify_file_entries(file, rules)` to `track_cues_v2`. It changes an MP3 file's `Serato Markers2` cue and track color entries with `EntryModifyRules` (`{"cues": [...], "color": [...]}`), and saves the file when anything changed. The file is a path or an open `MP3`. By default (`delete_tags_v1=True`) it also deletes the file's `Serato Markers_` tag, without which Serato doesn't show the changes. It changes nothing in a file without a `Serato Markers2` tag.
- **Feature:** Add `set_track_color(file, color)` to `track_cues_v2`, which sets an MP3 file's track color to one of the `TRACK_COLORS`, deleting its `Serato Markers_` tag as `modify_file_entries` does.
- **Feature:** Add `get_cue_color_key` and `get_track_color_key` to `track_cues_v2`, which give a color's name in `CUE_COLORS` or `TRACK_COLORS`.
- **Feature:** Add beatgrid analysis. `serato_tools.utils.beatgrid_analyze.analyze_beatgrid` detects a track's BPM, beats, and downbeats. `track_beatgrid.analyze_and_write` writes a beatgrid from them, with a marker every 4 beats and the BPM from the track's `TBPM` tag. Both need the new `beatgrid_analysis` extra (`librosa` and `numpy`). `track_beatgrid` also gains `write`, which serializes beatgrid markers.
- **Feature (CLI):** Add the `analyze_beatgrid` console script, which analyzes an audio file and writes its beatgrid.
  - NOTE: It fails to start, since it names the wrong module, until 3.2.10 fixes it as `serato_analyze_beatgrid`. Use `python -m serato_tools.track_beatgrid` until then.
- **Feature (CLI):** `python -m serato_tools.track_cues_v2 <file> --set_color <name>` sets the track color to the `TRACK_COLORS` entry with that name.

## [1.8.1] - 2025-04-11

### Database / Track Tags

- **[BREAKING]** The modules move into `database` and `track` subpackages, and the track tag modules are renamed after what they hold.
  - **Upgrading:** Update your imports:
    - `serato_tools.database_v2` is now `serato_tools.database.database_v2`.
    - `serato_tools.serato_markers2` is now `serato_tools.track.track_cues_v2`, and `serato_tools.serato_markers_` is now `serato_tools.track.track_cues_v1`.
    - `serato_tools.serato_beatgrid`, `serato_autotags`, `serato_gain`, and `serato_overview` are now `serato_tools.track.track_beatgrid`, `track_autotags`, `track_gain`, and `track_waveform`.
    - `serato_tools.tagdump` is now `serato_tools.track.track_tagdump`.

## [1.7.0] - 2025-04-11

### Database

- **[BREAKING]** `modify_file` takes `rules` first and `file` second, and `file` defaults to the library's `database V2` (`DATABASE_FILE`).
  - **Upgrading:** Pass `rules` first, or pass both by keyword (`modify_file(rules=..., file=...)`).
- **Feature:** Name the `tcmp` (Composer) and `bcrt` (Corrupt) fields in `FIELDNAMES`, so the `database_v2` CLI shows their names.
- **Fix:** A rule's `files` match a track given as a full Windows path with its drive (`C:\Music\track.mp3`), since the database stores paths without one.

### Documentation

- **Docs:** Add README examples of modifying the database file and a track's cues.

## [1.6.2] - 2025-04-11

### Database

- **Feature:** A `modify_file` rule (`ModifyRule`) takes an optional `files` list, to change its field only for those tracks. Paths match whatever their case.

## [1.5.2] - 2025-04-11

### Packaging

- **Fix:** Install the package as `serato_tools`, so it can be imported (e.g. `import serato_tools.database_v2`). 1.5.1 installed it as `serato-tools`, which isn't a valid module name.

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
