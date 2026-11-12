# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Conventions

The repo's conventions live in `conventions/` and are imported here in full — they apply to all work in this repo, and everything below extends them. Keep this file consistent with them: nothing here should ever contradict a convention.

@conventions/all.md

`conventions/` is synced automatically from `bvandrc/bvandrc-conventions` by `.github/workflows/sync-conventions.yml`. The workflow deletes and recreates the directory on every run, so edits made here are lost — change them upstream. When a sync adds a new file to `conventions/`, add a matching `@conventions/<file>` import to this section.

## Commands

Requires Python 3.12+ (the code uses PEP 695 `type` statements, which are a syntax error on 3.11).

Work in the repo's `.venv` (gitignored), with the package installed editable so `serato_tools` imports resolve to `src/` rather than some other installed copy:

```bash
python -m venv .venv
source .venv/Scripts/activate                                     # Git Bash on Windows; .venv/bin/activate elsewhere
pip install -e ".[all,dev]"                                  # all optional deps + black, isort, pylint, pyright
```

```bash
python -m unittest                                                # full suite
python -m unittest test.test_crate                                # one module
python -m unittest test.test_crate.TestCase.test_add_tracks_is_saved  # one test
pylint $(git ls-files '*.py')                                     # lint (config in .pylintrc, most C/R checks disabled)
pyright                                                           # type check (config in pyproject.toml)
isort .                                                           # sort imports (config in pyproject.toml)
black .                                                           # format, line-length 120
```

This is a Python repo with no package manager scripts, so `isort .` then `black .` is the "format script" the conventions require before every commit; CI checks both.

Tests import the installed `serato_tools` (editable locally, a regular install in CI) and open fixtures by paths relative to the repo root, so `python -m unittest` only works from there.

CI (`.github/workflows/ci.yml`) runs two jobs: `Lint` (pylint and pyright, plus isort and black once) on ubuntu-latest, and `Test` on windows-latest, macos-latest, and ubuntu-latest, both across Python 3.12-3.15.
- **Lint on every version:** neither tool pins one, and both check against the running interpreter, so 3.12 catches use of anything newer and later versions catch deprecations and removals.
- **Required checks:** the `main` ruleset requires these checks by name, so renaming a job or matrix entry means updating the ruleset too.
- **OS-specific tests:** tests that only make sense on one OS (drive letters, backslash separators, POSIX mount points) are skipped on the others with `unittest.skipUnless` / `skipIf`, with a matching test for the other OS family.

Bump `version` in `pyproject.toml` and add a `CHANGELOG.md` entry for user-visible changes. End every sentence of a changelog entry with a period, the last one included, so an entry of two sentences doesn't end one with a period and not the other. Publishing a GitHub release then publishes that version to PyPI, through `.github/workflows/release.yml`:
- **Tag:** it must be `v` + the version (e.g. `v6.0.0`), or the workflow fails before building.
- **Notes:** a release published with empty notes gets the version's `CHANGELOG.md` section as its notes, and the built distributions are attached to it.
- **Trusted publisher:** PyPI's names that workflow file and its `pypi` environment, so renaming either means updating it on PyPI too.

## Architecture

The package handles two unrelated Serato binary formats. Nearly everything else is a subclass of one of the two base classes.

### 1. Serato bin container — `utils/bin_file_base.py`

`SeratoBinFile` parses the format used by the library database and crate files (`database V2`, `.crate`, `.scrate`).
- **Entries:** the container is a flat/nested sequence of entries: an 8-byte header (`>4sI` — 4-char ASCII field name, big-endian length) followed by the payload.
- **Value types:** **the value type is derived from the first character of the field name**, not from any type byte: `o`/`r` → nested struct, `p`/`t` → UTF-16-BE text, `b` → bool, `s` → u16, `u` → u32. `vrsn` is special-cased as text.

Subclasses (`DatabaseV2`, `CrateBase` → `Crate` / `SmartCrate`):
- **Required attributes:** they must define `TESTED_VERSIONS`, `TRACK_PATH_KEY`, and `DEFAULT_ENTRIES`; the constructor raises `AttributeError` if any is missing.
- **Field names:**
  - Common ones live in the `SeratoBinFile.Fields` StrEnum. Fields whose meaning is only guessed are listed in a comment there, unnamed, rather than given a name that may be wrong.
  - The smart-crate-only fields (rules and their values) live in `SmartCrate.RuleFields`.
  - Each class lists its valid set in `FIELD_ENUMS`, with the `FIELDS` frozenset derived from it, so a rule field in a database or regular crate is rejected.
- **Smart crate rule values:** a rule holds exactly one of the `RULE_VALUE_FIELDS`, picked by its comparison's type suffix (`cond_*_str`/`_time`/`_uint`), never by the value's Python type. `set_rule` and `Rule.set_value` coerce the value to match, as Serato does.

The lifecycle is `parse → self.entries → change through the class's methods → to_bytes() → save()`:

- The file's bytes aren't stored. Each `to_bytes()` call serializes `entries` from scratch, so changes cost nothing and each `save()` pays for one serialization. Change a file through its methods (`modify_tracks`, `modify`, `filter_tracks`, `add_tracks`, ...), not by editing `entries` directly, and point callers and docs at those methods too. (The `SeratoGeobTag` classes below do store theirs, in the internal `_raw_data`.)
- The read-only `has_changed` property compares a hash of `to_bytes()` with one of the bytes the file was loaded from or last saved to its own path (`_saved_hash`).
  - It sees in-place edits too, and a file that didn't exist yet counts as changed.
  - Load hashes the bytes it already read rather than copying `entries`, so a read-only use pays next to nothing for it, and each `has_changed` call pays one serialization instead.
  - A file loaded from JSON is serialized once at load for its hash.
- `save(file=None, force=False)` writes to the file's own path only if its bytes differ from that hash, unless `force`, and returns whether it wrote. Saving to another path ("save as", e.g. `usb_export`) always writes. It serializes once, to check and to write. `CrateBase` overrides it to also check the file's extension.
- `modify_tracks`, `modify`, `change_track_path`, `filter_tracks`, `remove_tracks`, and `remove_duplicates` return whether anything changed. Methods that save on the caller's behalf (`modify_and_save`, `find_missing`, and `Library`'s methods) use that to skip even `save()`'s serialization when nothing changed.
- `modify()` takes a list of `ModifyRule` dicts (`{"field": ..., "func": (filename, prev_val) -> new_val | None, "files": [...]}`); returning `None` from `func` means "leave unchanged". A `func` returning `""` removes the field, as does a track entry's `set_value` with `""` (through its `remove_field`), since Serato removes a tag's field when the tag is cleared rather than storing it empty.
- `modify_tracks(func, files=...)` and `modify()` with every rule limited to `files` skip every other track after reading only its path, which keeps single-track edits fast on a large library.
- `add_tracks` / `remove_tracks` are the batch track APIs (one pass each); the singular `add_track` / `remove_track` are deprecated and delegate to them.
- Files can also round-trip through JSON (`to_json_object` / `from_json_object` / `write_json`), with bytes base64-encoded.

### 2. GEOB tags inside audio files — `utils/track_tags.py`

- **`ID3File`** is the open mutagen file type (an `ID3FileType` such as `MP3`, an `AIFF`, or bare `ID3` tags; none is a subclass of another).
- **`ID3FileTag`** is a value stored in an `ID3File`'s tags: it only holds the file (`tagfile`, opened by `open_tagfile`), and has nothing Serato-specific.
- **Module functions** (`get_geob`, `set_geob`, `del_geob`, `del_tag`) read and write frames on any open file, for code that needs a frame other than its own (`TrackCuesV2` deleting `Serato Markers_`, `track_tagdump.py`).
- **Saving:** every tag class's `save()` writes only if the tag changed since it was read or last saved (`has_changed`), unless `force`, and returns whether it wrote.
  - It's `ID3FileTag.save()`, which writes through the class's `_write_to_tagfile()`; only `TrackCuesV2` overrides it, for `delete_tags_v1`. A forced save of an unchanged tag puts nothing in the tagfile, so it can't restore a frame another tag sharing it deleted.
  - So other unsaved changes to a tagfile a caller passed in (frames set on it directly, or by another tag object sharing it) are only written along with one of the tag's own. The `save()` docstrings and README say to save the tagfile when `save()` returns False; there's no way to detect them, as mutagen has no unsaved-changes flag.
- **`SeratoGeobTag`** subclasses `ID3FileTag`, holding everything GEOB-specific (its own frame, the version check and packing, `_readbytes`). There's one class per GEOB tag, each declaring `GEOB_KEY` and `VERSION` and implementing `_parse` / `_serialize`:

| Class | GEOB tag | Module |
| --- | --- | --- |
| `TrackCuesV2` | `Serato Markers2` — hotcues, loops, flips, track color, BPM lock | `track_cues_v2.py` |
| `TrackCuesV1` | `Serato Markers_` — legacy equivalent | `track_cues_v1.py` |
| `TrackBeatgrid` | `Serato BeatGrid` | `track_beatgrid.py` |
| `TrackAutotags` | `Serato Autotags` — BPM/gain | `track_autotags.py` |
| `TrackWaveform` | `Serato Overview` | `track_waveform.py` |

Each of these accepts *either* a file path / mutagen tagfile *or* raw `bytes` (`SeratoGeobTag.FileOrData`). The bytes path is what lets tests feed the `.bin` fixtures in `test/data/` without an audio file, and it's why `self.tagfile` may be `None` — `save()` raises in that case.

`TrackGain` (`track_gain.py`) subclasses `ID3FileTag` directly, since Serato stores gain as an ID3 `RVA2:SeratoGain` frame rather than a GEOB.

`TrackTextFrames` (`track_text_frames.py`) also subclasses `ID3FileTag`: it gets and sets ID3 text frames (`TIT2`, `TBPM`, ...), adding a missing frame, and writes only frames whose text changed.
- **Naming a frame:** by its ID, or through its `Fields` StrEnum, named as `DatabaseV2.Fields` names the field holding the same value (`Fields.TITLE` is `"TIT2"`).
- **Setting:** `""` removes the frame, and setting a frame replaces all its values. `set` takes only a text frame stored under its bare ID (not `TXXX`, which its description keys too), or `COMM` for the comment. It raises for text it wouldn't read back, such as:
  - a `TDRC` that isn't a date;
  - a numeric `TCON` genre, which loading turns into a name;
  - an ID3v2.3-only frame, which loading converts or drops.
- **The comment (`COMM`, `Fields.COMMENT`):**
  - `get` gives the file's first comment frame, as Serato shows it.
  - `set` puts the comment in the `COMM` frames Serato writes, found by setting one in Serato: `('', 'eng')`, Latin-1 when the text fits and UTF-16 otherwise, plus `('ID3v1 Comment', 'eng')` only for Latin-1 text.
  - `read_comment` / `write_comment` read and change the comment in `tagfile` directly, without saving, for code such as an `EasyID3` key's getter and setter.

`Track` (`track.py`) isn't a tag itself (no base class): it parses each of these, `TrackGain`, and `TrackTextFrames`, from one open `ID3File` in its constructor.
- **Which tags:** a keyword flag per tag chooses which it parses (`cues_v2`, `cues_v1`, `beatgrid`, `autotags`, `gain`, `text_frames` default True, `waveform` False). A tag passed False is never constructed, so it's neither parsed nor saved, and its property raises ValueError naming the flag.
- **Saving:** its `save()` writes every change in one `tagfile.save()`, skipping it when nothing changed, and its read-only `has_changed` says beforehand whether it would write.
- **What each tag class implements:**
  - the read-only `has_changed` property;
  - `_write_to_tagfile()`, which puts its unsaved changes into the shared tagfile without saving and returns whether it had any. A `SeratoGeobTag` compares its data (`_raw_data`) with what it read or last saved (`_tagged_raw_data`) rather than with the tagfile, so an unchanged `Serato Markers_` that `TrackCuesV2` deleted isn't put back. `TrackCuesV2._write_to_tagfile` alone takes an argument, `delete_tags_v1`, which `Track.save()` passes it.
- **Adding a tag class:** implement both (`ID3FileTag`'s raise `NotImplementedError`; it isn't an ABC, so it can still be instantiated), which `save()` is built on, and add it to `Track`: a flag, a property, and an entry in `save()`'s tuple of parsed tags.

**v1/v2 interaction:** current Serato reads `Serato Markers2`, but a stale `Serato Markers_` shadows changes made to it.
- That's why `TrackCuesV2.save()` and `Track.save()` (and `Library.set_db_tracks_tags`, which passes it on) take `delete_tags_v1=True` by default: writing `Serato Markers2` deletes the v1 tag rather than keeping the two in sync.
- It's a save option, not an edit option, because the deletion happens only when `TrackCuesV2` writes (in its `_put_in_tagfile`, which `_write_to_tagfile` and `save` pass it to). So an edit that changed nothing, or was changed back, can't have it written by another tag's save.
- The edit methods (`modify_entries`, `set_track_color`, `set_beatgrid_locked`, on `TrackCuesV2` and `Track`) still accept a deprecated `delete_tags_v1`. `modify_entries` warns, with `skip_file_prefixes` so the warning points at the caller's code, and records a False in `_edits_keep_tags_v1`, which keeps the v1 tag at the next write unless another edit since the last write didn't pass False.

`TrackCuesV2` exposes each entry kind (`CueEntry`, `LoopEntry`, `ColorEntry`, `FlipEntry`, `BpmLockEntry`) as a dataclass, aggregated into `TrackCuesInfo`.
- **Editing:** `modify_entries(callback)` hands the callback the whole `TrackCuesInfo` and expects a new one back (use `dataclasses.replace`) or `None` for no change.
- **Converting:** each entry class (and `TrackCuesV1.Entry`) converts with `_parse()` / `_serialize()`, which are internal to its module. Callers go through `modify_entries` and `save()`, so the tag class and its CLI are the only users, and pylint's `protected-access` is disabled per function where they're called.

### Version gating

Both bases refuse unknown formats: `SeratoBinFile._check_version` rejects any `vrsn` not in `TESTED_VERSIONS`, and `SeratoGeobTag._check_version` rejects any tag version != `VERSION`. This is deliberate — writing a misparsed file would corrupt a user's library. Adding support for a new version means adding the version string *and* a fixture + round-trip test, not just widening the check.

### Cross-module dependencies

- Each tag class reads and writes only its own tag: one that needs another tag's data is passed that tag, never reads it from its own file.
  - **Cue snapping** is `TrackCuesV2.snap_cues_to_beats(beatgrid, ...)`, which moves the cues through `modify_entries` to where the `TrackBeatgrid` passed in puts them. `get_snapped_position`, which reads only the beatgrid, lives on `TrackBeatgrid`, and `track_cues_v2.py` imports `TrackBeatgrid` only for type checking.
  - **`Track.snap_cues_to_beats`** passes the track's own beatgrid, so both tags come from one open file, as `Track`'s other cue edits pass through to `cues_v2`.
  - **The `serato_snap_cues_v2` CLI** (`track_cues_v2:main`) reads a `TrackBeatgrid` from its open file only for `--snap_cues`.
- `Library` (`library.py`) holds one library folder's `DatabaseV2`, `Crate`s, and `SmartCrate`s, each parsed on first use and then kept.
  - **Whole-library operations:** `rename_track_file` and `remove_track_files` change the files on disk and update every one of them that contains the track, saving only those.
    - Each returns the paths of the library files it changed, which inside `batch()` aren't written until the block ends: `rename_track_file` as a list, and `remove_track_files` as its `RemoveTrackFilesResult`'s `library_files_changed`, beside `files_deleted`. `rename_track_file` raises `FileExistsError` rather than overwrite a different file at `dest`.
    - Smart crates are included because Serato re-adds a missing path from a smart crate to the database as a blank "?" entry.
    - New operations that have to reach the whole library (database and every crate) belong on `Library`, not on `DatabaseV2`.
    - Pass `Library(database=...)` an already-loaded database so the two don't overwrite each other's saves.
  - **Saving:** `Library.save()` writes each parsed file whose `has_changed` is true.
    - It saves changes made through `library.database`'s or the crates' own methods, such as `modify`.
    - **Batching:** inside `with library.batch():`, `rename_track_file`, `remove_track_files`, and `set_db_tracks_tags` change the files in memory without writing them (`_save_unless_batching`), and `batch()` calls `save()` when the outermost block ends, so many changes write each file once.
      - It saves in a `finally`, even when the block raises, since the track files were already changed on disk and the library has to point at them.
      - Nested batches count depth (`_batch_depth`), so only the outermost one saves.
      - A new `Library` method that saves has to go through `_save_unless_batching` too.
  - **Values in both the track file and the database:** `set_db_track_tags` / `set_db_tracks_tags` set values that live in both (Serato shows the database, and only rescans a file's tags when the track is loaded or on "Rescan File Tags").
    - **Which values:** the keys of the `DbTrackTags` TypedDict in `db_track_props.py`, each backed by an entry in its `_DB_TRACK_PROPS` table, so adding a value means adding to both. Each entry gives:
      - the database field;
      - the conversion to the database's form (e.g. a `TrackCuesV2.TrackColors` value as a `0xRRGGBB` int for `COLOR`);
      - how to write it through the file's `Track`.
    - **Order of writes:**
      - Each file is opened once, as a `Track`, and written with its one `save()`.
      - Every value is converted for the database, and every file read and changed in memory, before any file is saved, so a bad value or unreadable file changes nothing.
      - Every file is written before the database, which is saved once, in one `modify_tracks` pass.
    - **A track not in the database** only has its file's tags set, with a warning.
    - **Optional extra:** `Library` reaches `db_track_props` only through `_db_track_props()`, which imports it on first use and raises an ImportError naming the extra without it, so the rest of `Library` doesn't need the optional `track_tags` extra.
- `usb_export.py` composes `Crate`, `SmartCrate`, and `DatabaseV2`: it flattens all tracks into one folder on the drive, dedupes by basename, rewrites crate/database paths to the new layout, and copies only changed files.
- `SERATO_DIR` (`~/Music/_Serato_`) in `utils/__init__.py` is the default root for all library lookups.

### CLI conventions

Console scripts are declared in `[project.scripts]` in `pyproject.toml` and point at `main()` / `main_analyze()` in the module. Each entry point defines a local `@dataclass Args` and constructs it with `Args(**vars(parser.parse_args()))` to get a typed view of argparse output — follow that pattern when adding a CLI. To run a module directly, use `python -m serato_tools.<module>`.

## Repository layout notes

- `test/helpers.py` — shared test setup: temp copies of the test mp3 (`temp_mp3`, `untagged_mp3`, cleaned up with the test) and `read_bytes`. Tests of a base class's behaviour go in the base's own module (`test_bin_file_base.py`, `test_track_tags.py`), driven through one subclass or looped over all of them, not repeated per subclass.
- `test/data/` — fixtures for the unittest suite. Tests assert **byte-exact** round-trips (parse → serialize must reproduce the input), so regenerate fixtures deliberately, never to make a test pass.
- `data/` — reference dumps of raw GEOB tags captured from real tracks, organized by container (`id3`, `flac`, `mp4`, `aif`, `ogg`) and scenario (`hotcue-colors`, `saved-loops`, `bpmlock`, ...). Used as evidence for the format writeups in `docs/`, not by the test suite. Committed as binary via `.gitattributes`.
- `docs/` — per-tag format documentation; `docs/fileformats.md` covers how each container stores the tags.
- `conventions/` — see [Conventions](#conventions) above; imported, not editable in place.
