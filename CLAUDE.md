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
pip install -e ".[track_tags,waveform_drawing,beatgrid_analysis,dev]"  # all optional deps + black, pylint, pyright
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

CI (`.github/workflows/lint-and-test.yml`) runs on **windows-latest** across Python 3.12/3.13/3.14. Path handling is Windows-centric — `SeratoBinFile.get_relative_path` strips a drive letter via `os.path.splitdrive` and normalizes on `os.path.sep`, so several crate/database tests fail on Linux and macOS. That is expected locally; don't "fix" those failures unless the task is explicitly about cross-platform paths.

Publishing to PyPI is a manual `workflow_dispatch` of `.github/workflows/build-and-publish.yml`. Bump `version` in `pyproject.toml` and add a `CHANGELOG.md` entry for user-visible changes.

## Architecture

The package handles two unrelated Serato binary formats. Nearly everything else is a subclass of one of the two base classes.

### 1. Serato bin container — `utils/bin_file_base.py`

`SeratoBinFile` parses the format used by the library database and crate files (`database V2`, `.crate`, `.scrate`). The container is a flat/nested sequence of entries: an 8-byte header (`>4sI` — 4-char ASCII field name, big-endian length) followed by the payload. **The value type is derived from the first character of the field name**, not from any type byte: `o`/`r` → nested struct, `p`/`t` → UTF-16-BE text, `b` → bool, `s` → u16, `u` → u32. `vrsn` is special-cased as text.

Subclasses (`DatabaseV2`, `CrateBase` → `Crate` / `SmartCrate`) must define `TESTED_VERSIONS`, `TRACK_PATH_KEY`, and `DEFAULT_ENTRIES`; the constructor raises `AttributeError` if any is missing. Field names are centralized in the `SeratoBinFile.Fields` StrEnum.

The lifecycle is `parse → self.entries → mutate → to_bytes() → save()`:

- The file's bytes aren't stored. Each `to_bytes()` call serializes `entries` from scratch, so mutations cost nothing and each `save()` pays for one serialization. Edit `entries` however you like, in place or by assignment. `raw_data` is a deprecated alias of `to_bytes()`, due for removal in 5.0; the `SeratoTag` classes' `raw_data` is unrelated and really is stored.
- `modify_tracks`, `modify`, `change_track_path`, `filter_tracks`, `remove_track`, and `remove_duplicates` return whether anything changed. Methods that save on the caller's behalf (`modify_and_save`, `find_missing`, `DatabaseV2.rename_track_file`) use that to skip writing an unchanged file. `save()` itself always writes, since it doubles as "save as".
- `modify()` takes a list of `ModifyRule` dicts (`{"field": ..., "func": (filename, prev_val) -> new_val | None, "files": [...]}`); returning `None` from `func` means "leave unchanged".
- `modify_tracks(func, files=...)` and `modify()` with every rule limited to `files` skip all other tracks without parsing them, which keeps single-track edits fast on a large library.
- Files can also round-trip through JSON (`to_json_object` / `from_json_object` / `write_json`), with bytes base64-encoded.

### 2. GEOB tags inside audio files — `utils/track_tags.py`

`SeratoTrack` wraps a mutagen file and reads/writes `GEOB:<key>` frames. `SeratoTag` subclasses it, one class per GEOB tag, each declaring `GEOB_KEY` and `VERSION` and implementing `_parse` / `_dump`:

| Class | GEOB tag | Module |
| --- | --- | --- |
| `TrackCuesV2` | `Serato Markers2` — hotcues, loops, flips, track color, BPM lock | `track_cues_v2.py` |
| `TrackCuesV1` | `Serato Markers_` — legacy equivalent | `track_cues_v1.py` |
| `TrackBeatgrid` | `Serato BeatGrid` | `track_beatgrid.py` |
| `TrackAutotags` | `Serato Autotags` — BPM/gain | `track_autotags.py` |
| `TrackWaveform` | `Serato Overview` | `track_waveform.py` |

Each of these accepts *either* a file path / mutagen tagfile *or* raw `bytes` (`SeratoTag.FileOrData`). The bytes path is what lets tests feed the `.bin` fixtures in `test/data/` without an audio file, and it's why `self.tagfile` may be `None` — `save()` raises in that case.

**v1/v2 interaction:** current Serato reads `Serato Markers2`, but a stale `Serato Markers_` shadows changes made to it. That's why the mutating APIs (`TrackCuesV2.modify_entries`, `set_track_color`) take `delete_tags_v1=True` by default — they delete the v1 tag rather than keeping the two in sync.

`TrackCuesV2` exposes each entry kind (`CueEntry`, `LoopEntry`, `ColorEntry`, `FlipEntry`, `BpmLockEntry`) as a dataclass, aggregated into `TrackCuesInfo`; `modify_entries(callback)` hands the callback the whole `TrackCuesInfo` and expects a new one back (use `dataclasses.replace`) or `None` for no change.

### Version gating

Both bases refuse unknown formats: `SeratoBinFile._check_version` rejects any `vrsn` not in `TESTED_VERSIONS`, and `SeratoTag._check_version` rejects any tag version != `VERSION`. This is deliberate — writing a misparsed file would corrupt a user's library. Adding support for a new version means adding the version string *and* a fixture + round-trip test, not just widening the check.

### Cross-module dependencies

- `TrackCuesV2` cue snapping reads the track's `TrackBeatgrid` to find beat positions.
- `DatabaseV2.rename_track_file` renames on disk, then updates the database *and* every crate under `Crate.DIR_PATH`, saving only those that contain the track, so a renamed file doesn't go missing.
- `usb_export.py` composes `Crate`, `SmartCrate`, and `DatabaseV2`: it flattens all tracks into one folder on the drive, dedupes by basename, rewrites crate/database paths to the new layout, and copies only changed files.
- `SERATO_DIR` (`~/Music/_Serato_`) in `utils/__init__.py` is the default root for all library lookups.

### CLI conventions

Console scripts are declared in `[project.scripts]` in `pyproject.toml` and point at `main()` / `main_analyze()` in the module. Each entry point defines a local `@dataclass Args` and constructs it with `Args(**vars(parser.parse_args()))` to get a typed view of argparse output — follow that pattern when adding a CLI. Modules also start with `if __package__ is None: sys.path.append(...)` so they can be run directly as scripts.

## Repository layout notes

- `test/data/` — fixtures for the unittest suite. Tests assert **byte-exact** round-trips (parse → dump must reproduce the input), so regenerate fixtures deliberately, never to make a test pass.
- `data/` — reference dumps of raw GEOB tags captured from real tracks, organized by container (`id3`, `flac`, `mp4`, `aif`, `ogg`) and scenario (`hotcue-colors`, `saved-loops`, `bpmlock`, ...). Used as evidence for the format writeups in `docs/`, not by the test suite. Committed as binary via `.gitattributes`.
- `docs/` — per-tag format documentation; `docs/fileformats.md` covers how each container stores the tags.
- `conventions/` — see [Conventions](#conventions) above; imported, not editable in place.
