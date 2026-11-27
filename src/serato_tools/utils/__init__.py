"""The default Serato folder and the package's logger, shared by every module."""

import logging
from pathlib import Path

logger = logging.getLogger("serato-tools")

SERATO_DIR_NAME = "_Serato_"
# TODO(breaking): change to a Path
SERATO_DIR = str(Path.home() / "Music" / SERATO_DIR_NAME)
SERATO_DRIVE = Path(SERATO_DIR).drive
