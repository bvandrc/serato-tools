# Changelog

Each release groups its changes by the part of the package they're in. Within each part, the most significant changes come first, and each **[BREAKING]** one says how to upgrade past it.

## [Unreleased]

### USB Export

- **Fix:** Tracks that share a filename are all exported, rather than only the first (a later one goes in a subfolder named after its own folder).
- **Fix:** The drive keeps your crate order, with a root crate or smart crates.
  - Before, Serato couldn't use the order file the export wrote, and on Windows it was garbled.
  - The order lists only the exported crates, with the root crate first.
- **Feature:** `copy_crates_to_usb`'s `dest_tracks_dir` defaults to `Tracks`, the folder `serato_usb_export` uses.
- **Fix:** An export with a crate file it can't read fails before writing anything to the drive, rather than after deleting the drive's `_Serato_` folder.

### Crate Order

- **Feature:** Add `CrateOrder` (`serato_tools.crate_order`), which reads and writes Serato's crate order file, `neworder.pref`, so you can reorder, add, or remove crates in it.
- **Feature (CLI):** Add `serato_crate_order`, which prints a library's crate order, or sets it from a text file of crate names.

## [6.0.2] - 2026-11-24

### Smart Crates

- **Fix:** `SmartCrate.Rule` raises `ValueError` for a rule with no comparison or track field, or one this package doesn't know, rather than failing later or never.
  - `set_rule` and `delete_rule` keep such a rule as it is when it's on another field, rather than raising `AttributeError` for one with no track field.
  - `Rule.remove_field` refuses the comparison and track field.

## [6.0.1] - 2026-11-24

### Library

- **[BREAKING]** `Library.set_unanalyzed` is renamed `Library.delete_analysis`, and its result `SetUnanalyzedResult` is renamed `DeleteAnalysisResult`, since it deletes the analysis from the files, unlike `DatabaseV2.set_unanalyzed`.
  - **Upgrading:** Call `delete_analysis` where you called `Library.set_unanalyzed`.

## [6.0.0] - 2026-11-21

### Library

- **Feature:** `Library.set_db_track_tags` / `set_db_tracks_tags` now also set a track's metadata in its ID3 text frames and the database: `title`, `artist`, `album`, `genre`, `key`, `grouping`, `publisher`, `composer`, `year`, `remixer`, `track_number`, `disc_number`, and `comment`.
  - An empty value removes it from both.
- **Feature:** Add `Library.save`, which writes each of the library's parsed files that has changed, and returns their paths.
- **Feature:** Add `Library.batch()`, a context manager inside which `Library`'s methods write each changed database and crate file once, when the block ends, rather than once per track.
  - It still saves if the block raises.
- **Feature:** Add `Library.set_unanalyzed`, which deletes tracks' analysis from their files (waveform, beatgrid, autotags, and gain) and marks them not yet analyzed, so Serato analyzes them again.
  - A track with a locked beatgrid raises `ValueError`, unless `include_locked`, which unlocks it.
  - `Track.delete_analysis` does the files' part for one track, and `DatabaseV2.set_unanalyzed` the database's.
- **[BREAKING]** `Library.set_db_track_tags` / `set_db_tracks_tags` return a `DbTrackTagsResult` rather than a bool: `database_changed`, as the bool was, and `files_written`, the paths of the track files written.
  - **Upgrading:** Read `.database_changed` where you used the bool, since the result is always truthy.
- **[BREAKING]** `Library.rename_track_file` returns the paths of the database, crates, and smart crates it changed, rather than a bool, and raises `FileExistsError` when a different file already exists at `dest`, rather than logging an error and returning False.
  - **Upgrading:** Catch `FileExistsError` where you checked for False. It renamed the file whenever it returns, even with an empty list (when no library file held the track), so drop a check for True.
- **Feature:** `Library.remove_track_files` now returns a `RemoveTrackFilesResult`, with the track files it deleted (`files_deleted`) and the library files it changed (`library_files_changed`).
- **Feature:** Add `Library.crate_files`, the paths of the library's crate and smart crate files, listed without parsing them.
- **[BREAKING]** `Library.set_db_track_tags` / `set_db_tracks_tags` raise only `DataTypeError` for a color that isn't a `TrackCuesV2.TrackColors`, no longer also `AttributeError`.
  - **Upgrading:** Catch `DataTypeError`.

### Database / Crates / Track Tags

- **[BREAKING]** `save()` on the database, crates, and smart crates, and on `TrackCuesV1`, `TrackBeatgrid`, `TrackAutotags`, and `TrackWaveform`, now skips writing when nothing changed since the file or tag was loaded or last saved.
  - These, and every other tag class's `save()`, now return whether they wrote.
  - Saving a database or crate to another path always writes.
  - **Upgrading:** Pass `force=True` to write anyway, e.g. to overwrite a file changed on disk since it was loaded. If you passed a tag class a tagfile with other unsaved changes, and relied on its `save()` to write them, save the tagfile yourself when `save()` returns False.
- **[BREAKING]** A malformed database, crate, or Serato tag raises only `ValueError`, as does a number too big or negative for its field.
  - Before, some of these raised `AssertionError` or `struct.error`, or, for a database or crate with no version entry, `AttributeError`.
  - **Upgrading:** Catch `ValueError`.
- **[BREAKING]** `serato_tools.utils.ui` is renamed `serato_tools.utils.cli`.
  - **Upgrading:** Import from `serato_tools.utils.cli`.

### Database / Crates

- **[BREAKING] Removed:** The methods earlier releases deprecated.
  - **Upgrading:**
    - For `add_track` and `remove_track` (deprecated in 5.1.0), use `add_tracks` and `remove_tracks`.
    - For `DatabaseV2.rename_track_file` (5.2.0), use `Library.rename_track_file`.
    - For a track's `get_full_path()` (5.8.0), use its `full_path` property.
    - For `get_entries_filtered(track_matcher)` (5.8.0), use `get_entries(track_matcher)`.
- **[BREAKING]** `Crate(path)` and `SmartCrate(path)` raise `FileNotFoundError` for a file that doesn't exist, rather than warning and starting an empty crate.
  - `SmartCrate.to_regular_crate` raises `FileExistsError` for a file that already exists.
  - **Upgrading:** Start a new crate with `Crate.new(path)` or `SmartCrate.new(path)`, which `save()` then writes.
- **[BREAKING]** A database's or crate's `entries` and `version` are now internal.
  - **Upgrading:** Change a file through its methods (`modify_tracks`, `modify`, `add_tracks`, `set_rule`, ...), and read it through `get_entries`, `get_tracks`, or `to_json_object`. Its version is the `vrsn` entry `get_entries` gives.
- **Feature:** A database or crate track's, or a smart crate rule's, `set_value` raises `DataTypeError` for a value of the wrong type, and `ValueError` for an out-of-range number, when it's set rather than only when the file is saved.
  - `modify_tracks` and `modify` now check the tracks they change too.
- **Feature (CLI):** `serato_smartcrate` now takes each rule field as its own option, e.g. `serato_smartcrate Dubstep.scrate --grouping str_is UNTAGGED --year DELETE`.
  - A bad field, comparison, value, or number of arguments is rejected before any crate is changed.
- **[BREAKING] Removed (CLI):** `serato_smartcrate`'s `--set_rules`.
  - **Upgrading:** Pass the rule options directly, without it.
- **Fix:** Printing a smart crate shows a rule comparison or field this package doesn't know, such as one a newer Serato wrote, as `(unknown)` rather than raising `ValueError`.
- **[BREAKING]** `DataTypeError` and `DeeplyNestedListError` move from `serato_tools.utils` to `serato_tools.utils.bin_file_base`.
  - **Upgrading:** Import them from `serato_tools.utils.bin_file_base`.
- **Feature:** A smart crate rule's `comparison` is typed as `str` and its `field` as `int`, rather than as any value an entry can hold.

### Track Tags

- **[BREAKING] Removed (CLI):** The CLIs' edit modes: `-e` / `--edit` on `serato_snap_cues_v2`, `python -m serato_tools.track_cues_v1`, and `python -m serato_tools.track_autotags`.
  - `TrackCuesV2.parse_entries_file`, which read the edit mode's text, is removed with them.
  - **Upgrading:** Change a tag through its class's methods instead, such as `TrackCuesV2.modify_entries` and `set_track_color`, or `TrackAutotags.set`.
- **[BREAKING] Removed:** The names earlier releases deprecated.
  - **Upgrading:**
    - For the tag classes' read-only `raw_data` (deprecated in 5.1.1), parse, modify, and serialize through each tag's own methods.
    - For the `SeratoTrack` and `SeratoTag` names in `serato_tools.utils.track_tags` (5.4.0), use `ID3FileTag` and `SeratoGeobTag`.

### Track Text Frames

- **Feature:** Add `TrackTextFrames` (`serato_tools.track_text_frames`), which reads and sets a track file's ID3 text frames, and `Track.text_frames`.
  - `TrackTextFrames.Fields` names the frames Serato shows a column for (`Fields.TITLE`, `Fields.GENRE`, etc.).
  - `Fields.COMMENT` gets and sets the comment the way Serato does.
  - Setting a frame to `""` removes it.

### Track Cues

- **Feature:** Add `Track.snap_cues_to_beats(tolerance_beats)`, which snaps a track's cues to its beatgrid in memory and returns each move, as a `SnappedCue`.
  - `TrackCuesV2.snap_cues_to_beats(beatgrid, tolerance_beats)` does the same with the `TrackBeatgrid` passed to it.
  - `TrackBeatgrid.get_snapped_position` gives the position a single cue would snap to.
- **[BREAKING] Removed:** `TrackCuesV2` no longer reads the beatgrid from its own file for cue snapping; its methods that did are removed: `snap_positions_to_beat`, `snap_positions_to_beat_rule`, `get_snapped_beat_ms`, and `get_beat_position`.
  - **Upgrading:**
    - For `snap_positions_to_beat` and `snap_positions_to_beat_rule`, use `Track.snap_cues_to_beats`, or `TrackCuesV2.snap_cues_to_beats(beatgrid, ...)`. Both return the moves rather than printing them. There's no rule to pass to `modify_entries`: snap, then make any other edits, before saving.
    - For `get_snapped_beat_ms`, use `TrackBeatgrid.get_snapped_position` (e.g. `track.beatgrid.get_snapped_position`).
    - For `get_beat_position(entry)`, use `beatgrid.get_beat_position(entry.position)`.
- **[BREAKING]** `TrackCuesV1`'s entries are now dataclasses, and `TrackCuesV1.Color` is no longer a subclass of `TrackCuesV1.Entry`.
  - Entries with the same values compare equal, and can't be hashed (put in a set or used as a dict key).
  - **Upgrading:** Check for `TrackCuesV1.Color` too where `isinstance(entry, TrackCuesV1.Entry)` meant every entry. Key a dict by an entry's index in `entries` rather than the entry.
- **[BREAKING] Removed:** The `FIELDS` tuple on `TrackCuesV2`'s and `TrackCuesV1`'s entry classes.
  - **Upgrading:** Use `dataclasses.fields`: `[f.name for f in dataclasses.fields(TrackCuesV2.CueEntry)]`.
- **[BREAKING] Removed:** `TrackCuesV2.modified`, deprecated in 5.6.0.
  - **Upgrading:** Use `has_changed`.
- **Feature (CLI):** `serato_snap_cues_v2 --snap_cues` now says which cue each move was for, and which tag is missing for a track without cues or a beatgrid.
- **Deprecated:** Passing `delete_tags_v1` to an edit method isn't removed yet: it stays deprecated until a future major release. Pass it to `save()` instead.
- **Fix:** `TrackCuesV1.Entry`'s `type` is typed as the `TrackCuesV1.EntryType` it holds, rather than `bytes | str`.

### Track Beatgrid

- **Feature:** Add `TrackBeatgrid.is_dynamic`, whether a beatgrid has more than one marker.
- **[BREAKING]** `TrackBeatgrid.find_nearest_beat` raises `NoBeatgridError` without a beatgrid, rather than returning None.
  - **Upgrading:** Catch `NoBeatgridError` where you checked for None.

### Track Waveform

- **[BREAKING]** `TrackWaveform` (and `Track(waveform=True)`) loads from a file Serato hasn't built a waveform for, with `data` None, rather than raising `NoWaveformError`.
  - `draw_image()` raises it instead.
  - **Upgrading:** Check `data is None` where you caught `NoWaveformError` on construction.

### USB Export

- **[BREAKING]** `get_crate_files`, and so `serato_usb_export --crate_matcher`, match a pattern against the crate's name, without its extension.
  - Before, `"*crate*"` matched every crate, through the extension.
  - **Upgrading:** Drop the extension from your patterns (`"house*"`, not `"house*.crate"`). A pattern can no longer pick crates or smart crates by extension.
- **[BREAKING]** `copy_crates_to_usb`, and so `serato_usb_export`, raise `FileNotFoundError` when none of the crates' tracks are found, rather than logging an error.
  - **Upgrading:** Catch `FileNotFoundError` if you call `copy_crates_to_usb`.
- **Feature:** USB export shows a progress bar while it copies tracks.
  - The package now installs `tqdm` for it.

## [5.8.1] - 2026-11-18

### USB Export

- **Fix:** No more "File does not exist" warning for each smart crate exported, from `SmartCrate.to_regular_crate`.
  - A damaged crate left on the drive is now replaced, rather than stopping the export.
- **Fix:** The progress percentage now reaches 100%.

## [5.8.0] - 2026-11-18

### Database / Crates

- **Feature:** `get_entries` on the database, crates, and smart crates now takes an optional `track_matcher`, a regex, and then gives only the tracks whose path it matches, ignoring case.
  - **Deprecated:** `get_entries_filtered(track_matcher)`, in favor of `get_entries(track_matcher)`. It still works until 6.0 removes it.
- **Feature:** Add a `full_path` property to a database or crate track: its absolute path.
  - **Deprecated:** A track's `get_full_path()`, in favor of `full_path`. It still works until 6.0 removes it.
- **Feature:** `SmartCrate.delete_rule` now returns whether the crate had a rule on that field to remove.
- **Fix:** A database or crate track's `relpath`, and a smart crate rule's `comparison`, `field`, and `value`, now read the track's or rule's current entries, so they no longer keep a value set through `set_value` or removed through `remove_field`. In particular, a `modify()` rule after one that changes a track's path now gets the new path. They're now read-only: change one through `set_path`, `set_value`, or the rule's setters.
- **Fix:** Setting a track's path to a value that isn't text, through `set_value`, now raises `DataTypeError`.
- **Fix:** `modify_tracks`, and so `modify`, now change no track when `func` raises for one, rather than keeping the changes to the tracks before it.
- **Fix:** A crate's `add_tracks`, and so `add_tracks_from_dir`, now skip a track already in the crate in another casing, and `remove_duplicates` removes a repeat of a track's path in another casing. Before, a crate could hold one track twice, under paths differing only in case.

### Track Tags

- **Feature:** `TrackBeatgrid`'s markers, `Footer`, and `BeatPoint` are typed as `NamedTuple`s, so type checkers know their fields' types, such as `position_s: float`.
- **Fix:** `TrackBeatgrid.analyze_and_write` now keeps the old grid when the analysis gives one Serato wouldn't write, such as downbeats out of order.
- **Fix (CLI):** `serato_snap_cues_v2 -e` now keeps an entry you leave unchanged after the editor fails or the content is invalid, and now works on Windows.
- **Fix (CLI):** `serato_tagdump` now exits saying a file has no tags, rather than with a traceback.

### Library

- **Fix:** `Library.set_db_track_tags` / `set_db_tracks_tags` now raise `DataTypeError` (as well as still `AttributeError`) for a color that isn't a `TrackCuesV2.TrackColors`, before changing any file.
  - **Deprecated:** Catching that error as `AttributeError`. It still works until 6.0, where it's only a `DataTypeError`.

## [5.7.0] - 2026-11-15

### Database / Crates / Track Tags

- **Feature:** Clearer error types:
  - A cut-off or malformed database, crate, or tag now raises `ValueError` (as well as still `AssertionError`) saying what's wrong.
  - A number too big or negative for its field now raises `ValueError` (as well as still `struct.error`) naming the field.
  - Errors that were a bare `Exception` are now a `ValueError`, `TypeError`, `FileNotFoundError`, or `ImportError` saying what's wrong.
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

- **Feature:** `TrackCuesV2.save()` and `Track.save()` take `delete_tags_v1` (default True), which deletes the legacy `Serato Markers_` tag when `Serato Markers2` is written, since a stale one stops the change from appearing in Serato. `Library.set_db_track_tags` and `set_db_tracks_tags` pass theirs to it.
- **[BREAKING]** Any write of `Serato Markers2` now deletes `Serato Markers_` by default, not only one after `modify_entries`, `set_track_color`, `set_beatgrid_locked`, or `snap_positions_to_beat`: that includes the `serato_snap_cues_v2 --edit` CLI, a forced save, and saving a deleted `Serato Markers2`.
  - **Upgrading:** Pass `delete_tags_v1=False` to `save()` where you need `Serato Markers_` kept.
- **Fix:** Fix `TrackCuesV2.save()` skipping the save, and losing a change, when an edit that changed nothing followed one that did.
- **Fix:** `TrackCuesV2` deletes the `Serato Markers_` tag only when it writes a change to `Serato Markers2`. An edit that changed nothing, or was changed back, used to delete it from the file in memory, and saving another tag in the same file would write the deletion.
- **Fix:** Fix `TrackCuesV1` failing to serialize a tag with an unset cue or loop position, as every `Serato Markers_` tag Serato writes has.
- **[BREAKING] Deprecated:** `TrackCuesV2.modified` is deprecated in favor of `has_changed`, and will be removed in the next major version. Until then it's read-only and returns `has_changed`, so an edit that changes nothing no longer resets it.
  - **Upgrading:** Stop assigning `modified`, which now raises, and read `has_changed` instead.
- **Deprecated:** Passing `delete_tags_v1` to an edit method (`modify_entries`, `set_track_color`, etc.) is deprecated in favor of passing it to `save()`, and will be removed in the next major version.
  - Until then, passing False still keeps `Serato Markers_` at the next save, unless another edit since the last save didn't pass False.

## [5.5.0] - 2026-11-06

### Library

- **Feature:** Add `Library.set_db_track_tags` and `set_db_tracks_tags`, which set a track's color and beatgrid lock in its tags and in the database at once, so Serato shows the change right away, without rescanning file tags. Only ID3 files (.mp3, .aiff, .aif) are currently supported.
- **Feature:** `Library.rename_track_file` returns whether it renamed the file. It returns False when a different file already exists at `dest`, which it still only logs.

### Database / Crates

- **Feature:** Add `ModifyFunc` (e.g. `DatabaseV2.ModifyFunc`), the type of a `ModifyRule`'s `func`, to annotate your own functions with.

### Track Cues

- **[BREAKING] Fix:** `TrackCuesV2` raises ValueError for a `COLOR`, `BPMLOCK`, `CUE`, or `LOOP` entry unlike any Serato writes. That includes a cue past 8, and it raises on saving one too.
  - **Upgrading:** Catch `ValueError` when reading tags you don't control, and remove any cue past 8 before saving.
- **Fix:** Changing a track's cues keeps its BPM lock before its flips, the order Serato writes them in.
- **Fix:** `TrackCuesV2` writes the `Serato Markers2` tag byte for byte as Serato does: its base64 ends as Serato's does, and it keeps the size the tag already had rather than shrinking it.
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

- **Fix:** Fix cue snapping moving almost every cue by 1 ms since 5.1.1: the default of 1 caught the 1 ms gap Serato commonly leaves between a cue and the rounded beat. The default `min_ms_change` is now 2, so 1 ms differences are left alone again, and passing less than 2 warns.

## [5.3.0] - 2026-11-03

### Database / Crates

- **Feature:** Name more database track fields, so they're printed with a name instead of `Unknown Field`, and can be used in `DatabaseV2.modify`: `COMMENT`, `REMIXER`, `TRACK_NUMBER`, `DISC_NUMBER`, `PLAY_COUNT`, `COLOR` (the track color, as `0xRRGGBB`), `CORRUPT_REASON`, `READ_ONLY`, and `OVERVIEW_BUILT` (waveform created).
  - The smart crate field holding the on/off value of "match all" and "live update" is named too: `SmartCrate.RuleFields.SETTING_VALUE`.
- **Feature:** Add `DatabaseV2.get_corrupt_tracks`, and `--list_corrupt` to the database CLI, which list the tracks Serato marked corrupt along with the reason Serato gives.

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

- **Fix:** `modify_tracks` and `modify()` no longer re-encode the file when no track changed.

## [4.0.3] - 2026-10-31

### Database / Crates

- **Fix:** `DatabaseV2.rename_track_file` rewrites only the crates that contain the track, instead of every crate.
- **Fix:** `get_full_path` now keeps a path's drive instead of dropping it.

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

- **Feature (CLI):** Add the `serato_crate` and `serato_smartcrate` commands, which take a crate file, a folder of crates, or `--all`.
- **[BREAKING] Removed (CLI):** The crate and smart crate CLIs' `-o` / `--output` option, which saved the crate to another file.
  - **Upgrading:** Call the crate's `save(file)`.

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
- **Feature:** Add `get_track_paths()`, `modify_tracks(func)`, `filter_tracks(func)`, `remove_track(filepath)`, and `remove_duplicates()` to the database, crates, and smart crates.
- **[BREAKING]** `str()` of a crate gives its entries rather than its tracks, and the crate CLIs print them by default, without `-d`.
  - **Upgrading:** Use `get_track_paths()`, or the CLI's `-l`, for the tracks.
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

- **[BREAKING]** The modules move into `database` and `track` subpackages, and the tag modules are now named after what they hold (e.g. `serato_markers2` → `track_cues_v2`).
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

[Unreleased]: https://github.com/bvandrc/serato-tools/compare/v6.0.2...HEAD
[6.0.2]: https://github.com/bvandrc/serato-tools/compare/v6.0.1...v6.0.2
[6.0.1]: https://github.com/bvandrc/serato-tools/compare/v6.0.0...v6.0.1
[6.0.0]: https://github.com/bvandrc/serato-tools/compare/v5.8.1...v6.0.0
[5.8.1]: https://github.com/bvandrc/serato-tools/compare/v5.8.0...v5.8.1
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
