import logging
import os
from dataclasses import dataclass
from unittest import mock

import pytest

from serato_tools import usb_export
from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate

from test.helpers.bin_files import LibraryFolders
from test.helpers.cli import cli_args
from test.helpers.files import copy_into, mock_files, read_bytes

# the folder on the drive the tests export tracks to
DRIVE_TRACKS = "Tracks"
# Serato's crate order file, trimmed from a real library's: UTF-16-BE with \n line endings, and a smart crate's
# subcrates separated with ≫≫
ORDER_FILE = "test/data/neworder.pref"


def read_pref_file(path: str) -> list[str]:
    """The order file's lines, decoded as Serato writes it, so a byte out of place fails to decode."""
    return read_bytes(path).decode("utf-16-be").split("\n")


@pytest.fixture
def crate_dirs(tmp_dir: str, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Empty Subcrates and SmartCrates folders, which get_crate_files looks in, in that order."""
    crate_dir = os.path.join(tmp_dir, usb_export.Crate.DIR)
    smart_crate_dir = os.path.join(tmp_dir, usb_export.SmartCrate.DIR)
    mock_files({crate_dir: [], smart_crate_dir: []})
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DIR", tmp_dir)
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
        pytest.param(
            ["house.crate", "test crate.crate", "house.scrate"],
            "*crate*",
            {"test crate.crate"},
            id="glob ignores the extension",
        ),
        pytest.param(["house.crate", "house.scrate"], "*.scrate", set(), id="glob can't match the extension"),
        pytest.param(["house.crate", "deep.crate"], "use$", {"house.crate"}, id="regex ignores the extension"),
        pytest.param(["Pop, Rock, etc..crate"], "*etc.", {"Pop, Rock, etc..crate"}, id="name ending in a dot"),
        pytest.param(
            ["Bass.crate", "Bass%%DnB.crate", "House.crate"],
            "Bass*",
            {"Bass.crate", "Bass%%DnB.crate"},
            id="subcrates match their parent's name",
        ),
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
class Export(LibraryFolders):
    """A local library and music folder, and a drive to export them to."""

    drive: str

    def __post_init__(self):
        super().__post_init__()
        mock_files({os.path.join(self.serato_dir, Crate.DIR): [], self.drive: []})

    def exported_database(self) -> DatabaseV2:
        return DatabaseV2(self.on_drive("_Serato_", DatabaseV2.FILENAME))

    def on_drive(self, *parts: str) -> str:
        return os.path.join(self.drive, *parts)


@pytest.fixture
def export(tmp_dir: str, monkeypatch: pytest.MonkeyPatch) -> Export:
    export = Export(
        serato_dir=os.path.join(tmp_dir, "_Serato_"),
        music_dir=os.path.join(tmp_dir, "Music"),
        drive=os.path.join(tmp_dir, "Drive"),
    )
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DIR", export.serato_dir)
    # built from the real library folder at import, so each is pointed at the test's too
    for name, path in [
        ("LOCAL_SERATO_STEMS_CRATE_PATH", Crate.SERATO_STEMS_CRATE_PATH),
    ]:
        monkeypatch.setattr(usb_export, name, os.path.join(export.serato_dir, path))
    monkeypatch.setattr(usb_export, "LOCAL_SERATO_DRIVE", os.path.splitdrive(tmp_dir)[0])
    return export


def test_copy_crates_to_usb(export: Export):
    a, b, not_exported = export.make_track("A.mp3", b"a"), export.make_track("B.mp3", b"b"), export.make_track("C.mp3")
    stems = export.make_track("B.serato-stems", b"stems")
    export.add_to_database(a, b, fields=[(DatabaseV2.Fields.PLAYED, True)])
    crates = [export.make_crate("House", [a, b]), export.make_crate("Deep", [b])]
    export.make_crate(os.path.join("Serato Stems", "Stems"), [b, not_exported])
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

    assert not os.path.exists(stale), "the drive's old library replaced"
    copied = {"A.mp3": a, "B.mp3": b, "B.serato-stems": stems}
    assert sorted(os.listdir(export.on_drive(DRIVE_TRACKS))) == sorted(copied), "only the exported crates' tracks"
    for name, src in copied.items():
        assert read_bytes(export.on_drive(DRIVE_TRACKS, name)) == read_bytes(src), f"{name} copied"


@pytest.fixture
def fixture_crates(export: Export) -> list[str]:
    """Crates named as in the order fixture: a regular one, a smart subcrate, and a regular subcrate."""
    a = export.make_track("A.mp3")
    copy_into(export.serato_dir, ORDER_FILE)
    return [
        export.make_crate("House & Techno", [a]),
        export.make_crate("Bass≫≫Riddim≫≫Wonky Monxxy Riddim", [a], SmartCrate),
        export.make_crate("Sets%%Riddim TODO%%Riddim MIX", [a]),
    ]


@pytest.mark.parametrize("root", [None, "Root"])
def test_copy_crates_to_usb_copies_the_crate_order(export: Export, fixture_crates: list[str], root: str | None):
    usb_export.copy_crates_to_usb(fixture_crates, export.drive, DRIVE_TRACKS, root_crate=root)

    prefix = f"{root}%%" if root else ""
    assert read_pref_file(export.on_drive("_Serato_", "neworder.pref")) == [
        "[begin record]",
        *([f"[crate]{root}"] if root else []),
        "[crate]Stems",
        f"[crate]{prefix}House & Techno",
        f"[crate]{prefix}Bass",
        f"[crate]{prefix}Bass%%Riddim",
        f"[crate]{prefix}Bass%%Riddim%%Wonky Monxxy Riddim",
        f"[crate]{prefix}Sets",
        f"[crate]{prefix}Sets%%Riddim TODO",
        f"[crate]{prefix}Sets%%Riddim TODO%%Riddim MIX",
        "[end record]",
        "",
    ], "only the exported crates and their parents, a smart crate named as the regular crate it's exported as"
    assert os.path.isfile(export.on_drive("_Serato_", Crate.DIR, f"{prefix}Bass%%Riddim%%Wonky Monxxy Riddim.crate")), (
        "the smart crate's file named as its line is"
    )


def test_copy_crates_to_usb_copies_only_changed_files(export: Export):
    a, b = export.make_track("A.mp3", b"a"), export.make_track("B.mp3", b"b")
    crates = [export.make_crate("House", [a, b])]
    usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)

    with mock.patch.object(usb_export.shutil, "copy2", wraps=usb_export.shutil.copy2) as copy2:
        usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)
        assert copy2.call_count == 0, "nothing changed, so nothing copied"

        export.make_track("B.mp3", b"b changed")
        usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)
    assert [os.path.basename(c.args[0]) for c in copy2.call_args_list] == ["B.mp3"]
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "B.mp3")) == b"b changed"


def test_copy_crates_to_usb_logs_a_missing_file(export: Export, caplog: pytest.LogCaptureFixture):
    a, gone = export.make_track("A.mp3", b"a"), os.path.join(export.music_dir, "Gone.mp3")
    crates = [export.make_crate("House", [a, gone])]

    with caplog.at_level(logging.ERROR):
        usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)

    assert f"does not exist - {gone}" in caplog.text
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "A.mp3")) == b"a", "the other track still copied"


def test_copy_crates_to_usb_logs_a_stems_file_gone_before_its_copied(export: Export, caplog: pytest.LogCaptureFixture):
    a = export.make_track("A.mp3", b"a")
    # found, then moved away by another program before it's copied
    gone = export.music_path("A.serato-stems")

    with (
        caplog.at_level(logging.ERROR),
        mock.patch.object(usb_export.Library, "find_stems_file", return_value=gone),
    ):
        usb_export.copy_crates_to_usb([export.make_crate("House", [a])], export.drive, DRIVE_TRACKS)

    assert f"does not exist - {gone}" in caplog.text
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "A.mp3")) == b"a", "the track still copied"


def test_copy_crates_to_usb_raises_when_every_track_is_missing(export: Export):
    crates = [export.make_crate("House", [os.path.join(export.music_dir, "Gone.mp3")])]
    with pytest.raises(FileNotFoundError, match="none of the tracks were found"):
        usb_export.copy_crates_to_usb(crates, export.drive, DRIVE_TRACKS)


def test_copy_crates_to_usb_needs_the_drive_to_exist(export: Export):
    with pytest.raises(FileNotFoundError):
        usb_export.copy_crates_to_usb([], os.path.join(export.drive, "Missing"), DRIVE_TRACKS)


@pytest.mark.parametrize(
    "bad_file, error",
    [
        pytest.param(os.path.join(Crate.DIR, "Notes.txt"), "not a crate file", id="not a crate"),
        pytest.param(os.path.join(Crate.DIR, "Broken.crate"), "file ends partway", id="unreadable crate"),
    ],
)
def test_copy_crates_to_usb_writes_nothing_to_the_drive_for_a_crate_it_cant_read(
    export: Export, bad_file: str, error: str
):
    crates = [export.make_crate("House", [export.make_track("A.mp3", b"a")])]
    (bad,) = mock_files({export.serato_dir: [bad_file]})
    with open(bad, "wb") as f:
        f.write(b"not a crate")
    mock_files({export.on_drive("_Serato_"): ["Old.txt"]})

    with pytest.raises(ValueError, match=error):
        usb_export.copy_crates_to_usb([*crates, bad], export.drive, DRIVE_TRACKS)

    assert os.listdir(export.on_drive("_Serato_")) == ["Old.txt"], "the drive's library left as it was"


def test_copy_crates_to_usb_copies_each_tracks_own_stems(export: Export):
    # named after the track with or without its extension; the old prefix match took "A Extended"'s for "A.mp3" too
    tracks = [export.make_track(name) for name in ["A.mp3", "A Extended.mp3", "C.mp3"]]
    stems = {
        name: export.make_track(name, name.encode())
        for name in ["A.serato-stems", "A Extended.serato-stems", "C.mp3.serato-stems"]
    }

    usb_export.copy_crates_to_usb([export.make_crate("House", tracks)], export.drive, DRIVE_TRACKS)

    for name, src in stems.items():
        assert read_bytes(export.on_drive(DRIVE_TRACKS, name)) == read_bytes(src), f"{name} copied"


def test_copy_crates_to_usb_puts_tracks_sharing_a_filename_in_subfolders(export: Export):
    # FAT32 and exFAT drives ignore case, so "a.MP3" would overwrite "A.mp3"
    tracks = {
        f"{DRIVE_TRACKS}/A.mp3": export.make_track("M1/A.mp3", b"m1"),
        f"{DRIVE_TRACKS}/M2/A.mp3": export.make_track("M2/A.mp3", b"m2"),
        f"{DRIVE_TRACKS}/M3/a.MP3": export.make_track("M3/a.MP3", b"m3"),
        f"{DRIVE_TRACKS}/M2 (2)/A.mp3": export.make_track("Other/M2/A.mp3", b"other m2"),
    }
    export.make_track("M2/A.serato-stems", b"stems")
    # the database lists them in another order than the crate
    for i, track in reversed(list(enumerate(tracks.values()))):
        export.add_to_database(track, fields=[(DatabaseV2.Fields.GENRE, str(i))])

    usb_export.copy_crates_to_usb([export.make_crate("House", list(tracks.values()))], export.drive, DRIVE_TRACKS)

    for on_drive, src in tracks.items():
        assert read_bytes(export.on_drive(on_drive)) == read_bytes(src), f"{on_drive} copied"
    assert read_bytes(export.on_drive(DRIVE_TRACKS, "M2", "A.serato-stems")) == b"stems", "stems beside their track"
    exported_crate = Crate(export.on_drive("_Serato_", Crate.DIR, "House.crate"))
    assert exported_crate.get_track_paths() == list(tracks), "the crate pointed at each"
    db_genres = {t.relpath: t.get_value(DatabaseV2.Fields.GENRE) for t in export.exported_database().get_tracks()}
    assert db_genres == {path: str(i) for i, path in enumerate(tracks)}, "each with its own database entry"


def test_copy_crates_to_usb_keeps_the_date_added(export: Export):
    a = export.make_track("A.mp3")
    added = [(DatabaseV2.Fields.DATE_ADDED_U, 1700000000), (DatabaseV2.Fields.DATE_ADDED_T, "1700000000")]
    export.add_to_database(a, fields=added)

    usb_export.copy_crates_to_usb([export.make_crate("House", [a])], export.drive, DRIVE_TRACKS)

    (track,) = export.exported_database().get_tracks()
    assert [track.get_value(field) for field, _ in added] == [value for _, value in added], (
        "the date the track was added to the library, which Serato's own sync resets to the export's"
    )


def test_copy_crates_to_usb_writes_a_smart_crate_as_a_regular_crate(export: Export):
    a = export.make_track("A.mp3")
    smart_crate = export.make_crate("Parent≫≫Dubstep", [a], SmartCrate)

    usb_export.copy_crates_to_usb([smart_crate], export.drive, DRIVE_TRACKS)

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
        usb_export.copy_crates_to_usb([export.make_crate("House", [a])], export.drive, DRIVE_TRACKS)


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
