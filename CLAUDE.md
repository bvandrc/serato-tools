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
python -m unittest test.test_crate.TestCase.test_format_filepath  # one test
pylint $(git ls-files '*.py')                                     # lint (config in .pylintrc, most C/R checks disabled)
pyright                                                           # type check (config in pyproject.toml)
black .                                                           # format, line-length 120
```

This is a Python repo with no package manager scripts, so `black .` is the "format script" the conventions require before every commit; CI enforces it with `psf/black@stable`.

Tests import via `from src.serato_tools...`, so `python -m unittest` only works from the repo root.

CI (`.github/workflows/ci.yml`) runs two jobs: `Lint` (pylint and pyright, plus black once) on ubuntu-latest, and `Test` on windows-latest, macos-latest, and ubuntu-latest, both across Python 3.12-3.15. Lint runs on every version because neither tool pins one: both check against the running interpreter, so 3.12 catches use of anything newer and later versions catch deprecations and removals. The `main` ruleset requires these checks by name, so renaming a job or matrix entry means updating the ruleset too. Tests that only make sense on one OS (drive letters, backslash separators, POSIX mount points) are skipped on the others with `unittest.skipUnless` / `skipIf`, with a matching test for the other OS family.

Publishing to PyPI is a manual `workflow_dispatch` of `.github/workflows/build-and-publish.yml`. Bump `version` in `pyproject.toml` and add a `CHANGELOG.md` entry for user-visible changes.

## Architecture

The package handles two unrelated Serato binary formats. Nearly everything else is a subclass of one of the two base classes.

### 1. Serato bin container — `utils/bin_file_base.py`

`SeratoBinFile` parses the format used by the library database and crate files (`database V2`, `.crate`, `.scrate`). The container is a flat/nested sequence of entries: an 8-byte header (`>4sI` — 4-char ASCII field name, big-endian length) followed by the payload. **The value type is derived from the first character of the field name**, not from any type byte: `o`/`r` → nested struct, `p`/`t` → UTF-16-BE text, `b` → bool, `s` → u16, `u` → u32. `vrsn` is special-cased as text.

Subclasses (`DatabaseV2`, `CrateBase` → `Crate` / `SmartCrate`) must define `TESTED_VERSIONS`, `TRACK_PATH_KEY`, and `DEFAULT_ENTRIES`; the constructor raises `AttributeError` if any is missing. Common field names live in the `SeratoBinFile.Fields` StrEnum (fields whose meaning is only guessed are listed in a comment there, unnamed, rather than given a name that may be wrong); the smart-crate-only fields (rules and their values) live in `SmartCrate.RuleFields`, and each class lists its valid set in `FIELD_ENUMS`, with the `FIELDS` frozenset derived from it, so a rule field in a database or regular crate is rejected. A smart crate rule holds exactly one of the `RULE_VALUE_FIELDS`, picked by its comparison's type suffix (`cond_*_str`/`_time`/`_uint`), never by the value's Python type — `set_rule` and `Rule.set_value` coerce the value to match, as Serato does.

The lifecycle is `parse → self.entries → mutate → to_bytes() → save()`:

- The file's bytes aren't stored. Each `to_bytes()` call serializes `entries` from scratch, so mutations cost nothing and each `save()` pays for one serialization. Edit `entries` however you like, in place or by assignment. (The `SeratoTag` classes below do store theirs, in `_raw_data`; the read-only `raw_data` getter is deprecated for removal in the next major version.)
- `modify_tracks`, `modify`, `change_track_path`, `filter_tracks`, `remove_tracks`, and `remove_duplicates` return whether anything changed. Methods that save on the caller's behalf (`modify_and_save`, `find_missing`, and `Library`'s methods) use that to skip writing an unchanged file. `save()` itself always writes, since it doubles as "save as".
- `modify()` takes a list of `ModifyRule` dicts (`{"field": ..., "func": (filename, prev_val) -> new_val | None, "files": [...]}`); returning `None` from `func` means "leave unchanged".
- `modify_tracks(func, files=...)` and `modify()` with every rule limited to `files` skip every other track after reading only its path, which keeps single-track edits fast on a large library.
- `add_tracks` / `remove_tracks` are the batch track APIs (one pass each); the singular `add_track` / `remove_track` are deprecated for removal in the next major version and delegate to them.
- Files can also round-trip through JSON (`to_json_object` / `from_json_object` / `write_json`), with bytes base64-encoded.

### 2. GEOB tags inside audio files — `utils/track_tags.py`

`SeratoTrack` wraps a mutagen file and reads/writes `GEOB:<key>` frames. `SeratoTag` subclasses it, one class per GEOB tag, each declaring `GEOB_KEY` and `VERSION` and implementing `_parse` / `_serialize`:

| Class | GEOB tag | Module |
| --- | --- | --- |
| `TrackCuesV2` | `Serato Markers2` — hotcues, loops, flips, track color, BPM lock | `track_cues_v2.py` |
| `TrackCuesV1` | `Serato Markers_` — legacy equivalent | `track_cues_v1.py` |
| `TrackBeatgrid` | `Serato BeatGrid` | `track_beatgrid.py` |
| `TrackAutotags` | `Serato Autotags` — BPM/gain | `track_autotags.py` |
| `TrackWaveform` | `Serato Overview` | `track_waveform.py` |

Each of these accepts *either* a file path / mutagen tagfile *or* raw `bytes` (`SeratoTag.FileOrData`). The bytes path is what lets tests feed the `.bin` fixtures in `test/data/` without an audio file, and it's why `self.tagfile` may be `None` — `save()` raises in that case.

**v1/v2 interaction:** current Serato reads `Serato Markers2`, but a stale `Serato Markers_` shadows changes made to it. That's why the mutating APIs (`TrackCuesV2.modify_entries`, `set_track_color`, `set_beatgrid_locked`) take `delete_tags_v1=True` by default — they delete the v1 tag rather than keeping the two in sync.

`TrackCuesV2` exposes each entry kind (`CueEntry`, `LoopEntry`, `ColorEntry`, `FlipEntry`, `BpmLockEntry`) as a dataclass, aggregated into `TrackCuesInfo`; `modify_entries(callback)` hands the callback the whole `TrackCuesInfo` and expects a new one back (use `dataclasses.replace`) or `None` for no change. Each entry class (and `TrackCuesV1.Entry`) converts with `_parse()` / `_serialize()`, which are internal to its module: callers go through `modify_entries` and `save()`, so the tag class and its CLI are the only users. Pylint's `protected-access` is disabled per function where they're called.

### Version gating

Both bases refuse unknown formats: `SeratoBinFile._check_version` rejects any `vrsn` not in `TESTED_VERSIONS`, and `SeratoTag._check_version` rejects any tag version != `VERSION`. This is deliberate — writing a misparsed file would corrupt a user's library. Adding support for a new version means adding the version string *and* a fixture + round-trip test, not just widening the check.

### Cross-module dependencies

- `TrackCuesV2` cue snapping reads the track's `TrackBeatgrid` to find beat positions.
- `Library` (`library.py`) holds one library folder's `DatabaseV2`, `Crate`s, and `SmartCrate`s, each parsed on first use and then kept. Its `rename_track_file` and `remove_track_files` change the files on disk and update every one of them that contains the track, saving only those. Smart crates are included because Serato re-adds a missing path from a smart crate to the database as a blank "?" entry. The deprecated `DatabaseV2.rename_track_file` calls it with its own database. New operations that have to reach the whole library (database and every crate) belong on `Library`, not on `DatabaseV2`; pass `Library(database=...)` an already-loaded database so the two don't overwrite each other's saves. `set_track_tags` / `set_tracks_tags` set values that live both in the track file's tags and in the database (Serato shows the database, and only rescans a file's tags when the track is loaded or on "Rescan File Tags"). The values are the keys of the `TrackTags` TypedDict in `track_properties.py`, each backed by an entry in its `_TRACK_PROPERTIES` table giving the database field, the conversion to the database's form (e.g. a `TrackCuesV2.TrackColors` value as a `0xRRGGBB` int for `COLOR`), and how to write it into the opened file; adding a value means adding to both. Each file is opened once and every file is written before the database, which is saved once. A Serato GEOB value the file has nowhere to put yet (track not yet imported) is only set in the database, with a warning. `Library` imports `track_properties` inside the method, so it doesn't need the optional `track_tags` extra.
- `usb_export.py` composes `Crate`, `SmartCrate`, and `DatabaseV2`: it flattens all tracks into one folder on the drive, dedupes by basename, rewrites crate/database paths to the new layout, and copies only changed files.
- `SERATO_DIR` (`~/Music/_Serato_`) in `utils/__init__.py` is the default root for all library lookups.

### CLI conventions

Console scripts are declared in `[project.scripts]` in `pyproject.toml` and point at `main()` / `main_analyze()` in the module. Each entry point defines a local `@dataclass Args` and constructs it with `Args(**vars(parser.parse_args()))` to get a typed view of argparse output — follow that pattern when adding a CLI. Modules also start with `if __package__ is None: sys.path.append(...)` so they can be run directly as scripts.

## Repository layout notes

- `test/data/` — fixtures for the unittest suite. Tests assert **byte-exact** round-trips (parse → serialize must reproduce the input), so regenerate fixtures deliberately, never to make a test pass.
- `data/` — reference dumps of raw GEOB tags captured from real tracks, organized by container (`id3`, `flac`, `mp4`, `aif`, `ogg`) and scenario (`hotcue-colors`, `saved-loops`, `bpmlock`, ...). Used as evidence for the format writeups in `docs/`, not by the test suite. Committed as binary via `.gitattributes`.
- `docs/` — per-tag format documentation; `docs/fileformats.md` covers how each container stores the tags.
- `conventions/` — see [Conventions](#conventions) above; imported, not editable in place.
