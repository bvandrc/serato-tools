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
pip install -e ".[all,dev]"                                  # all optional deps + black, pylint, pyright
```

```bash
python -m unittest                                                # full suite
python -m unittest test.test_crate                                # one module
python -m unittest test.test_crate.TestCase.test_add_tracks_is_saved  # one test
pylint $(git ls-files '*.py')                                     # lint (config in .pylintrc, most C/R checks disabled)
pyright                                                           # type check (config in pyproject.toml)
black .                                                           # format, line-length 120
```

This is a Python repo with no package manager scripts, so `black .` is the "format script" the conventions require before every commit; CI enforces it with `psf/black@stable`.

Tests import the installed `serato_tools` (editable locally, a regular install in CI) and open fixtures by paths relative to the repo root, so `python -m unittest` only works from there.

CI (`.github/workflows/ci.yml`) runs two jobs: `Lint` (pylint and pyright, plus black once) on ubuntu-latest, and `Test` on windows-latest, macos-latest, and ubuntu-latest, both across Python 3.12-3.15. Lint runs on every version because neither tool pins one: both check against the running interpreter, so 3.12 catches use of anything newer and later versions catch deprecations and removals. The `main` ruleset requires these checks by name, so renaming a job or matrix entry means updating the ruleset too. Tests that only make sense on one OS (drive letters, backslash separators, POSIX mount points) are skipped on the others with `unittest.skipUnless` / `skipIf`, with a matching test for the other OS family.

Publishing to PyPI is a manual `workflow_dispatch` of `.github/workflows/build-and-publish.yml`. Bump `version` in `pyproject.toml` and add a `CHANGELOG.md` entry for user-visible changes.

## Architecture

The package handles two unrelated Serato binary formats. Nearly everything else is a subclass of one of the two base classes.

### 1. Serato bin container — `utils/bin_file_base.py`

`SeratoBinFile` parses the format used by the library database and crate files (`database V2`, `.crate`, `.scrate`). The container is a flat/nested sequence of entries: an 8-byte header (`>4sI` — 4-char ASCII field name, big-endian length) followed by the payload. **The value type is derived from the first character of the field name**, not from any type byte: `o`/`r` → nested struct, `p`/`t` → UTF-16-BE text, `b` → bool, `s` → u16, `u` → u32. `vrsn` is special-cased as text.

Subclasses (`DatabaseV2`, `CrateBase` → `Crate` / `SmartCrate`) must define `TESTED_VERSIONS`, `TRACK_PATH_KEY`, and `DEFAULT_ENTRIES`; the constructor raises `AttributeError` if any is missing. Common field names live in the `SeratoBinFile.Fields` StrEnum (fields whose meaning is only guessed are listed in a comment there, unnamed, rather than given a name that may be wrong); the smart-crate-only fields (rules and their values) live in `SmartCrate.RuleFields`, and each class lists its valid set in `FIELD_ENUMS`, with the `FIELDS` frozenset derived from it, so a rule field in a database or regular crate is rejected. A smart crate rule holds exactly one of the `RULE_VALUE_FIELDS`, picked by its comparison's type suffix (`cond_*_str`/`_time`/`_uint`), never by the value's Python type — `set_rule` and `Rule.set_value` coerce the value to match, as Serato does.

The lifecycle is `parse → self.entries → mutate → to_bytes() → save()`:

- The file's bytes aren't stored. Each `to_bytes()` call serializes `entries` from scratch, so mutations cost nothing and each `save()` pays for one serialization. Edit `entries` however you like, in place or by assignment. (The `SeratoGeobTag` classes below do store theirs, in `_raw_data`; the read-only `raw_data` getter is deprecated for removal in the next major version.)
- The read-only `has_changed` property compares a hash of `to_bytes()` with one of the bytes the file was loaded from or last saved to its own path (`_saved_hash`), so it sees in-place edits too; a file that didn't exist yet counts as changed. Load hashes the bytes it already read rather than copying `entries`, so a read-only use pays next to nothing for it, and each `has_changed` call pays one serialization instead. A file loaded from JSON is serialized once at load for its hash.
- `modify_tracks`, `modify`, `change_track_path`, `filter_tracks`, `remove_tracks`, and `remove_duplicates` return whether anything changed. Methods that save on the caller's behalf (`modify_and_save`, `find_missing`, and `Library`'s methods) use that to skip writing an unchanged file. `save()` itself always writes, since it doubles as "save as".
- `modify()` takes a list of `ModifyRule` dicts (`{"field": ..., "func": (filename, prev_val) -> new_val | None, "files": [...]}`); returning `None` from `func` means "leave unchanged". A `func` returning `""` removes the field, as does a track entry's `set_value` with `""` (through its `remove_field`), since Serato removes a tag's field when the tag is cleared rather than storing it empty.
- `modify_tracks(func, files=...)` and `modify()` with every rule limited to `files` skip every other track after reading only its path, which keeps single-track edits fast on a large library.
- `add_tracks` / `remove_tracks` are the batch track APIs (one pass each); the singular `add_track` / `remove_track` are deprecated for removal in the next major version and delegate to them.
- Files can also round-trip through JSON (`to_json_object` / `from_json_object` / `write_json`), with bytes base64-encoded.

### 2. GEOB tags inside audio files — `utils/track_tags.py`

`ID3File` is the open mutagen file type (an `ID3FileType` such as `MP3`, an `AIFF`, or bare `ID3` tags; none is a subclass of another). `ID3FileTag` is a value stored in an `ID3File`'s tags: it only holds the file (`tagfile`, opened by `open_tagfile`), and has nothing Serato-specific. Module functions (`get_geob`, `set_geob`, `del_geob`, `del_tag`) read and write frames on any open file, for code that needs a frame other than its own (`TrackCuesV2` deleting `Serato Markers_`, `track_tagdump.py`). `SeratoGeobTag` subclasses it, holding everything GEOB-specific (its own frame, the version check and packing, `_readbytes`), one class per GEOB tag, each declaring `GEOB_KEY` and `VERSION` and implementing `_parse` / `_serialize`:

| Class | GEOB tag | Module |
| --- | --- | --- |
| `TrackCuesV2` | `Serato Markers2` — hotcues, loops, flips, track color, BPM lock | `track_cues_v2.py` |
| `TrackCuesV1` | `Serato Markers_` — legacy equivalent | `track_cues_v1.py` |
| `TrackBeatgrid` | `Serato BeatGrid` | `track_beatgrid.py` |
| `TrackAutotags` | `Serato Autotags` — BPM/gain | `track_autotags.py` |
| `TrackWaveform` | `Serato Overview` | `track_waveform.py` |

Each of these accepts *either* a file path / mutagen tagfile *or* raw `bytes` (`SeratoGeobTag.FileOrData`). The bytes path is what lets tests feed the `.bin` fixtures in `test/data/` without an audio file, and it's why `self.tagfile` may be `None` — `save()` raises in that case.

`TrackGain` (`track_gain.py`) subclasses `ID3FileTag` directly, since Serato stores gain as an ID3 `RVA2:SeratoGain` frame rather than a GEOB. The two bases were named `SeratoTrack` and `SeratoTag` before 5.4.0 (and their file types `SeratoTrack.Tagfile` / `FileArg`); a module `__getattr__` in `utils/track_tags.py` still gives the old names, with a `DeprecationWarning`, until the next major version.

`Track` (`track.py`) isn't a tag itself (no base class): it parses each of these, and `TrackGain`, from one open `ID3File` in its constructor, choosing which with a keyword flag per tag (`cues_v2`, `cues_v1`, `beatgrid`, `autotags`, `gain` default True, `waveform` False). A tag passed False is never constructed, so it's neither parsed nor saved, and its property raises ValueError naming the flag. Its `save()` writes every change in one `tagfile.save()`, skipping it when nothing changed, and its read-only `has_changed` says beforehand whether it would write. Each tag class implements the read-only `has_changed` property, and `_write_to_tagfile()`, which puts its unsaved changes into the shared tagfile without saving and returns whether it had any; a `SeratoGeobTag` compares its data (`_raw_data`) with what it read or last saved (`_tagged_raw_data`) rather than with the tagfile, so an unchanged `Serato Markers_` that `TrackCuesV2` deleted isn't put back. `TrackCuesV2._write_to_tagfile` alone takes an argument, `delete_tags_v1`, which `Track.save()` passes it. A new tag class has to implement both (`ID3FileTag`'s raise `NotImplementedError`; it isn't an ABC, so it, and the deprecated `SeratoTrack`, can still be instantiated) and be added to `Track`: a flag, a property, and an entry in `save()`'s tuple of parsed tags.

**v1/v2 interaction:** current Serato reads `Serato Markers2`, but a stale `Serato Markers_` shadows changes made to it. That's why `TrackCuesV2.save()` and `Track.save()` (and `Library.set_db_tracks_tags`, which passes it on) take `delete_tags_v1=True` by default — writing `Serato Markers2` deletes the v1 tag rather than keeping the two in sync. It's a save option, not an edit option, because the deletion happens only when `TrackCuesV2` writes (in its `_put_in_tagfile`, which `_write_to_tagfile` and `save` pass it to), so an edit that changed nothing, or was changed back, can't have it written by another tag's save. The edit methods (`modify_entries`, `set_track_color`, `set_beatgrid_locked`, on `TrackCuesV2` and `Track`) still accept a deprecated `delete_tags_v1` until the next major version: `modify_entries` warns, with `skip_file_prefixes` so the warning points at the caller's code, and records a False in `_edits_keep_tags_v1`, which keeps the v1 tag at the next write unless another edit since the last write didn't pass False.

`TrackCuesV2` exposes each entry kind (`CueEntry`, `LoopEntry`, `ColorEntry`, `FlipEntry`, `BpmLockEntry`) as a dataclass, aggregated into `TrackCuesInfo`; `modify_entries(callback)` hands the callback the whole `TrackCuesInfo` and expects a new one back (use `dataclasses.replace`) or `None` for no change. Each entry class (and `TrackCuesV1.Entry`) converts with `_parse()` / `_serialize()`, which are internal to its module: callers go through `modify_entries` and `save()`, so the tag class and its CLI are the only users. Pylint's `protected-access` is disabled per function where they're called.

### Version gating

Both bases refuse unknown formats: `SeratoBinFile._check_version` rejects any `vrsn` not in `TESTED_VERSIONS`, and `SeratoGeobTag._check_version` rejects any tag version != `VERSION`. This is deliberate — writing a misparsed file would corrupt a user's library. Adding support for a new version means adding the version string *and* a fixture + round-trip test, not just widening the check.

### Cross-module dependencies

- `TrackCuesV2` cue snapping reads the track's `TrackBeatgrid` to find beat positions.
- `Library` (`library.py`) holds one library folder's `DatabaseV2`, `Crate`s, and `SmartCrate`s, each parsed on first use and then kept. Its `rename_track_file` and `remove_track_files` change the files on disk and update every one of them that contains the track, saving only those. Smart crates are included because Serato re-adds a missing path from a smart crate to the database as a blank "?" entry. The deprecated `DatabaseV2.rename_track_file` calls it with its own database. New operations that have to reach the whole library (database and every crate) belong on `Library`, not on `DatabaseV2`; pass `Library(database=...)` an already-loaded database so the two don't overwrite each other's saves.
  - `set_db_track_tags` / `set_db_tracks_tags` set values that live both in the track file's tags and in the database (Serato shows the database, and only rescans a file's tags when the track is loaded or on "Rescan File Tags"). The values are the keys of the `DbTrackTags` TypedDict in `db_track_props.py`, each backed by an entry in its `_DB_TRACK_PROPS` table giving the database field, the conversion to the database's form (e.g. a `TrackCuesV2.TrackColors` value as a `0xRRGGBB` int for `COLOR`), and how to write it through the file's `Track`; adding a value means adding to both. Each file is opened once, as a `Track`, and written with its one `save()`. Every value is converted for the database, and every file read and changed in memory, before any file is saved, so a bad value or unreadable file changes nothing; every file is written before the database, which is saved once, in one `modify_tracks` pass. A path that isn't in the database only has its file's tags set, with a warning. `Library` reaches `db_track_props` only through `_db_track_props()`, which imports it on first use and raises an ImportError naming the extra without it, so the rest of `Library` doesn't need the optional `track_tags` extra.
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
