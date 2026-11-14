import copy
import json
import os
from unittest import mock

import pytest

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate

# bin_file_base raises the installed package's DataTypeError, so catch that one
from serato_tools.utils.bin_file_base import DataTypeError, SeratoBinFile

from test.helpers.bin_files import TEST_CRATE, TEST_DATABASE
from test.helpers.files import copy_into, read_bytes, read_text

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows drive letters and backslash separators")
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX paths")


@pytest.fixture
def db_file(tmp_dir: str) -> str:
    """A copy of the test database, as its own file name."""
    return copy_into(tmp_dir, TEST_DATABASE, DatabaseV2.FILENAME)


# paths


@pytest.mark.parametrize(
    "path, expected",
    [
        ("Music/DJ Tracks/Tripp St. - Enlighten.mp3", "Music/DJ Tracks/Tripp St. - Enlighten.mp3"),
        pytest.param(
            "C:\\Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3",
            "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
            marks=WINDOWS_ONLY,
        ),
        pytest.param(
            "Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3",
            "Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
            marks=WINDOWS_ONLY,
        ),
        pytest.param(
            "C:/Music/DJ Tracks/Tripp St. - Enlighten.mp3",
            "Music/DJ Tracks/Tripp St. - Enlighten.mp3",
            marks=WINDOWS_ONLY,
        ),
        pytest.param(
            "/Users/Username/Music/DJ Tracks/Tripp St. - Enlighten.mp3",
            "Users/Username/Music/DJ Tracks/Tripp St. - Enlighten.mp3",
            marks=POSIX_ONLY,
        ),
    ],
)
def test_relative_path(path: str, expected: str):
    assert SeratoBinFile.get_relative_path(path) == expected


@WINDOWS_ONLY
def test_full_path_keeps_given_drive():
    path = "D:/Music/DJ Tracks/Tripp St. - Enlighten.mp3"
    assert SeratoBinFile.get_full_path(path) == os.path.normpath(path)


@POSIX_ONLY
def test_full_path_keeps_absolute_posix_path():
    path = "/Volumes/USB/Music/DJ Tracks/Tripp St. - Enlighten.mp3"
    assert SeratoBinFile.get_full_path(path) == path


def test_full_path_without_drive_is_absolute():
    # Serato stores track paths with no drive or leading separator
    full_path = SeratoBinFile.get_full_path("Music/DJ Tracks/Tripp St. - Enlighten.mp3")
    assert os.path.isabs(full_path)
    assert full_path.endswith(os.path.normpath("/Music/DJ Tracks/Tripp St. - Enlighten.mp3"))


# loading a file: from its bytes, from JSON, or, for a file that doesn't exist yet, from its class's defaults


@pytest.mark.parametrize(
    "cut_at",
    [pytest.param(3, id="partway through a header"), pytest.param(-1, id="partway through an entry")],
)
def test_a_file_cut_off_raises(tmp_dir: str, cut_at: int):
    path = os.path.join(tmp_dir, "Cut.crate")
    with open(path, "wb") as f:
        f.write(read_bytes(TEST_DATABASE)[:cut_at])
    with pytest.raises(ValueError, match="file ends partway through"):
        DatabaseV2(path)


# DatabaseV2 can't be created new. Crate and SmartCrate share CrateBase.DEFAULT_VIEW_ENTRIES' sublists
@pytest.mark.parametrize("cls", (Crate, SmartCrate), ids=lambda cls: cls.__name__)
def test_new_file_shares_no_entries_with_its_class_default(tmp_dir: str, cls: type[Crate] | type[SmartCrate]):
    defaults = {c: copy.deepcopy(c.DEFAULT_ENTRIES) for c in (Crate, SmartCrate)}
    a = cls(os.path.join(tmp_dir, "A" + cls.EXTENSION))
    a.add_tracks(["/music/track1.mp3"])
    b = cls(os.path.join(tmp_dir, "B" + cls.EXTENSION))

    for i, (field, value) in enumerate(a.entries[: len(defaults[cls])]):
        if isinstance(value, list):
            assert value is not cls.DEFAULT_ENTRIES[i][1], f"{field} sublist shared with class default"
            assert value is not b.entries[i][1], f"{field} sublist shared between instances"
            value.append((SeratoBinFile.Fields.COLUMN_NAME, "mutated"))

    for c, default in defaults.items():
        assert c.DEFAULT_ENTRIES == default, f"{c.__name__}'s default mutated"
    assert b.entries == defaults[cls], "other instance must not inherit tracks or nested edits"


def test_json_round_trip():
    db_from_bin = DatabaseV2(TEST_DATABASE)
    assert db_from_bin.to_json_object() == json.loads(read_text("test/data/database_v2_json.json"))

    db_from_json = DatabaseV2(os.path.abspath("test/data/database_v2_json.json"))
    assert db_from_json.__str__() == db_from_bin.__str__(), "loaded from a JSON file"

    db_from_json.entries = []
    db_from_json.from_json_object(db_from_bin.to_json_object())
    assert db_from_json.__str__() == db_from_bin.__str__(), "from_json_object"


def test_mistyped_json_value_is_refused(tmp_dir: str):
    db = DatabaseV2(TEST_DATABASE)
    original_entries = copy.deepcopy(db.entries)
    json_obj = db.to_json_object()
    track = json_obj[1]["value"]
    assert isinstance(track, list)
    uadd = next(e for e in track if e["field"] == DatabaseV2.Fields.DATE_ADDED_U)
    uadd["value"], uadd["type"] = "not an int", "str"

    json_file = os.path.join(tmp_dir, "db.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_obj, f)
    with pytest.raises(DataTypeError):  # on load
        DatabaseV2(json_file)

    with pytest.raises(DataTypeError):  # into an existing db
        db.from_json_object(json_obj)
    assert db.entries == original_entries, "existing entries left as they were"


# changing a file's tracks, through DatabaseV2, whose tracks have the most fields


def test_modify():
    db = DatabaseV2(TEST_DATABASE)

    original_entries = copy.deepcopy(db.entries)
    original_str = db.__str__()
    assert not db.modify([]), "reports no change"
    assert db.entries == original_entries, "was not modified"
    assert db.__str__() == original_str, "was not modified"

    new_time = int(1735748100)
    changed = db.modify(
        [
            {"field": DatabaseV2.Fields.DATE_ADDED_U, "func": lambda *args: new_time},
            {"field": DatabaseV2.Fields.DATE_ADDED_T, "func": lambda *args: str(new_time)},
            {"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "NEW_GROUPING"},
        ]
    )
    assert changed, "reports change"
    assert db.__str__() == read_text("test/data/database_v2_test_modified_output.txt", "utf-16")
    assert db.to_bytes() == read_bytes("test/data/database_v2_test_modified_output.bin")

    db.modify(
        [
            {
                "field": DatabaseV2.Fields.GENRE,
                "func": lambda *args: "NEW_GENRE",
                "files": [
                    "Users/bvand/Music/DJ Tracks/Zeds Dead - In The Beginning.mp3",
                    os.path.join(os.sep, "Users", "bvand", "Music", "DJ Tracks", "Tripp St. - Enlighten.mp3"),
                ]
                # backslashes and drive letters only mean something on Windows
                + (
                    [
                        "Users\\bvand\\Music\\DJ Tracks\\Zeds Dead - In The Beginning.mp3",
                        "C:/Users/bvand/Music/DJ Tracks/Tripp St. - Enlighten.mp3",
                    ]
                    if os.name == "nt"
                    else []
                ),
            },
        ]
    )
    assert db.__str__() == read_text("test/data/database_v2_test_modified_output_2.txt"), "given files"
    assert db.to_bytes() == read_bytes("test/data/database_v2_test_modified_output_2.bin"), "given files"


def test_modify_with_two_rules_for_a_field_raises():
    db = DatabaseV2(TEST_DATABASE)
    rule: SeratoBinFile.ModifyRule = {"field": DatabaseV2.Fields.GENRE, "func": lambda *args: None}
    with pytest.raises(ValueError, match="1 rule per field"):
        db.modify([rule, rule])


def test_modify_empty_value_removes_field(db_file: str):
    # as Serato does when a tag is cleared
    db = DatabaseV2(db_file)
    target = "Users/bvand/Music/DJ Tracks/SiR - D'Evils.mp3"
    other = "Users/bvand/Music/DJ Tracks/Slaycub - Visceral Planet.mp3"
    clear_grouping: list[DatabaseV2.ModifyRule] = [
        {"field": DatabaseV2.Fields.GROUPING, "files": [target], "func": lambda *args: ""}
    ]

    def grouping(database: DatabaseV2, relpath: str):
        track = next(t for t in database.get_tracks() if t.relpath == relpath)
        return track.get_value(DatabaseV2.Fields.GROUPING) if DatabaseV2.Fields.GROUPING in track.fields else None

    assert db.modify(clear_grouping), "reports removal"
    assert grouping(db, target) is None, "removed rather than set empty"
    assert grouping(db, other) == "UNTAGGED", "other tracks left as they were"
    assert not db.modify(clear_grouping), "reports no change when already gone"
    db.save()
    assert grouping(DatabaseV2(db_file), target) is None, "removed in the saved file"

    with pytest.raises(ValueError):  # a track can't be without its path
        db.modify([{"field": DatabaseV2.Fields.FILE_PATH, "files": [target], "func": lambda *args: ""}])


def test_modify_tracks_given_files():
    db = DatabaseV2(TEST_DATABASE)
    target = "Users/bvand/Music/DJ Tracks/Tripp St. - Enlighten.mp3"

    seen: list[str] = []

    def func(track: DatabaseV2.Track):
        seen.append(track.relpath)
        return track

    db.modify_tracks(func, files=[target])
    assert seen == [DatabaseV2.get_relative_path(target)], "only the given track is passed to func"


def test_remove_tracks():
    db = DatabaseV2(TEST_DATABASE)
    paths = db.get_track_paths()
    assert len(paths) > 2

    assert db.remove_tracks(paths[:2]), "reports removal"
    assert db.get_track_paths() == paths[2:], "removes exactly the given tracks, keeping order"
    assert not db.remove_tracks(paths[:2]), "reports no change when already gone"


def test_remove_duplicates():
    db = DatabaseV2("test/data/database_v2_duplicates.bin")
    assert db.__str__() == read_text("test/data/database_v2_duplicates_output.txt"), "original"
    assert db.remove_duplicates(), "reports removal"
    assert db.__str__() == read_text("test/data/database_v2_duplicates_output_deduped.txt"), "deduped"
    assert not db.remove_duplicates(), "nothing left to remove"


# a track's fields


def test_duplicate_field_raises():
    # a repeated field would be silently collapsed/duplicated on round-trip, corrupting the file
    with pytest.raises(ValueError):
        SeratoBinFile.Track(
            [
                (SeratoBinFile.Fields.FILE_PATH.value, "a.mp3"),
                (SeratoBinFile.Fields.GENRE.value, "House"),
                (SeratoBinFile.Fields.GENRE.value, "Techno"),
            ],
            path_key=SeratoBinFile.Fields.FILE_PATH.value,
        )


def test_remove_field():
    path, genre = SeratoBinFile.Fields.FILE_PATH.value, SeratoBinFile.Fields.GENRE.value
    track = SeratoBinFile.Track([(path, "a.mp3"), (genre, "House")], path_key=path)
    only_path = [(path, "a.mp3")]

    assert track.remove_field(genre), "reports removal"
    assert track.to_entries() == only_path, "removed from the entries written back"
    assert not track.remove_field(genre), "reports no change when already gone"

    # as Serato does when a tag is cleared
    track.set_value(genre, "House")
    track.set_value(genre, "")
    assert track.to_entries() == only_path, "set_value empty removes it, rather than setting it empty"
    track.set_value(genre, "")
    assert track.to_entries() == only_path, "set_value empty doesn't add it when already gone"

    # a track can't be without its path
    with pytest.raises(ValueError):
        track.remove_field(path)
    with pytest.raises(ValueError):
        track.set_value(path, "")
    assert track.to_entries() == only_path, "path kept"


# has_changed and save, mostly through Crate, the smallest of the bin file classes


@pytest.fixture
def crate_file(tmp_dir: str) -> str:
    """A copy of the test crate, as Test.crate."""
    return copy_into(tmp_dir, TEST_CRATE, "Test.crate")


def test_save_writes_its_own_file_only_when_changed(tmp_dir: str, crate_file: str, bin_file_writes: list[str]):
    crate = Crate(crate_file)
    assert not crate.has_changed, "as loaded"
    assert not crate.save(), "unchanged"
    assert bin_file_writes == [], "unchanged, so not written"
    assert crate.save(force=True), "forced"
    assert bin_file_writes == ["Test.crate"], "forced, so written"
    copy_file = os.path.join(tmp_dir, "Copy.crate")
    assert crate.save(copy_file), "saving elsewhere always writes"
    assert read_bytes(copy_file) == read_bytes(crate_file), "as it was"

    crate.add_tracks(["/music/track1.mp3"])
    assert crate.has_changed, "track added"
    crate.save(copy_file)
    assert crate.has_changed, "saving a copy elsewhere leaves its own file unsaved"
    with mock.patch.object(Crate, "to_bytes", autospec=True, side_effect=Crate.to_bytes) as to_bytes:
        assert crate.save()
    assert to_bytes.call_count == 1, "serialized once, to check and to write"
    assert Crate(crate_file).get_track_paths() == crate.get_track_paths(), "written"
    assert not crate.has_changed, "saved"
    assert not crate.save(), "not written again"

    sorting = crate.entries[1][1]
    assert isinstance(sorting, list)
    sorting.append((Crate.Fields.COLUMN_NAME, "edited in place"))
    assert crate.has_changed, "nested entry edited in place"
    sorting.pop()
    assert not crate.has_changed, "edited back"


@pytest.mark.skipif(os.name == "nt", reason="creating a symlink needs extra privileges on Windows")
def test_saving_through_a_symlink_is_saving_its_own_file(tmp_dir: str, crate_file: str):
    link = os.path.join(tmp_dir, "Link.crate")
    os.symlink(crate_file, link)
    crate = Crate(crate_file)
    crate.add_tracks(["/music/track1.mp3"])
    crate.save(link)
    assert not crate.has_changed


def test_new_file_has_changed_until_saved(tmp_dir: str):
    file = os.path.join(tmp_dir, "New.crate")
    crate = Crate(file)
    assert crate.has_changed, "saving creates the file"
    crate.add_tracks(["/music/track1.mp3"])
    crate.save()
    assert not crate.has_changed
    assert Crate(file).get_track_paths() == crate.get_track_paths(), "created with its tracks"


def test_file_loaded_from_json_hasnt_changed(tmp_dir: str, crate_file: str):
    json_file = os.path.join(tmp_dir, "Test.json")
    Crate(crate_file).write_json(json_file)
    crate = Crate(json_file)
    assert not crate.has_changed
    crate.add_tracks(["/music/track1.mp3"])
    assert crate.has_changed


def test_save_leaves_file_as_it_was_on_error(db_file: str):
    orig = read_bytes(TEST_DATABASE)

    db = DatabaseV2(db_file)
    db.entries.append((DatabaseV2.Fields.TRACK, "not a list"))
    with pytest.raises(DataTypeError):
        db.save()
    assert read_bytes(db_file) == orig, "serialization error"

    class SavesTooEarly(DatabaseV2):
        def __init__(self, file: str):
            self.filepath = file
            self.save()
            super().__init__(file)

    with pytest.raises(RuntimeError):
        SavesTooEarly(db_file)
    assert read_bytes(db_file) == orig, "save before parse finished"


def test_methods_that_save_skip_it_when_unchanged(db_file: str, bin_file_writes: list[str]):
    db = DatabaseV2(db_file)

    no_match: list[DatabaseV2.ModifyRule] = [
        {"field": DatabaseV2.Fields.GROUPING, "files": ["Not In Library.mp3"], "func": lambda *args: "X"}
    ]
    db.modify_and_save(no_match)
    assert bin_file_writes == [], "modify_and_save unchanged, so not saved"
    if os.name == "nt":  # paths are only case-insensitive on Windows
        db.modify_and_save(no_match, db_file.upper())
        assert bin_file_writes == [], "same file in other case, unchanged, so not saved"

    # the fixture's tracks don't exist here, so each one prompts; "s" skips it
    with mock.patch("builtins.input", return_value="s"), mock.patch("builtins.print"):
        db.find_missing()
    assert bin_file_writes == [], "find_missing relocated nothing, so not saved"

    db.modify_and_save(no_match, os.path.join(os.path.dirname(db_file), "copy"))
    assert bin_file_writes == ["copy"], "saved anyway when given another file"

    db.modify_and_save([{"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "X"}])
    assert bin_file_writes == ["copy", DatabaseV2.FILENAME], "changed, so saved"
