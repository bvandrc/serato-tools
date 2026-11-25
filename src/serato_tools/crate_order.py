"""Serato's crate order file, `neworder.pref` in the library folder."""

import os

from serato_tools.utils import SERATO_DIR


class CrateOrder:
    """Serato's crate order file: the order it lists the library's crates and smart crates in, by name.

    `crates` holds the names in order, each with its parents' before it, separated with `%%` in a regular crate's
    (`Bass%%DnB`) and `≫≫` in a smart crate's. Change the list and `save()` to reorder, add, or remove crates. The
    file's other lines are kept as they are.
    """

    FILENAME = "neworder.pref"
    DEFAULT_FILE = os.path.join(SERATO_DIR, FILENAME)
    # in UTF-16-BE on every OS
    _ENCODING = "utf-16-be"
    # how a line names a crate
    _CRATE_KEY = "[crate]"

    def __init__(self, file: str = DEFAULT_FILE):
        """Loads the crate order file at `file`, the default library's by default.

        Raises FileNotFoundError if it doesn't exist, and ValueError if it isn't UTF-16-BE text.
        """
        self.filepath = file
        # read and written in binary, since Serato's \n line endings would be written as \r\n on Windows: one byte that
        # misaligns every UTF-16 character after it
        with open(file, "rb") as f:
            lines = f.read().decode(self._ENCODING).split("\n")
        self.crates: list[str] = [line.removeprefix(self._CRATE_KEY) for line in lines if self._is_crate(line)]
        # the other lines, either side of where the crates are written back: where the first one was, or after the
        # first line ("[begin record]") if there are none
        first_crate = next((i for i, line in enumerate(lines) if self._is_crate(line)), min(1, len(lines)))
        self._lines_before = lines[:first_crate]
        self._lines_after = [line for line in lines[first_crate:] if not self._is_crate(line)]

    def save(self, file: str | None = None):
        """Writes the order to `file`, or to the path it was loaded from."""
        lines = [*self._lines_before, *(self._CRATE_KEY + name for name in self.crates), *self._lines_after]
        with open(file or self.filepath, "wb") as f:
            f.write("\n".join(lines).encode(self._ENCODING))

    @classmethod
    def _is_crate(cls, line: str) -> bool:
        return line.startswith(cls._CRATE_KEY)
