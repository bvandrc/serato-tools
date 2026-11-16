import os
from typing import Callable

import pytest

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.library import Library
from serato_tools.utils import HOME_TRACK_PATH_ROOT, get_track_path_root

from test.helpers.bin_files import TEST_DATABASE
from test.helpers.files import copy_into, mock_files
from test.helpers.platforms import POSIX_ONLY, WINDOWS_ONLY

type AsMount = Callable[..., None]


@pytest.fixture
def drive(tmp_dir: str) -> str:
    """A folder standing in for an external drive's root (e.g. E:\\ or /Volumes/USB), with _Serato_ and Music in it."""
    drive = os.path.join(os.path.realpath(tmp_dir), "USB")
    mock_files({os.path.join(drive, "_Serato_", Crate.DIR): [], os.path.join(drive, "Music"): []})
    return drive


@pytest.fixture
def as_mount(monkeypatch: pytest.MonkeyPatch) -> AsMount:
    """Makes os.path.ismount report only the mount points it's called with as mounted, for the rest of the test."""

    def as_mount(*mount_points: str):
        mounted = {os.path.normcase(p) for p in mount_points}
        monkeypatch.setattr(os.path, "ismount", lambda p: os.path.normcase(p) in mounted)

    return as_mount


@pytest.mark.parametrize(
    "parts",
    [
        pytest.param([DatabaseV2.FILENAME], id="database"),
        pytest.param([Crate.DIR, "House.crate"], id="crate"),
        pytest.param([Crate.DIR, "Serato Stems", "Stems.crate"], id="crate in a subfolder"),
    ],
)
def test_root_of_external_drive_library(drive: str, as_mount: AsMount, parts: list[str]):
    as_mount(drive)
    assert get_track_path_root(os.path.join(drive, "_Serato_", *parts)) == drive


def test_root_of_home_library_is_its_drive_root(drive: str, as_mount: AsMount):
    as_mount()
    serato_dir = os.path.join(drive, "_Serato_")
    drive_root = os.path.join(os.path.splitdrive(serato_dir)[0], os.sep)
    assert get_track_path_root(os.path.join(serato_dir, DatabaseV2.FILENAME)) == drive_root


def test_root_of_file_outside_a_serato_folder_is_home_library_root(drive: str, as_mount: AsMount):
    as_mount(drive)
    assert get_track_path_root(os.path.join(drive, "Music", "Exported.crate")) == HOME_TRACK_PATH_ROOT


def test_paths_relative_to_given_root(drive: str):
    track = os.path.join(drive, "Music", "Track.mp3")
    assert DatabaseV2.get_relative_path(track, drive) == "Music/Track.mp3"
    assert DatabaseV2.get_full_path("Music/Track.mp3", drive) == track


def test_path_in_a_sibling_of_the_root_is_outside_it(drive: str):
    # a sibling folder whose name starts with the root's isn't inside it
    sibling_track = os.path.join(drive + "2", "Music", "Track.mp3")
    with pytest.raises(ValueError):
        DatabaseV2.get_relative_path(sibling_track, drive)


def test_relative_path_is_taken_as_relative_to_root(drive: str):
    assert DatabaseV2.get_relative_path(os.path.join("Music", "Track.mp3"), drive) == "Music/Track.mp3"


@WINDOWS_ONLY
def test_home_library_drops_another_drive():
    # only Windows has paths outside the home library's root, on another drive; unlike an external library, the home
    # library keeps the old behavior for one
    other_drive = "Z:" if not HOME_TRACK_PATH_ROOT.upper().startswith("Z") else "Y:"
    assert DatabaseV2.get_relative_path(f"{other_drive}\\Music\\Track.mp3", HOME_TRACK_PATH_ROOT) == "Music/Track.mp3"


@pytest.mark.parametrize(
    "drive_root, track, serato_file",
    [
        pytest.param(
            "E:\\", "E:\\Music\\Track.mp3", "E:\\_Serato_\\database V2", id="Windows drive letter", marks=WINDOWS_ONLY
        ),
        pytest.param(
            "/Volumes/USB",
            "/Volumes/USB/Music/Track.mp3",
            "/Volumes/USB/_Serato_/database V2",
            id="POSIX mount point",
            marks=POSIX_ONLY,
        ),
    ],
)
def test_external_drive_paths(as_mount: AsMount, drive_root: str, track: str, serato_file: str):
    assert DatabaseV2.get_relative_path(track, drive_root) == "Music/Track.mp3"
    assert DatabaseV2.get_full_path("Music/Track.mp3", drive_root) == track
    as_mount(drive_root)
    assert get_track_path_root(serato_file) == drive_root


def test_external_drive_library_tracks(drive: str, as_mount: AsMount):
    as_mount(drive)
    serato_dir = os.path.join(drive, "_Serato_")
    copy_into(serato_dir, TEST_DATABASE, DatabaseV2.FILENAME)
    old, kept = mock_files({os.path.join(drive, "Music"): ["Old.mp3", "Kept.mp3"]})
    new = os.path.join(drive, "Music", "New.mp3")

    crate = Crate(os.path.join(serato_dir, Crate.DIR, "USB.crate"))
    crate.add_tracks([old, kept])
    assert crate.get_track_paths() == ["Music/Old.mp3", "Music/Kept.mp3"], "stored relative to the drive"
    assert crate.get_track_paths(include_drive=True) == [old, kept], "resolved from the drive"
    crate.save()

    library = Library(serato_dir)
    library.rename_track_file(old, new)
    assert Crate(crate.filepath).get_track_paths() == ["Music/New.mp3", "Music/Kept.mp3"], "renamed"

    library.remove_track_files([new])
    assert Crate(crate.filepath).get_track_paths() == ["Music/Kept.mp3"], "removed"
    assert not os.path.exists(new), "file deleted"


def test_external_drive_library_rejects_track_on_another_drive(drive: str, as_mount: AsMount):
    as_mount(drive)
    crate = Crate(os.path.join(drive, "_Serato_", Crate.DIR, "USB.crate"))
    other_drive_track = os.path.join(os.path.dirname(drive), "Other", "Music", "Track.mp3")
    with pytest.raises(ValueError):
        crate.add_tracks([other_drive_track])
    assert crate.get_track_paths() == [], "nothing added"
