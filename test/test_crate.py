import os

import pytest

from serato_tools.crate import Crate

from test.helpers.bin_files import TEST_CRATE
from test.helpers.files import read_bytes, read_text


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
