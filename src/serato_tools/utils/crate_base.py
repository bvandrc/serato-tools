# This is from this repo: https://github.com/sharst/seratopy
"""What crates and smart crates share: their file extension and folder, track paths, and how they print."""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar, Self

from serato_tools.utils.bin_file_base import SeratoBinFile


class CrateBase(SeratoBinFile):
    """A crate or smart crate file: a list of track paths, which subclasses give an `EXTENSION` and a `DIR`."""

    EXTENSION: str
    DIR: str
    DIR_PATH: str
    TRACK_PATH_KEY = SeratoBinFile.Fields.TRACK_PATH

    # the sort and columns Serato gives a new crate or smart crate, which follow the version (and a smart crate's
    # settings) in each one's DEFAULT_ENTRIES
    DEFAULT_VIEW_ENTRIES: ClassVar[SeratoBinFile.EntryList] = [
        (
            SeratoBinFile.Fields.SORTING,
            [(SeratoBinFile.Fields.COLUMN_NAME, "key"), (SeratoBinFile.Fields.REVERSE_ORDER, False)],
        ),
        *(
            (
                SeratoBinFile.Fields.COLUMN,
                [(SeratoBinFile.Fields.COLUMN_NAME, column), (SeratoBinFile.Fields.COLUMN_WIDTH, "0")],
            )
            for column in ("song", "playCount", "artist", "bpm", "key", "album", "length", "comment", "added")
        ),
    ]

    def _stringify_entry(self, entry: SeratoBinFile.EntryFull, indent: int = 0) -> str:
        _field, _fieldname, value = entry
        return self._stringify_entries(value, indent) if isinstance(value, list) else str(value)

    def _stringify_entries(self, entries: Iterable[SeratoBinFile.EntryFull], indent: int = 0) -> str:
        lines: list[str] = []

        for field, fieldname, value in entries:
            if isinstance(value, list):
                field_lines = [
                    f"[ {entry[0]} ({entry[1]}): {self._stringify_entry(entry, indent + 1)} ]" for entry in value
                ]
                print_val = ", ".join(field_lines)
            else:
                print_val = str(value)
            lines.append(f"{field} ({fieldname}): {print_val}")

        return "\n".join(lines)

    def print_track_paths(self, filenames_only: bool = False):
        """Prints each track's absolute path, or with `filenames_only`, its filename without the extension."""
        track_paths = self.get_track_paths(include_drive=True)
        if filenames_only:
            track_paths = [Path(t).stem for t in track_paths]
        print("\n".join(track_paths))  # noqa: T201

    def save(self, file: str | None = None, force: bool = False) -> bool:
        """As `SeratoBinFile.save`, but raises ValueError if `file` doesn't end with this class's `EXTENSION`."""
        path = Path(self.filepath if file is None else file)
        if not path.name.endswith(self.EXTENSION):
            raise ValueError(f"file should end with {self.EXTENSION}: {path}")
        return super().save(str(path), force)

    def add_tracks(self, filepaths: Iterable[str]):
        """Adds the tracks not already in the crate. Filepaths must include the containing dir.

        A track already in the crate in another case isn't added again, as `remove_tracks` matches paths whatever
        their case.
        """
        # build the existing-path set once: checking get_track_paths() per added file costs a pass over
        # the whole crate per file
        existing = {path.upper() for path in self.get_track_paths()}
        for filepath in filepaths:
            relpath = self.get_relative_path(filepath)
            if relpath.upper() not in existing:
                self._entries.append((CrateBase.Fields.TRACK, [(CrateBase.Fields.TRACK_PATH, relpath)]))
                existing.add(relpath.upper())

    def add_tracks_from_dir(self, dir: str, replace: bool = False):  # noqa: A002
        """Adds every file directly in `dir` but hidden ones, such as `.DS_Store`; with `replace`, first removes every
        track that isn't one of them."""
        dir_tracks = [
            self.get_relative_path(str(path))
            for path in Path(dir).iterdir()
            # not a subfolder, which isn't a track
            if not path.name.startswith(".") and path.is_file()
        ]

        if replace:
            # one filter pass instead of a full scan per removed track; matched whatever their case, as add_tracks
            # matches them, so a track in the crate in another case is kept rather than removed and added again
            dir_track_set = {track.upper() for track in dir_tracks}
            self.filter_tracks(lambda track: track.relpath.upper() in dir_track_set)

        self.add_tracks(dir_tracks)

    @classmethod
    def new(cls, file: str) -> Self:
        """A new, empty crate at `file`, with the sort and columns Serato gives one, which `save()` creates.

        Raises FileExistsError if `file` already exists, rather than replace it on save.
        """
        return cls(file, _new=True)

    @classmethod
    def get_crate_files(cls, file_or_dir: str | None = None) -> list[str]:
        """The paths of this class's crate files directly in `file_or_dir`, or just `file_or_dir` if it's a file.

        Defaults to this class's folder in the default Serato folder (`DIR_PATH`). Raises FileNotFoundError if
        `file_or_dir` doesn't exist.
        """
        if file_or_dir is None:
            file_or_dir = cls.DIR_PATH
        path = Path(file_or_dir)

        crate_paths: list[str] = []
        if path.is_dir():
            # normpath, which unlike Path collapses "..", for the same paths the crates were always listed by
            crate_paths = [
                str(crate)
                for crate in Path(os.path.normpath(path)).iterdir()
                if crate.is_file() and crate.name.endswith(cls.EXTENSION)
            ]
        elif path.is_file():
            crate_paths = [file_or_dir]
        else:
            raise FileNotFoundError(f"does not exist: {file_or_dir}")

        return crate_paths
