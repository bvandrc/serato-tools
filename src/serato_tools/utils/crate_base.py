# This is from this repo: https://github.com/sharst/seratopy
"""What crates and smart crates share: their file extension and folder, track paths, and how they print."""

import os
import warnings
from collections.abc import Iterable

from serato_tools.utils.bin_file_base import SeratoBinFile


class CrateBase(SeratoBinFile):
    """A crate or smart crate file, which holds a list of track paths.

    Subclasses give it an `EXTENSION` and a `DIR`.
    """

    EXTENSION: str
    DIR: str
    DIR_PATH: str
    TRACK_PATH_KEY = SeratoBinFile.Fields.TRACK_PATH

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
            track_paths = [os.path.splitext(os.path.basename(t))[0] for t in track_paths]
        print("\n".join(track_paths))

    def save(self, file: str | None = None):
        """As `SeratoBinFile.save`, but raises ValueError if `file` doesn't end with this class's `EXTENSION`."""
        if file is None:
            file = self.filepath

        if not file.endswith(self.EXTENSION):
            raise ValueError(f"file should end with {self.EXTENSION}: " + file)

        super().save(file)

    def add_track(self, filepath: str):
        """Deprecated, to be removed in the next major version: use add_tracks(), which this calls."""
        warnings.warn("add_track is deprecated, use add_tracks instead", DeprecationWarning, stacklevel=2)
        self.add_tracks([filepath])

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
                self.entries.append((CrateBase.Fields.TRACK, [(CrateBase.Fields.TRACK_PATH, relpath)]))
                existing.add(relpath.upper())

    def add_tracks_from_dir(self, dir: str, replace: bool = False):
        """Adds every file directly in `dir` but hidden ones, such as `.DS_Store`; with `replace`, first removes every
        track that isn't one of them."""
        dir_tracks = [
            self.get_relative_path(path)
            for name in os.listdir(dir)
            # not a subfolder, which isn't a track
            if not name.startswith(".") and os.path.isfile(path := os.path.join(dir, name))
        ]

        if replace:
            # one filter pass instead of a full scan per removed track; matched whatever their case, as add_tracks
            # matches them, so a track in the crate in another case is kept rather than removed and added again
            dir_track_set = {track.upper() for track in dir_tracks}
            self.filter_tracks(lambda track: track.relpath.upper() in dir_track_set)

        self.add_tracks(dir_tracks)

    @classmethod
    def get_crate_files(cls, file_or_dir: str | None = None) -> list[str]:
        """The paths of this class's crate files directly in `file_or_dir`, or just `file_or_dir` if it's a file.

        Defaults to this class's folder in the default Serato folder (`DIR_PATH`). Raises FileNotFoundError if
        `file_or_dir` doesn't exist.
        """
        if file_or_dir is None:
            file_or_dir = cls.DIR_PATH

        crate_paths: list[str] = []
        if os.path.isdir(file_or_dir):

            for fname in os.listdir(file_or_dir):
                path = os.path.normpath(os.path.join(file_or_dir, fname))
                if os.path.isfile(path) and path.endswith(cls.EXTENSION):
                    crate_paths.append(path)
        elif os.path.isfile(file_or_dir):
            crate_paths = [file_or_dir]
        else:
            raise FileNotFoundError("does not exist: " + file_or_dir)

        return crate_paths
