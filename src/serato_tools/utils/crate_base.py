#!/usr/bin/python
# This is from this repo: https://github.com/sharst/seratopy
import os
import sys
from typing import Optional, Iterable

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.bin_file_base import SeratoBinFile


class CrateBase(SeratoBinFile):
    EXTENSION: str
    DIR: str
    DIR_PATH: str
    TRACK_PATH_KEY = SeratoBinFile.Fields.TRACK_PATH

    def _stringify_entry(self, entry: SeratoBinFile.EntryFull, indent: int = 0) -> str:
        field, fieldname, value = entry  # pylint: disable=unused-variable
        if isinstance(value, list):
            return self._stringify_entries(value, indent)
        return str(value)

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
        track_paths = self.get_track_paths(include_drive=True)
        if filenames_only:
            track_paths = [os.path.splitext(os.path.basename(t))[0] for t in track_paths]
        print("\n".join(track_paths))

    def save(self, file: Optional[str] = None):
        if file is None:
            file = self.filepath

        if not file.endswith(self.EXTENSION):
            raise ValueError(f"file should end with {self.EXTENSION}: " + file)

        self._dump()
        super().save(file)

    def add_track(self, filepath: str):
        # filepath name must include the containing dir
        filepath = self.get_relative_path(filepath)

        if filepath in self.get_track_paths():
            return

        self.entries.append((CrateBase.Fields.TRACK, [(CrateBase.Fields.TRACK_PATH, filepath)]))
        self._dump()

    def add_tracks_from_dir(self, dir: str, replace: bool = False):
        dir_tracks = [self.get_relative_path(os.path.join(dir, t)) for t in os.listdir(dir)]

        if replace:
            for track in self.get_track_paths():
                if track not in dir_tracks:
                    self.remove_track(track)

        for track in dir_tracks:
            self.add_track(track)

    @classmethod
    def get_crate_files(cls, file_or_dir: str | None = None) -> list[str]:
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
