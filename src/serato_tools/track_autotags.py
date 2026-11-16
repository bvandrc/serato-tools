"""The `Serato Autotags` tag, which holds the BPM and gain values Serato's analysis found for a track."""

import io
from dataclasses import dataclass

from serato_tools.utils.track_tags import GeobKeys, SeratoGeobTag


class TrackAutotags(SeratoGeobTag):
    """The `Serato Autotags` tag: the track's `bpm`, `autogain`, and `gaindb`, each None if the tag isn't set."""

    GEOB_KEY = GeobKeys.AUTOTAGS
    VERSION = (0x01, 0x01)

    def __init__(self, file_or_data: SeratoGeobTag.FileOrData):
        super().__init__(file_or_data)

        self.bpm: float | None = None
        self.autogain: float | None = None
        self.gaindb: float | None = None

        if self._raw_data is not None:
            self.bpm, self.autogain, self.gaindb = self._parse(self._raw_data)

    def __str__(self) -> str:
        return f"bpm: {self.bpm}\nautogain: {self.autogain}\ngaindb: {self.gaindb}"

    def _parse(self, data: bytes):
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        def get_value():
            value = self._readbytes(fp).decode("ascii")
            return float(value)

        bpm = get_value()
        autogain = get_value()
        gaindb = get_value()
        return bpm, autogain, gaindb

    def _serialize(self):
        # explicit attribute accesses rather than getattr(self, name): pyright checks these, so a
        # typo'd field is a type error, where a typo'd getattr string would silently pass
        missing = [
            name
            for name, value in (("bpm", self.bpm), ("autogain", self.autogain), ("gaindb", self.gaindb))
            if value is None
        ]
        if missing:
            raise ValueError(f"must be set to write the Serato Autotags tag: {', '.join(missing)}")
        data: bytes = self._pack_version()
        for value, decimals in ((self.bpm, 2), (self.autogain, 3), (self.gaindb, 3)):
            data += "{:.{}f}".format(value, decimals).encode("ascii")
            data += b"\x00"
        self._raw_data = data

    def set(
        self,
        bpm: float | None = None,
        autogain: float | None = None,
        gaindb: float | None = None,
    ):
        """Sets the values given, leaving the rest, in memory; call `save()` to write them to the file.

        Raises ValueError if that leaves any unset, which happens when the file had no `Serato Autotags` tag.
        """
        if bpm is not None:
            self.bpm = bpm
        if autogain is not None:
            self.autogain = autogain
        if gaindb is not None:
            self.gaindb = gaindb
        self._serialize()


if __name__ == "__main__":
    import argparse

    from serato_tools.utils.cli import open_tag_file_or_data

    @dataclass
    class Args:
        file: str

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = Args(**vars(parser.parse_args()))

    tags = open_tag_file_or_data(TrackAutotags, args.file)
    print(str(tags))  # noqa: T201
