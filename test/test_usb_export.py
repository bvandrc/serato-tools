import logging
import os
from dataclasses import dataclass
from unittest import mock

import pytest

from serato_tools import usb_export
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2

from test.helpers.bin_files import TEST_DATABASE
from test.helpers.cli import cli_args
from test.helpers.files import copy_into, read_bytes


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


@dataclass
class Export:
    """A local library and music folder, and a drive to export them to."""

    serato_dir: str
    music_dir: str
    drive: str

    def music(self, name: str, content: bytes = b"audio") -> str:
        """A file in the music folder, with `content`."""
        path = os.path.join(self.music_dir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def crate(self, name: str, tracks: list[str]) -> str:
        crate = Crate(os.path.join(self.serato_dir, Crate.DIR, name + Crate.EXTENSION))
        crate.add_tracks(tracks)
        crate.save()
        return crate.filepath

    def add_to_database(self, *tracks: str):
        """Adds `tracks` to the local database, each marked played."""
        db = DatabaseV2()
        for track in tracks:
            db.entries.append(
                (
                    DatabaseV2.Fields.TRACK,
                    [
                        (DatabaseV2.Fields.FILE_PATH, DatabaseV2.get_relative_path(track)),
                        (DatabaseV2.Fields.PLAYED, True),
                    ],
                )
            )
        db.save()

    def on_drive(self, *parts: str) -> str:
        return os.path.join(self.drive, *parts)


@pytest.fixture
def export(tmp_dir: str, monkeypatch: pytest.MonkeyPatch) -> Export:
    serato_dir, music_dir, drive = (os.path.join(tmp_dir, name) for name in ["_Serato_", "Music", "Drive"])
    os.makedirs(os.path.join(serato_dir, Crate.DIR))
    os.mkdir(music_dir)
    os.mkdir(drive)
    db_file = copy_into(serato_dir, TEST_DATABASE, DatabaseV2.FILENAME)
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DIR", serato_dir)
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DRIVE", os.path.splitdrive(tmp_dir)[0])
    # DatabaseV2() reads the database at its default path, which is fixed when the class is defined
    monkeypatch.setattr(DatabaseV2.__init__, "__defaults__", (db_file,))
    return Export(serato_dir, music_dir, drive)


def test_copy_crates_to_usb(export: Export):
    a, b = export.music("A.mp3", b"a"), export.music("B.mp3", b"b")
    stems = export.music("B.serato-stems", b"stems")
    export.add_to_database(a, b)
    crates = [export.crate("House", [a, b]), export.crate("Deep", [b])]
    with open(os.path.join(export.serato_dir, "neworder.pref"), "w", encoding="utf-8") as f:
        f.write("[begin record]\n[crate]House\n[crate]Deep\n[crate]Stems\n[end record]\n")
    stale = export.on_drive("_Serato_", "Stale.txt")
    os.makedirs(os.path.dirname(stale))
    open(stale, "wb").close()

    usb_export.copy_crates_to_usb(crates, export.drive, "Tracks", root_crate="Root")

    # as Serato stores paths on a drive: from its root
    on_drive = ["Tracks/A.mp3", "Tracks/B.mp3"]
    exported_crates = os.path.join(export.drive, "_Serato_", Crate.DIR)
    assert sorted(os.listdir(exported_crates)) == ["Root%%Deep.crate", "Root%%House.crate"], "inside the root crate"
    assert Crate(os.path.join(exported_crates, "Root%%House.crate")).get_track_paths() == on_drive
    assert Crate(os.path.join(exported_crates, "Root%%Deep.crate")).get_track_paths() == on_drive[1:]

    db = DatabaseV2(export.on_drive("_Serato_", DatabaseV2.FILENAME))
    assert db.get_track_paths() == on_drive, "only the crates' tracks, at their new paths"
    assert all(t.get_value(DatabaseV2.Fields.PLAYED) is False for t in db.get_tracks()), "played reset"

    with open(export.on_drive("_Serato_", "neworder.pref"), encoding="utf-8") as f:
        assert f.read() == "[begin record]\n[crate]Root%%House\n[crate]Root%%Deep\n[crate]Stems\n[end record]\n"
    assert not os.path.exists(stale), "the drive's old library replaced"
    for src, name in [(a, "A.mp3"), (b, "B.mp3"), (stems, "B.serato-stems")]:
        assert read_bytes(export.on_drive("Tracks", name)) == read_bytes(src), f"{name} copied"


def test_copy_crates_to_usb_copies_only_changed_files(export: Export):
    a, b = export.music("A.mp3", b"a"), export.music("B.mp3", b"b")
    crates = [export.crate("House", [a, b])]
    usb_export.copy_crates_to_usb(crates, export.drive, "Tracks")

    with mock.patch.object(usb_export.shutil, "copy2", wraps=usb_export.shutil.copy2) as copy2:
        usb_export.copy_crates_to_usb(crates, export.drive, "Tracks")
        assert copy2.call_count == 0, "nothing changed, so nothing copied"

        export.music("B.mp3", b"b changed")
        usb_export.copy_crates_to_usb(crates, export.drive, "Tracks")
    assert [os.path.basename(c.args[0]) for c in copy2.call_args_list] == ["B.mp3"]
    assert read_bytes(export.on_drive("Tracks", "B.mp3")) == b"b changed"


def test_copy_crates_to_usb_warns_of_a_missing_file(export: Export, caplog: pytest.LogCaptureFixture):
    a, gone = export.music("A.mp3", b"a"), os.path.join(export.music_dir, "Gone.mp3")
    crates = [export.crate("House", [a, gone])]

    with caplog.at_level(logging.WARNING):
        usb_export.copy_crates_to_usb(crates, export.drive, "Tracks")

    assert f"does not exist - {gone}" in caplog.text
    assert read_bytes(export.on_drive("Tracks", "A.mp3")) == b"a", "the other track still copied"


def test_copy_crates_to_usb_needs_the_drive_to_exist(export: Export):
    with pytest.raises(FileNotFoundError):
        usb_export.copy_crates_to_usb([], os.path.join(export.drive, "Missing"), "Tracks")
