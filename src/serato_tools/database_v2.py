"""Serato's library database (`database V2`), which holds every track's path and the values Serato shows for it."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from serato_tools.utils import SERATO_DIR
from serato_tools.utils.bin_file_base import SeratoBinFile


class DatabaseV2(SeratoBinFile):
    """Serato's library database file (`database V2`).

    It holds one entry per track, with its path and the values Serato shows.

    For changes that have to reach the crates too, such as renaming a track's file, use `Library`.
    """

    TESTED_VERSIONS = frozenset({"2.0/Serato Scratch LIVE Database"})
    FILENAME = "database V2"
    # TODO(breaking): change to a Path
    DEFAULT_DATABASE_FILE = str(Path(SERATO_DIR, FILENAME))
    TRACK_PATH_KEY = SeratoBinFile.Fields.FILE_PATH

    DEFAULT_ENTRIES: ClassVar[SeratoBinFile.EntryList] = [
        (SeratoBinFile.Fields.VERSION, "2.0/Serato Scratch LIVE Database"),
    ]

    def __init__(self, file: str = DEFAULT_DATABASE_FILE):
        """Parses the database at `file`, Serato's own by default; raises FileNotFoundError if it doesn't exist."""
        super().__init__(file=file)

    def get_corrupt_tracks(self) -> dict[str, str]:
        """The full path of each track Serato marked corrupt, with the reason Serato gives, or "" if it gave none."""
        fields = SeratoBinFile.Fields
        corrupt: dict[str, str] = {}
        for track in self.get_tracks():
            if fields.CORRUPT in track.fields and track.get_value(fields.CORRUPT, bool):
                reason = track.get_value(fields.CORRUPT_REASON, str) if fields.CORRUPT_REASON in track.fields else ""
                corrupt[track.full_path] = reason
        return corrupt

    def set_unanalyzed(self, filepaths: Iterable[str]) -> bool:
        """Marks the tracks as not yet analyzed, so Serato analyzes them again, and returns whether any changed.

        For a track whose audio changed, since Serato otherwise keeps its old analysis. Doesn't save.
        """
        overview_built = SeratoBinFile.Fields.OVERVIEW_BUILT

        def set_unanalyzed(track: SeratoBinFile.Track) -> SeratoBinFile.Track:
            # Serato sets this False when it adds a track, and True once it's analyzed it
            track.set_value(overview_built, False)
            return track

        return self.modify_tracks(set_unanalyzed, files=filepaths)


if __name__ == "__main__":
    # ruff: disable[T201]
    import argparse

    @dataclass
    class Args:
        file: Path
        find_missing: bool
        list_corrupt: bool

    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="?", type=Path, default=DatabaseV2.DEFAULT_DATABASE_FILE)
    parser.add_argument("--find_missing", action="store_true", help="List files that do not exist")
    parser.add_argument("--list_corrupt", action="store_true", help="List tracks Serato marked corrupt, and why")
    args = Args(**vars(parser.parse_args()))

    db = DatabaseV2(str(args.file))

    if args.find_missing:
        # TODO: actually look for that missing flag.
        db.find_missing()
    elif args.list_corrupt:
        for path, reason in db.get_corrupt_tracks().items():
            print(f"{path}: {reason}")
    else:
        print(db)
    # ruff: enable[T201]
