import os

import pytest

from serato_tools.crate import Crate, main

from test.helpers.bin_files import TEST_CRATE
from test.helpers.cli import cli_args
from test.helpers.files import copy_into, read_bytes, read_text


def test_parse_and_add_tracks():
    file = os.path.abspath(TEST_CRATE)
    crate = Crate(file)

    assert crate.to_bytes() == read_bytes(file)
    expected = read_text("test/data/crate.txt")
    assert crate.__str__() == expected, "parse"

    # absolute in this OS's form: C:\Users\... on Windows, /Users/... elsewhere
    full_track_path = os.path.join(
        os.path.splitdrive(os.getcwd())[0], os.sep, "Users", "bvand", "Music", "DJ Tracks", "Soulacybin - Zeu.mp3"
    )
    crate.add_tracks([full_track_path])
    expected += "\notrk (Track): [ ptrk (Track Path): Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3 ]"
    assert crate.__str__() == expected, "track added"

    same_track_paths = [
        full_track_path,
        "Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
        "/Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
    ]
    if os.name == "nt":
        # backslashes are only separators on Windows
        same_track_paths += [
            "C:\\Users\\bvand\\Music\\DJ Tracks\\Soulacybin - Zeu.mp3",
            "Users\\bvand\\Music\\DJ Tracks\\Soulacybin - Zeu.mp3",
            "C:/Users/bvand/Music/DJ Tracks/Soulacybin - Zeu.mp3",
        ]
    crate.add_tracks(same_track_paths)
    assert crate.__str__() == expected, "duplicate tracks not added"

    crate.add_tracks([os.path.join(os.path.dirname(full_track_path), "Thundercat - Them Changes.mp3")])
    expected += "\notrk (Track): [ ptrk (Track Path): Users/bvand/Music/DJ Tracks/Thundercat - Them Changes.mp3 ]"
    assert crate.__str__() == expected, "track added"


def test_saving_needs_the_crate_extension(tmp_dir: str):
    crate = Crate(os.path.join(tmp_dir, "Test.crate"))
    with pytest.raises(ValueError, match="should end with .crate"):
        crate.save(os.path.join(tmp_dir, "Test.txt"))


def run_cli(*args: str) -> str:
    """Runs `serato_crate` with `args`, and returns what it printed."""
    with cli_args("serato_crate", *args) as stdout:
        main()
    return stdout.getvalue()


def test_cli_lists_a_crates_tracks():
    crate = Crate(TEST_CRATE)
    assert run_cli(TEST_CRATE, "-l").splitlines() == crate.get_track_paths(include_drive=True), "absolute paths"
    assert run_cli(TEST_CRATE, "-f").splitlines() == [
        os.path.splitext(os.path.basename(path))[0] for path in crate.get_track_paths()
    ], "filenames without their extension"
    assert "Tripp St. - Enlighten" in run_cli(TEST_CRATE, "-f").splitlines()


def test_cli_prints_each_crate_in_a_folder(tmp_dir: str):
    for name in ["A.crate", "B.crate"]:
        copy_into(tmp_dir, TEST_CRATE, name)
    copy_into(tmp_dir, TEST_CRATE, "Not A Crate.txt")
    printed = run_cli(tmp_dir)
    assert printed.count(str(Crate(TEST_CRATE))) == 2


def test_cli_without_a_crate_lists_the_crates_and_exits(tmp_dir: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Crate, "DIR_PATH", tmp_dir)
    crate = copy_into(tmp_dir, TEST_CRATE)
    with cli_args("serato_crate") as stdout, pytest.raises(SystemExit):
        main()
    assert stdout.getvalue().splitlines() == ["must pass a file or dir, or --all!", f"files in {tmp_dir}:", crate]


def test_add_tracks_from_dir(tmp_dir: str):
    music = os.path.join(tmp_dir, "Music")
    os.mkdir(music)
    for name in ["A.mp3", "B.mp3"]:
        open(os.path.join(music, name), "wb").close()
    in_music = [Crate.get_relative_path(os.path.join(music, name)) for name in ["A.mp3", "B.mp3"]]
    elsewhere = Crate.get_relative_path(os.path.join(tmp_dir, "Elsewhere.mp3"))

    crate = Crate(os.path.join(tmp_dir, "Test.crate"))
    crate.add_tracks([elsewhere, os.path.join(music, "A.mp3")])
    crate.add_tracks_from_dir(music)
    assert sorted(crate.get_track_paths()) == sorted([elsewhere, *in_music]), "added, each once"

    crate.add_tracks_from_dir(music, replace=True)
    assert sorted(crate.get_track_paths()) == sorted(in_music), "replace drops the tracks not in the folder"
