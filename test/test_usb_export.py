# pylint: disable=protected-access
import argparse
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from unittest import mock

import pytest

from serato_tools import usb_export
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate

from test.helpers.bin_files import LibraryFolders
from test.helpers.cli import cli_args
from test.helpers.files import mock_files, read_bytes

# the folder on the drive the tests export tracks to
DRIVE_TRACKS = "Tracks"


@pytest.fixture
def crate_dirs(tmp_dir: str) -> tuple[str, str]:
    """Empty Subcrates and SmartCrates folders in tmp_dir, which stands in for a library's _Serato_ folder.

    get_crate_files looks in them, in that order, given tmp_dir.
    """
    crate_dir = os.path.join(tmp_dir, usb_export.Crate.DIR)
    smart_crate_dir = os.path.join(tmp_dir, usb_export.SmartCrate.DIR)
    mock_files({crate_dir: [], smart_crate_dir: []})
    return crate_dir, smart_crate_dir


def add_files(crate_dirs: tuple[str, str], *names: str):
    """Adds an empty file for each of `names`: a smart crate's to SmartCrates, anything else to Subcrates."""
    crate_dir, smart_crate_dir = crate_dirs
    smart = usb_export.SmartCrate.EXTENSION
    mock_files(
        {
            crate_dir: [name for name in names if not name.endswith(smart)],
            smart_crate_dir: [name for name in names if name.endswith(smart)],
        }
    )


def matched_names(serato_dir: str, pattern: str) -> set[str]:
    return {os.path.basename(f) for f in usb_export.get_crate_files(pattern, serato_dir)}


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
def test_get_crate_files(tmp_dir: str, crate_dirs: tuple[str, str], names: list[str], pattern: str, matched: set[str]):
    add_files(crate_dirs, *names)
    assert matched_names(tmp_dir, pattern) == matched


def test_get_crate_files_without_a_smart_crates_folder(tmp_dir: str, crate_dirs: tuple[str, str]):
    add_files(crate_dirs, "house.crate")
    os.rmdir(crate_dirs[1])
    assert matched_names(tmp_dir, "*") == {"house.crate"}


@dataclass
class Export(LibraryFolders):
    """A local library and music folder, and a drive to export them to."""

    drive: str

    def __post_init__(self):
        super().__post_init__()
        mock_files({os.path.join(self.serato_dir, Crate.DIR): [], self.drive: []})

    def export_crates(self, crate_files: list[str], **kwargs: Any):
        """Exports `crate_files` from this library to the drive, under DRIVE_TRACKS."""
        usb_export.copy_crates_to_usb(
            crate_files, self.drive, DRIVE_TRACKS, source_serato_dir=self.serato_dir, **kwargs
        )

    def exported_database(self) -> DatabaseV2:
        return DatabaseV2(self.on_drive("_Serato_", DatabaseV2.FILENAME))

    def on_drive(self, *parts: str) -> str:
        return os.path.join(self.drive, *parts)


@pytest.fixture
def export(tmp_dir: str) -> Export:
    """A library in tmp_dir, which isn't a drive's root, so its track paths are stored as the home library's are."""
    return Export(
        serato_dir=os.path.join(tmp_dir, "_Serato_"),
        music_dir=os.path.join(tmp_dir, "Music"),
        drive=os.path.join(tmp_dir, "Drive"),
    )


@pytest.fixture
def external_export(tmp_dir: str, monkeypatch: pytest.MonkeyPatch) -> Export:
    """A library at the root of a drive of its own, Source, as Serato keeps one on an external drive."""
    # resolved, so the paths the library resolves its tracks to match the ones the test made them at
    source = os.path.join(os.path.realpath(tmp_dir), "Source")
    mounted = os.path.normcase(source)
    monkeypatch.setattr(os.path, "ismount", lambda p: os.path.normcase(p) == mounted)
    return Export(
        serato_dir=os.path.join(source, "_Serato_"),
        music_dir=os.path.join(source, "Music"),
        drive=os.path.join(os.path.realpath(tmp_dir), "USB"),
    )


def test_copy_crates_to_usb(export: Export):
    a, b, not_exported = export.make_track("A.mp3", b"a"), export.make_track("B.mp3", b"b"), export.make_track("C.mp3")
    stems = export.make_track("B.serato-stems", b"stems")
    export.add_to_database(a, b, fields=[(DatabaseV2.Fields.PLAYED, True)])
    crates = [export.make_crate("House", [a, b]), export.make_crate("Deep", [b])]
    export.make_crate(os.path.join("Serato Stems", "Stems"), [b, not_exported])
    with open(os.path.join(export.serato_dir, "neworder.pref"), "w", encoding="utf-8") as f:
        f.write("[begin record]\n[crate]House\n[crate]Deep\n[crate]Stems\n[end record]\n")
    (stale,) = mock_files({export.on_drive("_Serato_"): ["Stale.txt"]})

    export.export_crates(crates, root_crate="Root")

    # as Serato stores paths on a drive: from its root
    on_drive = [f"{DRIVE_TRACKS}/A.mp3", f"{DRIVE_TRACKS}/B.mp3"]
    exported_crates = os.path.join(export.drive, "_Serato_", Crate.DIR)
    assert sorted(os.listdir(exported_crates)) == [
        "Root%%Deep.crate",
        "Root%%House.crate",
        "Serato Stems",
    ], "inside the root crate"
    assert Crate(os.path.join(exported_crates, "Root%%House.crate")).get_track_paths() == on_drive
    assert Crate(os.path.join(exported_crates, "Root%%Deep.crate")).get_track_paths() == on_drive[1:]
    stems_crate = Crate(os.path.join(export.drive, "_Serato_", Crate.SERATO_STEMS_CRATE_PATH))
    assert stems_crate.get_track_paths() == on_drive[1:], "the stems crate, with only the exported tracks"

    db = export.exported_database()
    assert db.get_track_paths() == on_drive, "only the crates' tracks, at their new paths"
    assert all(t.get_value(DatabaseV2.Fields.PLAYED) is False for t in db.get_tracks()), "played reset"

    with open(export.on_drive("_Serato_", "neworder.pref"), encoding="utf-8") as f:
        assert f.read() == "[begin record]\n[crate]Root%%House\n[crate]Root%%Deep\n[crate]Stems\n[end record]\n"
    assert not os.path.exists(stale), "the drive's old library replaced"
    copied = {"A.mp3": a, "B.mp3": b, "B.serato-stems": stems}
    assert sorted(os.listdir(export.on_drive(DRIVE_TRACKS))) == sorted(copied), "only the exported crates' tracks"
    for name, src in copied.items():
        assert read_bytes(export.on_drive(DRIVE_TRACKS, name)) == read_bytes(src), f"{name} copied"


def test_copy_crates_to_usb_copies_only_changed_files(export: Export):
    a, b = export.make_track("A.mp3", b"a"), export.make_track("B.mp3", b"b")
    crates = [export.make_crate("House", [a, b])]
    export.export_crates(crates)

    with mock.patch.object(usb_export.shutil, "copy2", wraps=usb_export.shutil.copy2) as copy2:
        export.export_crates(crates)
        assert copy2.call_count == 0, "nothing changed, so nothing copied"

        export.make_track("B.mp3", b"b changed")
        export.export_crates(crates)
    assert [os.path.basename(c.args[0]) for c in copy2.call_args_list] == ["B.mp3"]
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "B.mp3")) == b"b changed"


def test_copy_crates_to_usb_warns_of_a_missing_file(export: Export, caplog: pytest.LogCaptureFixture):
    a, gone = export.make_track("A.mp3", b"a"), os.path.join(export.music_dir, "Gone.mp3")
    crates = [export.make_crate("House", [a, gone])]

    with caplog.at_level(logging.WARNING):
        export.export_crates(crates)

    assert f"does not exist - {gone}" in caplog.text
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "A.mp3")) == b"a", "the other track still copied"


def test_copy_crates_to_usb_needs_the_drive_to_exist(export: Export):
    with pytest.raises(FileNotFoundError):
        usb_export.copy_crates_to_usb([], os.path.join(export.drive, "Missing"), DRIVE_TRACKS)


def test_copy_crates_to_usb_copies_each_tracks_own_stems(export: Export):
    # named after the track with or without its extension; the old prefix match took "A Extended"'s for "A.mp3" too
    tracks = [export.make_track(name) for name in ["A.mp3", "A Extended.mp3", "C.mp3"]]
    stems = {
        name: export.make_track(name, name.encode())
        for name in ["A.serato-stems", "A Extended.serato-stems", "C.mp3.serato-stems"]
    }

    export.export_crates([export.make_crate("House", tracks)])

    for name, src in stems.items():
        assert read_bytes(export.on_drive(DRIVE_TRACKS, name)) == read_bytes(src), f"{name} copied"


def test_copy_crates_to_usb_keeps_the_database_entry_of_the_track_it_copies(export: Export):
    # two tracks with one filename: the crate lists M1's first, the database M2's
    m1, m2 = export.make_track("M1/A.mp3", b"m1"), export.make_track("M2/A.mp3", b"m2")
    export.add_to_database(m2, fields=[(DatabaseV2.Fields.GENRE, "from M2")])
    export.add_to_database(m1, fields=[(DatabaseV2.Fields.GENRE, "from M1")])

    export.export_crates([export.make_crate("House", [m1, m2])])

    assert read_bytes(export.on_drive(DRIVE_TRACKS, "A.mp3")) == b"m1", "the first in the crates copied"
    exported_crate = Crate(export.on_drive("_Serato_", Crate.DIR, "House.crate"))
    assert exported_crate.get_track_paths() == [f"{DRIVE_TRACKS}/A.mp3"], "the crate lists it once"
    tracks = export.exported_database().get_tracks()
    assert [t.get_value(DatabaseV2.Fields.GENRE) for t in tracks] == ["from M1"], "with its own database entry"


def test_copy_crates_to_usb_writes_a_smart_crate_as_a_regular_crate(export: Export):
    a = export.make_track("A.mp3")
    smart_crate = export.make_crate("Parent≫≫Dubstep", [a], SmartCrate)

    export.export_crates([smart_crate])

    # a smart crate's subcrate separator in its filename is ≫≫, a regular crate's %%
    exported = Crate(export.on_drive("_Serato_", Crate.DIR, "Parent%%Dubstep.crate"))
    assert exported._version == Crate.DEFAULT_ENTRIES[0][1], "a regular crate, which Crate opens"
    assert exported.get_track_paths() == [f"{DRIVE_TRACKS}/A.mp3"]


def test_copy_crates_to_usb_raises_for_a_track_with_two_stems_files(export: Export):
    # stems files named both with the track's extension and without it, so which to copy isn't known
    a = export.make_track("A.mp3")
    export.make_track("A.serato-stems")
    export.make_track("A.mp3.serato-stems")
    with pytest.raises(ValueError, match="more than 1 stems file"):
        export.export_crates([export.make_crate("House", [a])])


def test_copy_crates_to_usb_skips_a_folder_in_the_crate_list(export: Export):
    house = export.make_crate("House", [export.make_track("A.mp3")])
    folder = os.path.join(export.serato_dir, Crate.DIR, "Folder")
    mock_files({folder: []})

    export.export_crates([folder, house])

    assert os.listdir(export.on_drive("_Serato_", Crate.DIR)) == ["House.crate"], "the crates after it still exported"
    assert os.listdir(export.on_drive(DRIVE_TRACKS)) == ["A.mp3"]


def test_copy_crates_to_usb_raises_for_a_file_that_isnt_a_crate(export: Export):
    notes = os.path.join(export.serato_dir, Crate.DIR, "notes.txt")
    with open(notes, "w", encoding="utf-8") as f:
        f.write("not a crate")
    with pytest.raises(ValueError, match="not a crate file"):
        export.export_crates([notes])


def test_copy_crates_to_usb_logs_the_database_and_stems_crate_it_writes(
    export: Export, caplog: pytest.LogCaptureFixture
):
    house = export.make_crate("House", [export.make_track("A.mp3")])
    export.make_crate(os.path.join("Serato Stems", "Stems"), [])

    with caplog.at_level(logging.INFO, "serato-tools"):
        export.export_crates([house])

    assert f"created database file {export.on_drive('_Serato_', DatabaseV2.FILENAME)}" in caplog.messages
    assert f"copied crate {export.on_drive('_Serato_', Crate.SERATO_STEMS_CRATE_PATH)}" in caplog.messages


def test_copy_crates_to_usb_leaves_the_library_as_it_was(export: Export):
    house = export.make_crate("House", [export.make_track("A.mp3")])
    crate_bytes, db_bytes = read_bytes(house), read_bytes(export.db_file)

    export.export_crates([house])

    assert read_bytes(house) == crate_bytes, "crate unchanged"
    assert read_bytes(export.db_file) == db_bytes, "database unchanged"


def test_copy_crates_to_usb_from_a_library_on_an_external_drive(external_export: Export):
    a, b = external_export.make_track("A.mp3", b"a"), external_export.make_track("B.mp3", b"b")
    external_export.add_to_database(a, b)
    house = external_export.make_crate("House", [a, b])
    assert Crate(house).get_track_paths() == ["Music/A.mp3", "Music/B.mp3"], "stored relative to its drive"

    external_export.export_crates([house])

    on_drive = [f"{DRIVE_TRACKS}/A.mp3", f"{DRIVE_TRACKS}/B.mp3"]
    assert Crate(external_export.on_drive("_Serato_", Crate.DIR, "House.crate")).get_track_paths() == on_drive
    assert sorted(external_export.exported_database().get_track_paths()) == on_drive, "only the copied tracks"
    assert read_bytes(external_export.on_drive(DRIVE_TRACKS, "A.mp3")) == b"a", "found on the source drive"
    assert read_bytes(external_export.on_drive(DRIVE_TRACKS, "B.mp3")) == b"b", "found on the source drive"


def test_copy_crates_to_usb_stores_a_full_tracks_path_relative_to_the_drive(export: Export):
    a = export.make_track("A.mp3")
    export.add_to_database(a)
    house = export.make_crate("House", [a])

    usb_export.copy_crates_to_usb(
        [house], export.drive, export.on_drive("DJ", "Tracks"), source_serato_dir=export.serato_dir
    )

    assert os.path.isfile(export.on_drive("DJ", "Tracks", "A.mp3")), "copied"
    assert Crate(export.on_drive("_Serato_", Crate.DIR, "House.crate")).get_track_paths() == ["DJ/Tracks/A.mp3"]
    assert export.exported_database().get_track_paths() == ["DJ/Tracks/A.mp3"]


@pytest.fixture
def source_library(tmp_dir: str) -> tuple[str, str]:
    """A drive holding a library to export from, and its _Serato_ folder."""
    drive = os.path.realpath(tmp_dir)
    serato_dir = os.path.join(drive, "_Serato_")
    mock_files({serato_dir: []})
    return drive, serato_dir


def run_cli(*args: str, system: str = "Darwin") -> Mapping[str, Any]:
    """Runs serato_usb_export with `args` as if on `system`, and returns the keyword arguments it exports with."""
    with (
        cli_args("serato_usb_export", "--crates", "*", *args),
        mock.patch.object(usb_export.platform, "system", return_value=system),
        mock.patch.object(usb_export, "get_crate_files", return_value=[]),
        mock.patch.object(usb_export, "copy_crates_to_usb") as copy_crates_to_usb,
    ):
        usb_export.main()
    return copy_crates_to_usb.call_args.kwargs


@pytest.mark.parametrize(
    "drive, system, dest",
    [
        pytest.param("E", "Windows", "E:\\", id="drive letter becomes drive root"),
        pytest.param("/Volumes/USB", "Darwin", "/Volumes/USB", id="drive folder kept"),
    ],
)
def test_cli_exports_to_the_drive(source_library: tuple[str, str], drive: str, system: str, dest: str):
    _, serato_dir = source_library
    assert run_cli("--drive", drive, "--source", serato_dir, system=system)["dest_drive_dir"] == dest


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(lambda drive, serato_dir: serato_dir, id="its _Serato_ folder"),
        pytest.param(lambda drive, serato_dir: drive, id="the drive it's on"),
    ],
)
def test_cli_exports_from_the_source_library(source_library: tuple[str, str], source: Callable[[str, str], str]):
    drive, serato_dir = source_library
    exported = run_cli("--drive", "/Volumes/USB", "--source", source(drive, serato_dir))
    assert exported["source_serato_dir"] == serato_dir


def test_cli_source_defaults_to_the_home_library(source_library: tuple[str, str], monkeypatch: pytest.MonkeyPatch):
    _, serato_dir = source_library
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DIR", serato_dir)
    assert run_cli("--drive", "/Volumes/USB")["source_serato_dir"] == serato_dir


def test_cli_source_folder_without_a_library_is_an_error(source_library: tuple[str, str]):
    drive, _ = source_library
    # cli_args drops stderr, so the message is read from the call that prints it
    with (
        mock.patch.object(argparse.ArgumentParser, "error", autospec=True, side_effect=SystemExit(2)) as error,
        pytest.raises(SystemExit),
    ):
        run_cli("--drive", "/Volumes/USB", "--source", os.path.join(drive, "Nope"))
    assert "no Serato library folder" in error.call_args.args[1]
