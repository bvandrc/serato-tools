import os
from unittest import mock

import pytest

from serato_tools import usb_export

from test.helpers.cli import cli_args


@pytest.fixture
def crate_dirs(tmp_dir: str, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Empty Subcrates and SmartCrates folders, which get_crate_files looks in, in that order."""
    crate_dir = os.path.join(tmp_dir, usb_export.Crate.DIR)
    smart_crate_dir = os.path.join(tmp_dir, usb_export.SmartCrate.DIR)
    os.makedirs(crate_dir)
    os.makedirs(smart_crate_dir)
    monkeypatch.setattr(usb_export.Crate, "DIR_PATH", crate_dir)
    monkeypatch.setattr(usb_export.SmartCrate, "DIR_PATH", smart_crate_dir)
    return crate_dir, smart_crate_dir


def add_files(crate_dirs: tuple[str, str], *names: str):
    """Adds an empty file for each of `names`: a smart crate's to SmartCrates, anything else to Subcrates."""
    crate_dir, smart_crate_dir = crate_dirs
    for name in names:
        folder = smart_crate_dir if name.endswith(usb_export.SmartCrate.EXTENSION) else crate_dir
        with open(os.path.join(folder, name), "w", encoding="utf-8"):
            pass


def matched_names(pattern: str) -> set[str]:
    return {os.path.basename(f) for f in usb_export.get_crate_files(pattern)}


@pytest.mark.parametrize(
    "names, pattern, matched",
    [
        # "house*" is also a valid regex whose .search() would match "housing"
        pytest.param(["house.crate", "housing.crate"], "house*", {"house.crate"}, id="glob tried before regex"),
        pytest.param(
            ["house.crate", "house.scrate"], "*house*", {"house.crate", "house.scrate"}, id="glob matches both kinds"
        ),
        pytest.param(
            ["deep.crate", "house.crate", "techno.crate"],
            "deep|house",
            {"deep.crate", "house.crate"},
            id="invalid as a glob match, so regex",
        ),
        pytest.param(["house.crate", ".DS_Store", "notes.txt"], "*", {"house.crate"}, id="non-crate files never"),
        pytest.param(["house.crate"], "*[techno*", set(), id="invalid regex and no glob match"),
    ],
)
def test_get_crate_files(crate_dirs: tuple[str, str], names: list[str], pattern: str, matched: set[str]):
    add_files(crate_dirs, *names)
    assert matched_names(pattern) == matched


def test_get_crate_files_without_a_smart_crates_folder(crate_dirs: tuple[str, str]):
    add_files(crate_dirs, "house.crate")
    os.rmdir(crate_dirs[1])
    assert matched_names("*") == {"house.crate"}


@pytest.mark.parametrize(
    "drive, system, dest",
    [
        pytest.param("E", "Windows", "E:\\", id="drive letter becomes drive root"),
        pytest.param("/Volumes/USB", "Darwin", "/Volumes/USB", id="drive folder kept"),
    ],
)
def test_cli_exports_to_the_drive(drive: str, system: str, dest: str):
    with (
        cli_args("serato_usb_export", "--drive", drive, "--crates", "*"),
        mock.patch.object(usb_export.platform, "system", return_value=system),
        mock.patch.object(usb_export, "get_crate_files", return_value=[]),
        mock.patch.object(usb_export, "copy_crates_to_usb") as copy_crates_to_usb,
    ):
        usb_export.main()
    assert copy_crates_to_usb.call_args.kwargs["dest_drive_dir"] == dest
