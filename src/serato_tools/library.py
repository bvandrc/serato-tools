"""A Serato library folder as a whole, for changes that have to reach its database and every crate together."""

import fnmatch
import os
import re
from collections.abc import Callable, Collection, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Unpack

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils import SERATO_DIR, StrPath, logger
from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils.crate_base import CrateBase

if TYPE_CHECKING:
    from serato_tools.db_track_props import DbTrackTags

# the extension of the file Serato keeps a track's stems in, beside the track
STEMS_EXTENSION = ".serato-stems"


@dataclass(frozen=True)
class DbTrackTagsResult:
    """What `Library.set_db_tracks_tags` (or `set_db_track_tags`) changed."""

    database_changed: bool
    """Whether the database changed. Inside `batch()`, it's saved when the block ends."""
    files_written: list[str]
    """The track files whose tags changed, so were written, as their paths were passed, in the order given."""


@dataclass(frozen=True)
class RemoveTrackFilesResult:
    """What `Library.remove_track_files` changed."""

    files_deleted: list[str]
    """The track files deleted, as their paths were passed, in the order given, each followed by its stems files. A
    file already gone isn't listed, and none are with `delete_files=False`."""
    library_files_changed: list[str]
    """The paths of the database, crates, and smart crates that held one of the tracks, so had it removed.

    Inside `batch()`, they're saved when the block ends.
    """


@dataclass(frozen=True)
class DeleteAnalysisResult:
    """What `Library.delete_analysis` changed."""

    database_changed: bool
    """Whether the database changed. Inside `batch()`, it's saved when the block ends."""
    files_written: list[str]
    """The track files that had analysis to delete, so were written, as their paths were passed, in the order given."""


@contextmanager
def _needs_track_tags_extra() -> Generator[None]:
    """Turns a missing mutagen, imported in the block, into an ImportError saying to install the track_tags extra.

    For the methods that change track files, which import those modules in this block on first use, so the rest of
    Library works without the extra.
    """
    try:
        yield
    except ModuleNotFoundError as error:
        if (error.name or "").split(".")[0] != "mutagen":
            raise
        raise ImportError(
            'changing track files needs the track_tags extra: pip install "serato-tools[track_tags]"'
        ) from error


class Library:
    """A Serato library: its database, crates, and smart crates, for changes that have to reach all of them.

    Each file is parsed the first time it's needed, then kept, so many changes in a row don't re-parse the library.
    Keep one Library per library folder: another copy's save would overwrite this one's changes, and the reverse.
    """

    def __init__(self, serato_dir: StrPath = SERATO_DIR, database: DatabaseV2 | None = None):
        """Pass `database` to use one already loaded, along with any unsaved changes it has, instead of parsing it."""
        # TODO(breaking): remove serato_dir, once deprecated in favor of serato_path
        self.serato_dir = os.fspath(serato_dir)
        self._database = database
        # how many batch() blocks are open; while any is, this class's methods leave saving to the outermost one
        self._batch_depth = 0

    @property
    def serato_path(self) -> Path:
        """The library folder, as a `Path`: `serato_dir`, which is a `str`."""
        return Path(self.serato_dir)

    @cached_property
    def database(self) -> DatabaseV2:
        if self._database is not None:
            return self._database
        return DatabaseV2(self.serato_path / DatabaseV2.FILENAME)

    @cached_property
    def crates(self) -> list[Crate]:
        """The library's crates, from its `Subcrates` folder."""
        return [Crate(path) for path in self._get_crate_files(Crate)]

    @cached_property
    def smart_crates(self) -> list[SmartCrate]:
        """The library's smart crates, from its `SmartCrates` folder."""
        return [SmartCrate(path) for path in self._get_crate_files(SmartCrate)]

    @property
    def crate_files(self) -> list[str]:
        """The paths of the library's crate and smart crate files, crates first, without parsing them.

        Read from disk on each access, so it includes crates made since the Library was.
        """
        return self._get_crate_files(Crate) + self._get_crate_files(SmartCrate)

    def find_crate_files(self, pattern: str) -> list[str]:
        """The paths of the library's crate and smart crate files whose name matches `pattern`, crates first.

        The name is the filename without its extension, so `"*crate*"` matches only crates with "crate" in their name. A
        subcrate's name includes its parents' (`Bass%%DnB`), so `"Bass*"` matches a crate and its subcrates. `pattern` is
        tried as a glob, and if nothing matches it, as a regex.
        """
        names = {f: Path(f).stem for f in self.crate_files}

        # try the pattern as a glob first: most globs (e.g. "house*") are also valid regexes, so
        # checking re.compile first would silently give glob-looking patterns regex semantics
        files = [f for f, name in names.items() if fnmatch.fnmatch(name, pattern)]
        if not files:
            try:
                regex = re.compile(pattern)
            except re.error:
                return []
            files = [f for f, name in names.items() if regex.search(name)]
        return files

    @staticmethod
    def find_stems_files(track_path: StrPath) -> list[str]:
        """The stems files Serato keeps beside the track at `track_path`, sorted: empty if it has none.

        Serato names one after the track without its extension, with the version of the separation before the
        extension: `A.1.2.serato-stems` for `A.mp3`. A track separated again with a newer version can have more than
        one. A name without the version (`A.serato-stems`) counts too. Lists the track's folder, so it finds them whether
        or not the track's own file exists.
        """
        path = Path(track_path)
        # the version is two numbers, so another track's never matches: A.1.mp3's A.1.1.2.serato-stems has three after
        # "A". Ignoring case, since Serato runs on case-insensitive filesystems, where the library's path for a track
        # may differ in case from its file's.
        pattern = re.compile(rf"{re.escape(path.stem)}(?:\.\d+\.\d+)?{re.escape(STEMS_EXTENSION)}", re.IGNORECASE)
        try:
            # listdir's names, rather than iterdir's Paths: the USB export calls this for every track, and a Path for
            # every file in each track's folder made exporting a 12,000-track library twice as slow
            names = [name for name in os.listdir(path.parent) if pattern.fullmatch(name)]  # noqa: PTH208
        except OSError:
            # its folder is gone, so it has none
            return []
        return sorted(str(path.parent / name) for name in names)

    def _get_crate_files(self, crate_class: type[CrateBase]) -> list[str]:
        crates_dir = self.serato_path / crate_class.DIR
        # Serato only creates the folder once the first crate of its kind is made
        return crate_class.get_crate_files(crates_dir) if crates_dir.is_dir() else []

    def _get_bin_files(self) -> list[SeratoBinFile]:
        """Every file in the library that holds track paths: the database, crates, and smart crates."""
        # smart crates store their matched tracks' paths too, and Serato re-adds any of those that are missing from
        # the database as blank "?" entries
        return [self.database, *self.crates, *self.smart_crates]

    def _get_parsed_bin_files(self) -> list[SeratoBinFile]:
        """The files of `_get_bin_files` that have been parsed, without parsing any others."""
        # cached_property keeps its value in the instance's vars, and a file that isn't parsed yet can't have changes.
        # A database passed to __init__ is only there once `database` is read, so it's taken from _database until then
        parsed = vars(self)
        database: DatabaseV2 | None = parsed.get("database", self._database)
        return [
            *([database] if database is not None else []),
            *parsed.get("crates", []),
            *parsed.get("smart_crates", []),
        ]

    def save(self) -> list[str]:
        """Writes every parsed file that has changed, and returns the paths of the ones written.

        Saves changes made through `database`'s or the crates' own methods, such as `modify`; `batch()` calls it for this
        class's own methods. Each parsed file is serialized once, to check it and to write it if it changed, so call this
        once, after all of the changes.
        """
        saved: list[str] = []
        for file in self._get_parsed_bin_files():
            # a loop rather than a comprehension, so the save isn't hidden in its filter
            if file.save():
                saved.append(file.filepath)  # noqa: PERF401
        return saved

    @contextmanager
    def batch(self) -> Generator[None]:
        """Holds back this library's saves until the block ends, then writes each changed file once, with `save()`.

        Inside the block, this class's methods change the database and crates without writing them, so many changes
        don't rewrite the database once per track. Track files are still renamed, deleted, or tagged right away, so the
        library is saved when the block ends even if it raises, keeping it pointed at them. A batch inside another saves
        only when the outermost one ends.
        """
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if not self._batch_depth:
                self.save()

    def _save_unless_batching(self, file: SeratoBinFile):
        """Saves `file` now, unless a `batch()` is open, which will save it when it ends."""
        if not self._batch_depth:
            file.save()

    def _change_bin_files(self, change: Callable[[SeratoBinFile], bool]) -> list[str]:
        """Applies `change` to every library file, saving each it changed unless batching; returns their paths."""
        changed: list[str] = []
        for file in self._get_bin_files():
            if change(file):
                self._save_unless_batching(file)
                changed.append(file.filepath)
        return changed

    def rename_track_file(self, src: StrPath, dest: StrPath) -> list[str]:
        """Renames the file, and points the database and crates at the new path, so the track isn't missing in Serato.

        Returns the paths of the database, crates, and smart crates that held the track, so were changed: empty when
        none did, e.g. for a file Serato hasn't imported. Only those are saved, or, inside `batch()`, left for it to
        save once. Raises FileExistsError, changing nothing, if a different file already exists at `dest`.
        """
        # rename only raises FileExistsError on Windows; on POSIX it silently overwrites, so check
        # first. A case-only rename is fine: on case-insensitive filesystems dest is then the same file.
        # If src is missing, samefile raises FileNotFoundError, just as the rename itself would.
        src_path, dest_path = Path(src), Path(dest)
        if dest_path.exists() and not src_path.samefile(dest_path):
            raise FileExistsError(f"can't rename {src}: a different file already exists at {dest}")
        # where exists misses a clash, e.g. a case change on some filesystems, rename raises FileExistsError itself on
        # Windows
        src_path.rename(dest_path)
        logger.info(f"renamed {src} to {dest}")

        return self._change_bin_files(lambda file: file.change_track_path(src, dest))

    def remove_track_files(
        self, filepaths: Collection[StrPath], *, delete_files: bool, missing_ok: bool = True
    ) -> RemoveTrackFilesResult:
        """Removes the tracks from the database and crates, then, with `delete_files=True`, deletes their files.

        With `delete_files=False`, the files are left as they are, so the tracks are only gone from the library.
        Otherwise each track's stems files (see `find_stems_files`) are deleted too, even when the track's own file is
        already gone.

        Returns which files it deleted, and which library files it changed (see RemoveTrackFilesResult). Paths whose
        file is already gone are still removed from the library, which cleans up missing tracks. With
        `delete_files=True` and `missing_ok=False`, it raises `FileNotFoundError` naming them instead, before changing
        anything. Only the files that contain one of the tracks are saved, or, inside `batch()`, left for it to save
        once.
        """
        # as str paths, the type files_deleted lists them as
        filepaths = [os.fspath(p) for p in filepaths]
        if delete_files and not missing_ok and (missing := [p for p in filepaths if not Path(p).exists()]):
            raise FileNotFoundError(f"Track files not found: {', '.join(missing)}")
        changed = self._change_bin_files(lambda file: file.remove_tracks(filepaths))
        deleted: list[str] = []
        if delete_files:
            for filepath in filepaths:
                for path in (filepath, *self.find_stems_files(filepath)):
                    try:
                        Path(path).unlink()
                    except FileNotFoundError:
                        continue
                    logger.info(f"deleted {path}")
                    deleted.append(path)
        return RemoveTrackFilesResult(files_deleted=deleted, library_files_changed=changed)

    def set_db_track_tags(
        self, filepath: StrPath, *, delete_tags_v1: bool = True, **tags: Unpack["DbTrackTags"]
    ) -> DbTrackTagsResult:
        """Sets values in the track file's tags and in the database, as set_db_tracks_tags does for many tracks."""
        return self.set_db_tracks_tags({filepath: tags}, delete_tags_v1=delete_tags_v1)

    def set_db_tracks_tags(
        self, tracks: Mapping[StrPath, "DbTrackTags"], delete_tags_v1: bool = True
    ) -> DbTrackTagsResult:
        """Sets values in each track file's tags and in the database, so Serato shows them right away.

        `tracks` maps each file's path to the values to set (see DbTrackTags). Returns whether the database changed, and
        which files were written (see DbTrackTagsResult).

        - Needs the `track_tags` extra, and raises ImportError without it.
        - Only ID3 files (.mp3, .aiff, .aif) are currently supported.
        - A track whose tags don't have a value yet, since Serato hasn't analyzed it, gets it added as Serato writes it.
        - A bad key or value, or a file that can't be read, raises before any file or the database is changed.
        - Every file is written before the database, which is saved once: here, or, inside `batch()`, when it ends.
        - A track that isn't in the database only has its file's tags set, with a warning.
        - See TrackCuesV2.save for `delete_tags_v1`.
        """
        with _needs_track_tags_extra():
            from serato_tools import db_track_props as props  # noqa: PLC0415
        # keyed by str paths, the type files_written lists them as
        str_tracks = {os.fspath(filepath): tags for filepath, tags in tracks.items()}
        # converted and checked before any file is written, so a value the database can't hold changes nothing
        db_values = {
            DatabaseV2.get_relative_path(filepath).upper(): props.to_db_values(tags)
            for filepath, tags in str_tracks.items()
        }
        for values in db_values.values():
            for field, value in values.items():
                SeratoBinFile.check_value(field, value)
        files_written = props.write_db_track_tags_to_files(str_tracks, delete_tags_v1)

        found: set[str] = set()

        def set_values(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
            # matched by case, as modify_tracks matches `files`
            relpath = track.relpath.upper()
            found.add(relpath)
            for field, value in db_values[relpath].items():
                track.set_value(field, value)
            return track

        changed = self.database.modify_tracks(set_values, files=str_tracks)
        for filepath in str_tracks:
            if DatabaseV2.get_relative_path(filepath).upper() not in found:
                logger.warning(f"track isn't in the database, so only its file's tags were set: {filepath}")
        if changed:
            self._save_unless_batching(self.database)
        return DbTrackTagsResult(database_changed=changed, files_written=files_written)

    def delete_analysis(self, filepaths: Collection[StrPath], include_locked: bool = False) -> DeleteAnalysisResult:
        """Deletes the tracks' analysis from their files and marks them unanalyzed, so Serato analyzes them again.

        For tracks whose audio changed. The analysis is the waveform overview, beatgrid, autotags (BPM and autogain),
        and gain; cues, color, and the text tags are kept. Returns whether the database changed, and which files were
        written (see DeleteAnalysisResult).

        - A track whose beatgrid is locked raises ValueError, before any file or the database is changed, unless
          `include_locked`, which unlocks it too, in the file and the database.
        - Needs the `track_tags` extra, and raises ImportError without it. Only ID3 files (.mp3, .aiff, .aif) are
          currently supported.
        - Every file is written before the database, which is saved once: here, or, inside `batch()`, when it ends.
        """
        with _needs_track_tags_extra():
            from serato_tools.track import Track  # noqa: PLC0415
        # as str paths, the type files_written lists them as
        filepaths = [os.fspath(p) for p in filepaths]
        # every file is read and checked before any is written, so a locked or unreadable one changes nothing
        tracks = {filepath: Track(filepath, cues_v1=False, text_frames=False) for filepath in filepaths}
        locked = [filepath for filepath, track in tracks.items() if track.is_beatgrid_locked()]
        if locked and not include_locked:
            raise ValueError(f"these tracks' beatgrids are locked, so pass include_locked to clear them: {locked}")

        for filepath in locked:
            tracks[filepath].set_beatgrid_locked(False)
        files_written: list[str] = []
        for filepath, track in tracks.items():
            track.delete_analysis()
            if track.save():
                files_written.append(filepath)

        changed = self.database.set_unanalyzed(filepaths)
        if locked:
            lock_field = SeratoBinFile.Fields.BEATGRID_LOCKED

            def unlock(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
                track.set_value(lock_field, False)
                return track

            unlocked = self.database.modify_tracks(unlock, files=locked)
            changed = changed or unlocked
        if changed:
            self._save_unless_batching(self.database)
        return DeleteAnalysisResult(database_changed=changed, files_written=files_written)
