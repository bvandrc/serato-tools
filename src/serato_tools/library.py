#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A Serato library folder as a whole, for changes that have to reach its database and every crate together."""

import os
from contextlib import contextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Iterator, Mapping, Unpack

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils import SERATO_DIR, logger
from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils.crate_base import CrateBase

if TYPE_CHECKING:
    from serato_tools.db_track_props import DbTrackTags


def _db_track_props():  # return type left to pyright, which infers the module and so checks its attributes
    """The db_track_props module, for the methods that change track files.

    Raises ImportError, saying how to install it, without the optional track_tags extra, so the rest of Library works
    without it.
    """
    try:
        from serato_tools import db_track_props  # pylint: disable=import-outside-toplevel
    except ModuleNotFoundError as error:
        if (error.name or "").split(".")[0] != "mutagen":
            raise
        raise ImportError(
            'changing track files needs the track_tags extra: pip install "serato-tools[track_tags]"'
        ) from error
    return db_track_props


class Library:
    """A Serato library: its database, crates, and smart crates, for changes that have to reach all of them.

    Each file is parsed the first time it's needed, then kept, so many changes in a row don't re-parse the library.
    Keep one Library per library folder: another copy's save would overwrite this one's changes, and the reverse.
    """

    def __init__(self, serato_dir: str = SERATO_DIR, database: DatabaseV2 | None = None):
        """Pass `database` to use one already loaded, along with any unsaved changes it has, instead of parsing it."""
        self.serato_dir = serato_dir
        self._database = database
        # how many batch() blocks are open; while any is, this class's methods leave saving to the outermost one
        self._batch_depth = 0

    @cached_property
    def database(self) -> DatabaseV2:
        if self._database is not None:
            return self._database
        return DatabaseV2(os.path.join(self.serato_dir, DatabaseV2.FILENAME))

    @cached_property
    def crates(self) -> list[Crate]:
        """The library's crates, from its `Subcrates` folder."""
        return [Crate(path) for path in self._get_crate_files(Crate)]

    @cached_property
    def smart_crates(self) -> list[SmartCrate]:
        """The library's smart crates, from its `SmartCrates` folder."""
        return [SmartCrate(path) for path in self._get_crate_files(SmartCrate)]

    def _get_crate_files(self, crate_class: type[CrateBase]) -> list[str]:
        crates_dir = os.path.join(self.serato_dir, crate_class.DIR)
        # Serato only creates the folder once the first crate of its kind is made
        return crate_class.get_crate_files(crates_dir) if os.path.isdir(crates_dir) else []

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
            if file.save():
                saved.append(file.filepath)
        return saved

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Holds back this library's saves until the block ends, then writes each changed file once, with `save()`.

        Inside the block, `rename_track_file`, `remove_track_files`, and `set_db_tracks_tags` change the database and
        crates without writing them, so many changes don't rewrite the database once per track. Track files are still
        renamed, deleted, or tagged right away, so the library is saved when the block ends even if it raises, keeping it
        pointed at them. A batch inside another saves only when the outermost one ends.
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

    def rename_track_file(self, src: str, dest: str) -> bool:
        """Renames the file, and points the database and crates at the new path, so the track isn't missing in Serato.

        Returns whether it renamed the file. It does nothing, and returns False, if a different file already exists at
        `dest`. Only the files that contain the track are saved, or, inside `batch()`, left for it to save once.
        """
        # os.rename only raises FileExistsError on Windows; on POSIX it silently overwrites, so check
        # first. A case-only rename is fine: on case-insensitive filesystems dest is then the same file.
        # If src is missing, samefile raises FileNotFoundError, just as the rename itself would.
        if os.path.exists(dest) and not os.path.samefile(src, dest):
            logger.error(f"File already exists with change: {src}")
            return False
        try:
            os.rename(src=src, dst=dest)
            logger.info(f"renamed {src} to {dest}")
        except FileExistsError:
            # can't just do os.path.exists, doesn't pick up case changes for certain filesystems
            logger.error(f"File already exists with change: {src}")
            return False

        for file in self._get_bin_files():
            if file.change_track_path(src, dest):
                self._save_unless_batching(file)
        return True

    def remove_track_files(self, filepaths: list[str]):
        """Removes the tracks from the database and crates, then deletes their files.

        Paths whose file is already gone are still removed from the library, which cleans up missing tracks. Only the
        files that contain one of the tracks are saved, or, inside `batch()`, left for it to save once.
        """
        for file in self._get_bin_files():
            if file.remove_tracks(filepaths):
                self._save_unless_batching(file)
        for filepath in filepaths:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"deleted {filepath}")

    def set_db_track_tags(
        self, filepath: str, *, delete_tags_v1: bool = True, write_files: bool = True, **tags: Unpack["DbTrackTags"]
    ) -> bool:
        """Sets values in the track file's tags and in the database, as set_db_tracks_tags does for many tracks."""
        return self.set_db_tracks_tags({filepath: tags}, delete_tags_v1=delete_tags_v1, write_files=write_files)

    def set_db_tracks_tags(
        self, tracks: Mapping[str, "DbTrackTags"], delete_tags_v1: bool = True, write_files: bool = True
    ) -> bool:
        """Sets values in each track file's tags and in the database, so Serato shows them right away.

        `tracks` maps each file's path to the values to set (see DbTrackTags). Returns whether the database changed.

        - Needs the `track_tags` extra, and raises ImportError without it.
        - Only ID3 files (.mp3, .aiff, .aif) are currently supported.
        - A track whose tags don't have a value yet, since Serato hasn't analyzed it, gets it added as Serato writes it.
        - A bad key or value, or a file that can't be read, raises before any file or the database is changed.
        - Every file is written before the database, which is saved once: here, or, inside `batch()`, when it ends.
        - A track that isn't in the database only has its file's tags set, with a warning.
        - With `write_files=False`, only the database is set, for files that already hold the values, such as ones the
          caller just wrote: the files aren't opened, and `delete_tags_v1` doesn't apply.
        - See TrackCuesV2.save for `delete_tags_v1`.
        """
        props = _db_track_props()
        # converted before any file is written, so a value the database can't hold changes nothing
        db_values = {
            DatabaseV2.get_relative_path(filepath).upper(): props.to_db_values(tags)
            for filepath, tags in tracks.items()
        }
        if write_files:
            props.write_db_track_tags_to_files(tracks, delete_tags_v1)

        found: set[str] = set()

        def set_values(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
            # matched by case, as modify_tracks matches `files`
            relpath = track.relpath.upper()
            found.add(relpath)
            for field, value in db_values[relpath].items():
                track.set_value(field, value)
            return track

        changed = self.database.modify_tracks(set_values, files=list(tracks))
        for filepath in tracks:
            if DatabaseV2.get_relative_path(filepath).upper() not in found:
                logger.warning(f"track isn't in the database, so only its file's tags were set: {filepath}")
        if changed:
            self._save_unless_batching(self.database)
        return changed
