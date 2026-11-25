"""The default Serato folder and the package's logger, shared by every module."""

import logging
import os

logger = logging.getLogger("serato-tools")

SERATO_DIR_NAME = "_Serato_"
SERATO_DIR = os.path.join(os.path.expanduser("~"), "Music", SERATO_DIR_NAME)
SERATO_DRIVE = os.path.splitdrive(SERATO_DIR)[0]
# the folder the home library's track paths are relative to: the root of the drive it's on
HOME_TRACK_PATH_ROOT = os.path.join(SERATO_DRIVE, os.sep)


def get_track_path_root(file: str) -> str:
    """The folder that the track paths in a Serato library file are relative to.

    Serato stores track paths relative to the root of the drive its `_Serato_` folder is on: `E:\\` or `/Volumes/<drive>`
    for a library on an external drive, or the system drive's root for the home library (`~/Music/_Serato_`). A file
    outside any `_Serato_` folder is treated as part of the home library.
    """
    path = os.path.abspath(file)
    while os.path.basename(path).lower() != SERATO_DIR_NAME.lower():
        parent = os.path.dirname(path)
        if parent == path:
            return HOME_TRACK_PATH_ROOT
        path = parent
    # an external drive keeps its _Serato_ folder at the drive's root, while the home library keeps it in the user's
    # Music folder, so the folder holding _Serato_ is a mount point only for an external drive
    drive_root = os.path.dirname(path)
    if os.path.ismount(drive_root):
        return drive_root
    return os.path.join(os.path.splitdrive(path)[0], os.sep)
