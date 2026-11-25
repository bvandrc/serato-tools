"""The default Serato folder and the package's logger, shared by every module."""

import logging
import os
from pathlib import Path

logger = logging.getLogger("serato-tools")

SERATO_DIR_NAME = "_Serato_"
SERATO_DIR = str(Path.home() / "Music" / SERATO_DIR_NAME)
SERATO_DRIVE = Path(SERATO_DIR).drive

# a file or folder's path, as a str or a path object such as pathlib.Path; functions taking one return str paths
type StrPath = str | os.PathLike[str]
