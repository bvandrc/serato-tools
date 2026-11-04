#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
from functools import cached_property
from typing import TYPE_CHECKING

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils.bin_file_base import SeratoBinFile
from serato_tools.utils import logger, SERATO_DIR

if TYPE_CHECKING:
    from serato_tools.track_cues_v2 import TrackCuesV2


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

    def set_track_color(self, filepath: str, color: "TrackCuesV2.TrackColors", delete_tags_v1: bool = True):
        """Sets the track's color in its tags and in the database, so Serato shows it right away and the file keeps it.

        Needs the `track_tags` extra. A track whose tags have no color yet (one Serato hasn't analyzed) only gets it in
        the database. See TrackCuesV2.set_track_color for `delete_tags_v1`.
        """
        # imported here, since only this needs the optional track_tags extra
        from serato_tools.track_cues_v2 import TrackCuesV2  # pylint: disable=import-outside-toplevel

        tags = TrackCuesV2(filepath)
        tags.set_track_color(color, delete_tags_v1=delete_tags_v1)
        if tags.get_track_color() is None:
            logger.warning(f"no track color in the tags to change, so only set in the database: {filepath}")
        tags.save()

        rgb = int.from_bytes(color.value, "big")
        self.database.modify_and_save([{"field": DatabaseV2.Fields.COLOR, "files": [filepath], "func": lambda *_: rgb}])
