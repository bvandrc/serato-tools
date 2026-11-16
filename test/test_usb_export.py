# pylint: disable=protected-access
import logging
import os
from dataclasses import dataclass
from unittest import mock

import pytest

from serato_tools import usb_export
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils.bin_file_base import SeratoBinFile

from test.helpers.bin_files import TEST_DATABASE
from test.helpers.cli import cli_args
from test.helpers.files import copy_into, mock_files, read_bytes

# the folder on the drive the tests export tracks to
DRIVE_TRACKS = "Tracks"


@pytest.fixture
def crate_dirs(tmp_dir: str, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Empty Subcrates and SmartCrates folders, which get_crate_files looks in, in that order."""
    crate_dir = os.path.join(tmp_dir, usb_export.Crate.DIR)
    smart_crate_dir = os.path.join(tmp_dir, usb_export.SmartCrate.DIR)
    mock_files({crate_dir: [], smart_crate_dir: []})
    monkeypatch.setattr(usb_export.Crate, "DIR_PATH", crate_dir)
    monkeypatch.setattr(usb_export.SmartCrate, "DIR_PATH", smart_crate_dir)
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


@dataclass
class Export:
    """A local library and music folder, and a drive to export them to."""

    serato_dir: str
    music_dir: str
    drive: str

    def music(self, name: str, content: bytes = b"audio") -> str:
        """A file in the music folder, which `name` may put in a subfolder, with `content`."""
        path = os.path.join(self.music_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def crate(self, name: str, tracks: list[str], crate_class: type[Crate] | type[SmartCrate] = Crate) -> str:
        """A crate, or a smart crate, of `tracks` in the local library, named as Serato names its file."""
        path = os.path.join(self.serato_dir, crate_class.DIR, name + crate_class.EXTENSION)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        crate = crate_class(path)
        crate.add_tracks(tracks)
        crate.save()
        return crate.filepath

    def add_to_database(self, *tracks: str, genre: str | None = None):
        """Adds `tracks` to the local database, in order, each marked played, and given `genre` if it's set."""
        db = DatabaseV2(os.path.join(self.serato_dir, DatabaseV2.FILENAME))
        for track in tracks:
            fields: SeratoBinFile.EntryList = [
                (DatabaseV2.Fields.FILE_PATH, DatabaseV2.get_relative_path(track)),
                (DatabaseV2.Fields.PLAYED, True),
            ]
            if genre is not None:
                fields.append((DatabaseV2.Fields.GENRE, genre))
            db._entries.append((DatabaseV2.Fields.TRACK, fields))
        db.save()

    def exported_database(self) -> DatabaseV2:
        return DatabaseV2(self.on_drive("_Serato_", DatabaseV2.FILENAME))

    def on_drive(self, *parts: str) -> str:
        return os.path.join(self.drive, *parts)


@pytest.fixture
def export(tmp_dir: str, monkeypatch: pytest.MonkeyPatch) -> Export:
    serato_dir, music_dir, drive = (os.path.join(tmp_dir, name) for name in ["_Serato_", "Music", "Drive"])
    mock_files({os.path.join(serato_dir, Crate.DIR): [], music_dir: [], drive: []})
    copy_into(serato_dir, TEST_DATABASE, DatabaseV2.FILENAME)
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DIR", serato_dir)
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DRIVE", os.path.splitdrive(tmp_dir)[0])
    return Export(serato_dir, music_dir, drive)


def test_copy_crates_to_usb(export: Export):
    a, b, not_exported = export.music("A.mp3", b"a"), export.music("B.mp3", b"b"), export.music("C.mp3")
    stems = export.music("B.serato-stems", b"stems")
    export.add_to_database(a, b)
    crates = [export.crate("House", [a, b]), export.crate("Deep", [b])]
    export.crate(os.path.join("Serato Stems", "Stems"), [b, not_exported])
    with open(os.path.join(export.serato_dir, "neworder.pref"), "w", encoding="utf-8") as f:
        f.write("[begin record]\n[crate]House\n[crate]Deep\n[crate]Stems\n[end record]\n")
    (stale,) = mock_files({export.on_drive("_Serato_"): ["Stale.txt"]})

    usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS, root_crate="Root")

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
    for src, name in [(a, "A.mp3"), (b, "B.mp3"), (stems, "B.serato-stems")]:
        assert read_bytes(export.on_drive(DRIVE_TRACKS, name)) == read_bytes(src), f"{name} copied"


def test_copy_crates_to_usb_copies_only_changed_files(export: Export):
    a, b = export.music("A.mp3", b"a"), export.music("B.mp3", b"b")
    crates = [export.crate("House", [a, b])]
    usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)

    with mock.patch.object(usb_export.shutil, "copy2", wraps=usb_export.shutil.copy2) as copy2:
        usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)
        assert copy2.call_count == 0, "nothing changed, so nothing copied"

        export.music("B.mp3", b"b changed")
        usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)
    assert [os.path.basename(c.args[0]) for c in copy2.call_args_list] == ["B.mp3"]
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "B.mp3")) == b"b changed"


def test_copy_crates_to_usb_warns_of_a_missing_file(export: Export, caplog: pytest.LogCaptureFixture):
    a, gone = export.music("A.mp3", b"a"), os.path.join(export.music_dir, "Gone.mp3")
    crates = [export.crate("House", [a, gone])]

    with caplog.at_level(logging.WARNING):
        usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)

    assert f"does not exist - {gone}" in caplog.text
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "A.mp3")) == b"a", "the other track still copied"


def test_copy_crates_to_usb_needs_the_drive_to_exist(export: Export):
    with pytest.raises(FileNotFoundError):
        usb_export.copy_crates_to_usb([], os.path.join(export.drive, "Missing"), DRIVE_TRACKS)


def test_copy_crates_to_usb_copies_each_tracks_own_stems(export: Export):
    # named after the track with or without its extension; the old prefix match took "A Extended"'s for "A.mp3" too
    tracks = [export.music(name) for name in ["A.mp3", "A Extended.mp3", "C.mp3"]]
    stems = {
        name: export.music(name, name.encode())
        for name in ["A.serato-stems", "A Extended.serato-stems", "C.mp3.serato-stems"]
    }

    usb_export.copy_crates_to_usb([export.crate("House", tracks)], export.drive, DRIVE_TRACKS)

    for name, src in stems.items():
        assert read_bytes(export.on_drive(DRIVE_TRACKS, name)) == read_bytes(src), f"{name} copied"


def test_copy_crates_to_usb_keeps_the_database_entry_of_the_track_it_copies(export: Export):
    # two tracks with one filename: the crate lists M1's first, the database M2's
    m1, m2 = export.music("M1/A.mp3", b"m1"), export.music("M2/A.mp3", b"m2")
    export.add_to_database(m2, genre="from M2")
    export.add_to_database(m1, genre="from M1")

    usb_export.copy_crates_to_usb([export.crate("House", [m1, m2])], export.drive, DRIVE_TRACKS)

    assert read_bytes(export.on_drive(DRIVE_TRACKS, "A.mp3")) == b"m1", "the first in the crates copied"
    tracks = export.exported_database().get_tracks()
    assert [t.get_value(DatabaseV2.Fields.GENRE) for t in tracks] == ["from M1"], "with its own database entry"


def test_copy_crates_to_usb_writes_a_smart_crate_as_a_regular_crate(export: Export):
    a = export.music("A.mp3")
    smart_crate = export.crate("Parent≫≫Dubstep", [a], SmartCrate)

    usb_export.copy_crates_to_usb([smart_crate], export.drive, DRIVE_TRACKS)

    # a smart crate's subcrate separator in its filename is ≫≫, a regular crate's %%
    exported = Crate(export.on_drive("_Serato_", Crate.DIR, "Parent%%Dubstep.crate"))
    assert exported._version == Crate.DEFAULT_ENTRIES[0][1], "a regular crate, which Crate opens"
    assert exported.get_track_paths() == [f"{DRIVE_TRACKS}/A.mp3"]


def test_copy_crates_to_usb_raises_for_a_track_with_two_stems_files(export: Export):
    # stems files named both with the track's extension and without it, so which to copy isn't known
    a = export.music("A.mp3")
    export.music("A.serato-stems")
    export.music("A.mp3.serato-stems")
    with pytest.raises(ValueError, match="more than 1 stems file"):
        usb_export.copy_crates_to_usb([export.crate("House", [a])], export.drive, DRIVE_TRACKS)


def test_copy_crates_to_usb_skips_a_folder_in_the_crate_list(export: Export):
    house = export.crate("House", [export.music("A.mp3")])
    folder = os.path.join(export.serato_dir, Crate.DIR, "Folder")
    mock_files({folder: []})

    usb_export.copy_crates_to_usb([folder, house], export.drive, DRIVE_TRACKS)

    assert os.listdir(export.on_drive("_Serato_", Crate.DIR)) == ["House.crate"], "the crates after it still exported"
    assert os.listdir(export.on_drive(DRIVE_TRACKS)) == ["A.mp3"]


def test_copy_crates_to_usb_raises_for_a_file_that_isnt_a_crate(export: Export):
    notes = os.path.join(export.serato_dir, Crate.DIR, "notes.txt")
    with open(notes, "w", encoding="utf-8") as f:
        f.write("not a crate")
    with pytest.raises(ValueError, match="not a crate file"):
        usb_export.copy_crates_to_usb([notes], export.drive, DRIVE_TRACKS)


def test_copy_crates_to_usb_logs_the_database_and_stems_crate_it_writes(
    export: Export, caplog: pytest.LogCaptureFixture
):
    house = export.crate("House", [export.music("A.mp3")])
    export.crate(os.path.join("Serato Stems", "Stems"), [])

    with caplog.at_level(logging.INFO, "serato-tools"):
        usb_export.copy_crates_to_usb([house], export.drive, DRIVE_TRACKS)

    assert f"created database file {export.on_drive('_Serato_', DatabaseV2.FILENAME)}" in caplog.messages
    assert f"copied crate {export.on_drive('_Serato_', Crate.SERATO_STEMS_CRATE_PATH)}" in caplog.messages


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
