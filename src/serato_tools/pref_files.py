"""Serato's pref files that list crates by name, in the library folder: its crate order, `neworder.pref`, and its
collapsed crates, `collapsed.pref`."""

from dataclasses import dataclass
from pathlib import Path

from serato_tools.utils import SERATO_DIR


class _SeratoPrefFile:
    """One of Serato's pref files that list crates by name, read and written as lines of text.

    A subclass sets `FILENAME`, and turns the file's lines into its own fields (`_parse`) and back (`_to_lines`).
    """

    FILENAME: str
    # the subclass's file in the default library, set from FILENAME
    DEFAULT_FILE: Path
    # in UTF-16-BE on every OS
    _ENCODING = "utf-16-be"

    def __init_subclass__(cls, **kwargs: object):
        super().__init_subclass__(**kwargs)
        cls.DEFAULT_FILE = Path(SERATO_DIR, cls.FILENAME)

    def __init__(self, file: str | None = None):
        """Loads the file at `file`, the default library's by default.

        Raises FileNotFoundError if it doesn't exist, and ValueError if it isn't UTF-16-BE text.
        """
        self.path = Path(file) if file else self.DEFAULT_FILE
        # read and written in binary, since Serato's \n line endings would be written as \r\n on Windows: one byte that
        # misaligns every UTF-16 character after it
        self._parse(self.path.read_bytes().decode(self._ENCODING).split("\n"))

    def save(self, file: str | None = None):
        """Writes the file to `file`, or to the path it was loaded from."""
        (Path(file) if file else self.path).write_bytes("\n".join(self._to_lines()).encode(self._ENCODING))

    def _parse(self, lines: list[str]):
        """Sets the subclass's fields from the file's lines."""
        raise NotImplementedError

    def _to_lines(self) -> list[str]:
        """The file's lines, from the subclass's fields."""
        raise NotImplementedError


class CrateOrder(_SeratoPrefFile):
    """Serato's crate order file: the order it lists the library's crates and smart crates in, by name.

    `crates` holds the names in order, each with its parents' before it, separated with `%%` in a regular crate's
    (`Bass%%DnB`) and `≫≫` in a smart crate's. Change the list and `save()` to reorder, add, or remove crates. The
    file's other lines are kept as they are.
    """

    FILENAME = "neworder.pref"
    # how a line names a crate
    _CRATE_KEY = "[crate]"

    def _parse(self, lines: list[str]):
        self.crates: list[str] = [line.removeprefix(self._CRATE_KEY) for line in lines if self._is_crate(line)]
        # the other lines, either side of where the crates are written back: where the first one was, or after the
        # first line ("[begin record]") if there are none
        first_crate = next((i for i, line in enumerate(lines) if self._is_crate(line)), min(1, len(lines)))
        self._lines_before = lines[:first_crate]
        self._lines_after = [line for line in lines[first_crate:] if not self._is_crate(line)]

    def _to_lines(self) -> list[str]:
        return [*self._lines_before, *(self._CRATE_KEY + name for name in self.crates), *self._lines_after]

    @classmethod
    def _is_crate(cls, line: str) -> bool:
        return line.startswith(cls._CRATE_KEY)


class CollapsedCrates(_SeratoPrefFile):
    """Serato's collapsed crates file: the crates whose subcrates its sidebar hides, by name.

    `crates` holds their names, as `CrateOrder` writes them. Change the list and `save()` to collapse or expand crates.
    Raises ValueError for a file that isn't a record per crate, as Serato writes it, rather than risk rewriting one it
    doesn't understand.
    """

    FILENAME = "collapsed.pref"
    _BEGIN_RECORD, _END_RECORD = "[begin record]", "[end record]"
    # how a crate is named: [playlist] in the files Serato was seen writing, [crate] as in the crate order
    _CRATE_KEYS = ("[playlist]", "[crate]")

    def _parse(self, lines: list[str]):
        # each crate is a record of three lines, and the file ends with a \n
        if lines[-1:] != [""] or (len(lines) - 1) % 3:
            raise ValueError(f"not a record per crate: {self.path}")
        self.crates: list[str] = []
        # each crate's key, so an unchanged file is written back as it was
        self._keys: dict[str, str] = {}
        for i in range(0, len(lines) - 1, 3):
            begin, line, end = lines[i : i + 3]
            key = next((k for k in self._CRATE_KEYS if line.startswith(k)), None)
            if (begin, end) != (self._BEGIN_RECORD, self._END_RECORD) or key is None:
                raise ValueError(f"not a record per crate, at line {i + 1}: {self.path}")
            name = line.removeprefix(key)
            self.crates.append(name)
            self._keys[name] = key

    def _to_lines(self) -> list[str]:
        lines: list[str] = []
        for name in self.crates:
            lines += [self._BEGIN_RECORD, self._keys.get(name, self._CRATE_KEYS[0]) + name, self._END_RECORD]
        return [*lines, ""]


def main():
    """The `serato_pref_files` CLI: prints a pref file's crates, in order.

    The file is read as collapsed crates if it's named `collapsed.pref`, and as a crate order otherwise. With no file,
    prints the default library's crate order and collapsed crates, each under a heading, skipping a file it doesn't
    have.
    """
    # ruff: disable[PLC0415, T201]
    import argparse

    @dataclass
    class Args:
        file: Path | None

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="A pref file to print (crate order or collapsed). Default: the library's crate order and collapsed crates,"
        f" {CrateOrder.DEFAULT_FILE} and {CollapsedCrates.DEFAULT_FILE}",
    )
    args = Args(**vars(parser.parse_args()))

    if args.file is not None:
        # the two files' records look alike, so the file's name says which it is
        is_collapsed = args.file.name.casefold() == CollapsedCrates.FILENAME
        print("\n".join((CollapsedCrates if is_collapsed else CrateOrder)(str(args.file)).crates))
        return
    sections = [
        (heading, cls().crates)
        for heading, cls in (("Crate order", CrateOrder), ("Collapsed crates", CollapsedCrates))
        if cls.DEFAULT_FILE.is_file()
    ]
    print("\n\n".join(f"{heading}:\n" + "\n".join(f"  {crate}" for crate in crates) for heading, crates in sections))
    # ruff: enable[PLC0415, T201]


if __name__ == "__main__":
    main()
