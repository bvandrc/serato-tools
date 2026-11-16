import os

import pytest

from serato_tools.crate import Crate, main

from test.helpers.bin_files import MP3_FILENAMES, TEST_CRATE, TRACKS_DIR
from test.helpers.cli import cli_args
from test.helpers.files import copy_into, mock_files, read_bytes, read_text

# the test crate parsed, as its __str__ prints it
TEST_CRATE_TXT_FILE = "test/data/crate.txt"


def test_parse():
    crate = Crate(TEST_CRATE)
    assert crate.to_bytes() == read_bytes(TEST_CRATE), "round-trips byte-exact"
    assert crate.__str__() == read_text(TEST_CRATE_TXT_FILE)


def test_add_tracks():
    crate = Crate(os.path.abspath(TEST_CRATE))
    expected = read_text(TEST_CRATE_TXT_FILE)

    # as Serato stores a track's path
    RELPATH = f"{TRACKS_DIR}/{MP3_FILENAMES.SOULACYBIN_ZEU}"
    # absolute in this OS's form: C:\Users\... on Windows, /Users/... elsewhere
    crate.add_tracks([os.path.abspath("/" + RELPATH)])
    expected += f"\notrk (Track): [ ptrk (Track Path): {RELPATH} ]"
    assert crate.__str__() == expected, "track added"

    same_track_paths = [os.path.abspath("/" + RELPATH), RELPATH, "/" + RELPATH]
    if os.name == "nt":
        # backslashes are only separators on Windows
        same_track_paths += ["C:\\" + RELPATH.replace("/", "\\"), RELPATH.replace("/", "\\"), "C:/" + RELPATH]
    crate.add_tracks(same_track_paths)
    assert crate.__str__() == expected, "duplicate tracks not added"

    OTHER_RELPATH = f"{TRACKS_DIR}/{MP3_FILENAMES.THUNDERCAT_THEMCHANGES}"
    crate.add_tracks([os.path.abspath("/" + OTHER_RELPATH)])
    expected += f"\notrk (Track): [ ptrk (Track Path): {OTHER_RELPATH} ]"
    assert crate.__str__() == expected, "track added"


def test_add_tracks_skips_a_track_already_there_in_another_case(new_crate: Crate):
    new_crate.add_tracks(["/music/A.mp3"])
    new_crate.add_tracks(["/MUSIC/a.MP3", "/music/B.mp3", "/music/b.mp3"])
    assert new_crate.get_track_paths() == ["music/A.mp3", "music/B.mp3"], "each as first added"


def test_add_tracks_from_dir(new_crate: Crate, tmp_dir: str):
    music = os.path.join(tmp_dir, "Music")
    # a hidden file, which isn't a track any more than the subfolder is
    a, b, _ = mock_files({music: ["A.mp3", "B.mp3", ".DS_Store", {"Subfolder": []}]})
    in_music = [Crate.get_relative_path(path) for path in [a, b]]
    elsewhere = Crate.get_relative_path(os.path.join(tmp_dir, "Elsewhere.mp3"))

    new_crate.add_tracks([elsewhere, a])
    new_crate.add_tracks_from_dir(music)
    assert sorted(new_crate.get_track_paths()) == sorted([elsewhere, *in_music]), "the folder's files added, each once"

    new_crate.add_tracks_from_dir(music, replace=True)
    assert sorted(new_crate.get_track_paths()) == sorted(in_music), "replace drops the tracks not in the folder"


def test_add_tracks_from_dir_replacing_keeps_a_track_there_in_another_case(new_crate: Crate, tmp_dir: str):
    music = os.path.join(tmp_dir, "Music")
    mock_files({music: ["a.mp3"]})
    in_crate = os.path.join(music, "A.MP3")
    new_crate.add_tracks([in_crate])

    new_crate.add_tracks_from_dir(music, replace=True)

    assert new_crate.get_track_paths() == [Crate.get_relative_path(in_crate)], "kept, not removed and added again"


def test_saving_needs_the_crate_extension(new_crate: Crate, tmp_dir: str):
    with pytest.raises(ValueError, match="should end with .crate"):
        new_crate.save(os.path.join(tmp_dir, "Test.txt"))


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
    assert os.path.splitext(MP3_FILENAMES.TRIPPST_ENLIGHTEN)[0] in run_cli(TEST_CRATE, "-f").splitlines()


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
