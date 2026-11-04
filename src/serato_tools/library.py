#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
from functools import cached_property
from typing import TYPE_CHECKING, Mapping, Unpack


from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils import logger, SERATO_DIR

if TYPE_CHECKING:
    from serato_tools.db_track_props import TrackTags


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

    @cached_property
    def database(self) -> DatabaseV2:
        if self._database is not None:
            return self._database
        return DatabaseV2(os.path.join(self.serato_dir, DatabaseV2.FILENAME))

    @cached_property
    def crates(self) -> list[Crate]:
        return [Crate(path) for path in self._get_crate_files(Crate)]

    @cached_property
    def smart_crates(self) -> list[SmartCrate]:
        return [SmartCrate(path) for path in self._get_crate_files(SmartCrate)]

    def _get_crate_files(self, crate_class: type[Crate] | type[SmartCrate]) -> list[str]:
        crates_dir = os.path.join(self.serato_dir, crate_class.DIR)
        # Serato only creates the folder once the first crate of its kind is made
        return crate_class.get_crate_files(crates_dir) if os.path.isdir(crates_dir) else []

    def _get_bin_files(self) -> list[SeratoBinFile]:
        # smart crates store their matched tracks' paths too, and Serato re-adds any of those that are missing from
        # the database as blank "?" entries
        return [self.database, *self.crates, *self.smart_crates]

    def rename_track_file(self, src: str, dest: str):
        """Renames the file, and points the database and crates at the new path, so the track isn't missing in Serato.

        Does nothing if a different file already exists at `dest`. Only the files that contain the track are saved.
        """
        # os.rename only raises FileExistsError on Windows; on POSIX it silently overwrites, so check
        # first. A case-only rename is fine: on case-insensitive filesystems dest is then the same file.
        # If src is missing, samefile raises FileNotFoundError, just as the rename itself would.
        if os.path.exists(dest) and not os.path.samefile(src, dest):
            logger.error(f"File already exists with change: {src}")
            return
        try:
            os.rename(src=src, dst=dest)
            logger.info(f"renamed {src} to {dest}")
        except FileExistsError:
            # can't just do os.path.exists, doesn't pick up case changes for certain filesystems
            logger.error(f"File already exists with change: {src}")
            return

        for file in self._get_bin_files():
            if file.change_track_path(src, dest):
                file.save()

    def remove_track_files(self, filepaths: list[str]):
        """Removes the tracks from the database and crates, then deletes their files.

        Paths whose file is already gone are still removed from the library, which cleans up missing tracks. Only the
        files that contain one of the tracks are saved.
        """
        for file in self._get_bin_files():
            if file.remove_tracks(filepaths):
                file.save()
        for filepath in filepaths:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"deleted {filepath}")

    def set_track_tags(self, filepath: str, *, delete_tags_v1: bool = True, **tags: Unpack["TrackTags"]) -> bool:
        """Sets values in the track file's tags and in the database, as set_tracks_tags does for many tracks."""
        return self.set_tracks_tags({filepath: tags}, delete_tags_v1=delete_tags_v1)

    def set_tracks_tags(self, tracks: Mapping[str, "TrackTags"], delete_tags_v1: bool = True) -> bool:
        """Sets values in each track file's tags and in the database, so Serato shows them right away.

        Needs the `track_tags` extra (raising ImportError without it), and only ID3 files (.mp3, .aiff, .aif) are
        currently supported. `tracks` maps each file's path to the values to set (see TrackTags). A value the file has
        nowhere to put yet, since Serato hasn't imported the track, is only set in the database, with a warning. Every
        file is written before the database is, in a single save, so a file that fails to be written leaves the
        database unchanged. Returns whether the database changed. See TrackCuesV2.set_track_color for `delete_tags_v1`.
        """
        props = _db_track_props()
        for tags in tracks.values():
            props.check_track_tags(tags)
        for filepath, tags in tracks.items():
            props.write_file_tags(filepath, tags, delete_tags_v1)

        # each field's new value per track; modify passes rules the track's path as Serato stores it, matched by case
        values_by_field: dict[DatabaseV2.Fields, dict[str, SeratoBinFile.BasicValue]] = {}
        for filepath, tags in tracks.items():
            relpath = DatabaseV2.get_relative_path(filepath).upper()
            for field, value in props.to_db_values(tags).items():
                values_by_field.setdefault(field, {})[relpath] = value
        rules: list[SeratoBinFile.ModifyRule] = [
            {
                "field": field,
                "files": list(values),
                "func": lambda relpath, _, values=values: values.get(relpath.upper()),
            }
            for field, values in values_by_field.items()
        ]
        changed = self.database.modify(rules) if rules else False
        if changed:
            self.database.save()
        return changed
