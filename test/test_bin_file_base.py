import copy
import json
import os
import struct
from collections.abc import Iterable
from enum import StrEnum, unique
from unittest import mock

import pytest

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils.bin_file_base import DataTypeError, DeeplyNestedListError, SeratoBinFile

from test.helpers.bin_files import MP3_FILENAMES, TEST_CRATE, TEST_DATABASE, TRACKS_DIR
from test.helpers.files import copy_into, mock_files, read_bytes, read_text
from test.helpers.platforms import POSIX_ONLY, WINDOWS_ONLY


@pytest.fixture
def db_file(tmp_dir: str) -> str:
    """A copy of the test database, as its own file name."""
    return copy_into(tmp_dir, TEST_DATABASE, DatabaseV2.FILENAME)


# paths


@pytest.mark.parametrize(
    "path, expected",
    [
        (f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}", f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}"),
        pytest.param(
            "C:\\" + f"{TRACKS_DIR}/{MP3_FILENAMES.ZEDSDEAD_INTHEBEGINNING}".replace("/", "\\"),
            f"{TRACKS_DIR}/{MP3_FILENAMES.ZEDSDEAD_INTHEBEGINNING}",
            marks=WINDOWS_ONLY,
        ),
        pytest.param(
            f"{TRACKS_DIR}/{MP3_FILENAMES.ZEDSDEAD_INTHEBEGINNING}".replace("/", "\\"),
            f"{TRACKS_DIR}/{MP3_FILENAMES.ZEDSDEAD_INTHEBEGINNING}",
            marks=WINDOWS_ONLY,
        ),
        pytest.param(
            f"C:/{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}",
            f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}",
            marks=WINDOWS_ONLY,
        ),
        pytest.param(
            f"/{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}",
            f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}",
            marks=POSIX_ONLY,
        ),
    ],
)
def test_relative_path(path: str, expected: str):
    assert SeratoBinFile.get_relative_path(path) == expected


@WINDOWS_ONLY
def test_full_path_keeps_given_drive():
    path = f"D:/{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}"
    assert SeratoBinFile.get_full_path(path) == os.path.normpath(path)


@POSIX_ONLY
def test_full_path_keeps_absolute_posix_path():
    path = f"/Volumes/USB/{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}"
    assert SeratoBinFile.get_full_path(path) == path


def test_full_path_without_drive_is_absolute():
    # Serato stores track paths with no drive or leading separator
    full_path = SeratoBinFile.get_full_path(f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}")
    assert os.path.isabs(full_path)
    assert full_path.endswith(os.path.normpath(f"/{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}"))


# a subclass's fields


def test_a_subclass_extending_field_enums_gets_its_fields_and_names():
    @unique
    class ExtraFields(StrEnum):
        EXTRA_THING = "uxtr"

    class ExtendedCrate(Crate):
        FIELD_ENUMS = (*Crate.FIELD_ENUMS, ExtraFields)

    assert "uxtr" in ExtendedCrate.FIELDS
    assert Crate.FIELDS < ExtendedCrate.FIELDS, "the rest kept"
    assert ExtendedCrate.FIELD_NAMES["uxtr"] == "Extra Thing"
    assert ExtendedCrate.get_field_name("uxtr") == "Extra Thing"
    assert "uxtr" not in Crate.FIELDS, "the class it extends is unchanged"
    assert "uxtr" not in Crate.FIELD_NAMES
    assert Crate.get_field_name("uxtr") == "Unknown Field"


# loading a file: from its bytes, from JSON, or, for a file that doesn't exist yet, from its class's defaults


@pytest.mark.parametrize(
    "cut_at",
    [pytest.param(3, id="partway through a header"), pytest.param(-1, id="partway through an entry")],
)
def test_a_file_cut_off_raises(tmp_dir: str, cut_at: int):
    path = os.path.join(tmp_dir, "database V2")
    with open(path, "wb") as f:
        f.write(read_bytes(TEST_DATABASE)[:cut_at])
    with pytest.raises(ValueError, match="file ends partway through"):
        DatabaseV2(path)


def test_an_untested_version_raises(tmp_dir: str):
    # rather than risk misparsing a format it hasn't seen, and corrupting it when saved
    version = Crate.DEFAULT_ENTRIES[0][1]
    assert isinstance(version, str)
    untested = "9.9" + version[3:]  # the same length, so the entry's header still fits
    data = read_bytes(TEST_CRATE)
    assert data.count(version.encode("utf-16-be")) == 1
    path = os.path.join(tmp_dir, "Untested.crate")
    with open(path, "wb") as f:
        f.write(data.replace(version.encode("utf-16-be"), untested.encode("utf-16-be")))
    with pytest.raises(ValueError, match="Untested version"):
        Crate(path)


def entry_bytes(field: str, data: bytes) -> bytes:
    """An entry as it's stored: its 4-character field name, its length, then `data`."""
    return struct.pack(">4sI", field.encode("ascii"), len(data)) + data


# rather than read a value it would write back differently, or not at all
@pytest.mark.parametrize(
    "entry, message",
    [
        pytest.param(
            entry_bytes(SeratoBinFile.Fields.REVERSE_ORDER.value, b"\x02"),
            "unexpected boolean value for field brev",
            id="a boolean neither 00 nor 01",
        ),
        pytest.param(entry_bytes("xabc", b"\x00"), "unexpected type for field: xabc", id="a field of no known type"),
        pytest.param(entry_bytes("stst", b"\x01"), "stst holds a", id="a u16 that isn't 2 bytes"),
        pytest.param(entry_bytes("utst", b"\x00\x00\x01"), "utst holds a", id="a u32 that isn't 4 bytes"),
    ],
)
def test_parsing_a_value_it_would_rewrite_raises(tmp_dir: str, entry: bytes, message: str):
    path = os.path.join(tmp_dir, "Test.crate")
    with open(path, "wb") as f:
        f.write(read_bytes(TEST_CRATE) + entry)
    with pytest.raises(ValueError, match=message):
        Crate(path)


# DatabaseV2 can't be created new. Crate and SmartCrate share CrateBase.DEFAULT_VIEW_ENTRIES' sublists
@pytest.mark.parametrize("cls", [Crate, SmartCrate], ids=lambda cls: cls.__name__)
def test_new_file_shares_no_entries_with_its_class_default(tmp_dir: str, cls: type[Crate] | type[SmartCrate]):
    defaults = {c: copy.deepcopy(c.DEFAULT_ENTRIES) for c in (Crate, SmartCrate)}
    a = cls.new(os.path.join(tmp_dir, "A" + cls.EXTENSION))
    a.add_tracks(["/music/track1.mp3"])
    b = cls.new(os.path.join(tmp_dir, "B" + cls.EXTENSION))

    for i, (field, value) in enumerate(a._entries[: len(defaults[cls])]):
        if isinstance(value, list):
            assert value is not cls.DEFAULT_ENTRIES[i][1], f"{field} sublist shared with class default"
            assert value is not b._entries[i][1], f"{field} sublist shared between instances"
            value.append((SeratoBinFile.Fields.COLUMN_NAME, "mutated"))

    for c, default in defaults.items():
        assert c.DEFAULT_ENTRIES == default, f"{c.__name__}'s default mutated"
    assert b._entries == defaults[cls], "other instance must not inherit tracks or nested edits"


def test_a_file_that_doesnt_exist_raises(tmp_dir: str):
    with pytest.raises(FileNotFoundError):
        Crate(os.path.join(tmp_dir, "Typo.crate"))


def test_new_refuses_a_file_that_exists():
    with pytest.raises(FileExistsError):
        Crate.new(TEST_CRATE)


def test_json_round_trip():
    db_from_bin = DatabaseV2(TEST_DATABASE)
    assert db_from_bin.to_json_object() == json.loads(read_text("test/data/database_v2_json.json"))

    db_from_json = DatabaseV2("test/data/database_v2_json.json")
    assert db_from_json.__str__() == db_from_bin.__str__(), "loaded from a JSON file"

    db_from_json._entries = []
    db_from_json.from_json_object(db_from_bin.to_json_object())
    assert db_from_json.__str__() == db_from_bin.__str__(), "from_json_object"


def test_mistyped_json_value_is_refused(tmp_dir: str):
    db = DatabaseV2(TEST_DATABASE)
    original_entries = copy.deepcopy(db._entries)
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
    assert db._entries == original_entries, "existing entries left as they were"


# changing a file's tracks, through DatabaseV2, whose tracks have the most fields


# the changes that turn the test database into database_v2_test_modified_output.txt
EVERY_TRACK_RULES: list[DatabaseV2.ModifyRule] = [
    {"field": DatabaseV2.Fields.DATE_ADDED_U, "func": lambda *args: 1735748100},
    {"field": DatabaseV2.Fields.DATE_ADDED_T, "func": lambda *args: "1735748100"},
    {"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "NEW_GROUPING"},
]


def test_modify_every_track():
    db = DatabaseV2(TEST_DATABASE)
    assert db.modify(EVERY_TRACK_RULES) is True, "reports change"
    assert db.__str__() == read_text("test/data/database_v2_test_modified_output.txt")
    assert db.to_bytes() == read_bytes("test/data/database_v2_test_modified_output.bin")


def test_modify_given_files():
    db = DatabaseV2(TEST_DATABASE)
    db.modify(EVERY_TRACK_RULES)  # database_v2_test_modified_output_2.txt has these changes too

    rule: DatabaseV2.ModifyRule = {
        "field": DatabaseV2.Fields.GENRE,
        "func": lambda *args: "NEW_GENRE",
        # each track given by a path in a different form
        "files": [
            f"{TRACKS_DIR}/{MP3_FILENAMES.ZEDSDEAD_INTHEBEGINNING}",
            os.sep + os.path.normpath(f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}"),
        ]
        # backslashes and drive letters only mean something on Windows
        + (
            [
                f"{TRACKS_DIR}/{MP3_FILENAMES.ZEDSDEAD_INTHEBEGINNING}".replace("/", "\\"),
                f"C:/{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}",
            ]
            if os.name == "nt"
            else []
        ),
    }
    assert db.modify([rule]) is True, "reports change"
    assert db.__str__() == read_text("test/data/database_v2_test_modified_output_2.txt")
    assert db.to_bytes() == read_bytes("test/data/database_v2_test_modified_output_2.bin")


def test_modify_passes_later_rules_the_new_path():
    db = DatabaseV2(TEST_DATABASE)
    old, new = db.get_track_paths()[:2]
    db.remove_tracks([new])  # so moving a track there doesn't duplicate one
    seen: list[str] = []
    with mock.patch("os.path.exists", return_value=True):
        db.modify(
            [
                {"field": DatabaseV2.Fields.FILE_PATH, "func": lambda f, _: new if f == old else None},
                {"field": DatabaseV2.Fields.GENRE, "func": lambda f, _: seen.append(f) if f == new else None},
            ]
        )
    assert seen == [new]


def test_modify_empty_value_removes_field(db_file: str):
    # as Serato does when a tag is cleared
    db = DatabaseV2(db_file)
    target = f"{TRACKS_DIR}/{MP3_FILENAMES.SIR_DEVILS}"
    other = f"{TRACKS_DIR}/{MP3_FILENAMES.SLAYCUB_VISCERALPLANET}"
    clear_grouping: list[DatabaseV2.ModifyRule] = [
        {"field": DatabaseV2.Fields.GROUPING, "files": [target], "func": lambda *args: ""}
    ]

    def grouping(database: DatabaseV2, relpath: str):
        track = next(t for t in database.get_tracks() if t.relpath == relpath)
        return track.get_value(DatabaseV2.Fields.GROUPING) if DatabaseV2.Fields.GROUPING in track.fields else None

    assert db.modify(clear_grouping) is True, "reports removal"
    assert grouping(db, target) is None, "removed rather than set empty"
    assert grouping(db, other) == "UNTAGGED", "other tracks left as they were"
    assert db.modify(clear_grouping) is False, "reports no change when already gone"
    db.save()
    assert grouping(DatabaseV2(db_file), target) is None, "removed in the saved file"

    with pytest.raises(ValueError, match="can't remove a track's path"):
        db.modify([{"field": DatabaseV2.Fields.FILE_PATH, "files": [target], "func": lambda *args: ""}])


def test_modify_tracks_given_files():
    db = DatabaseV2(TEST_DATABASE)
    target = f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}"

    seen: list[str] = []

    def func(track: DatabaseV2.Track):
        seen.append(track.relpath)
        return track

    db.modify_tracks(func, files=[target])
    assert seen == [DatabaseV2.get_relative_path(target)], "only the given track is passed to func"


def _raises_for_the_second_track():
    calls = 0

    def func(track: DatabaseV2.Track):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second track")
        track.set_value(DatabaseV2.Fields.GENRE, "Changed")
        return track

    return func


def _skips_set_value(track: DatabaseV2.Track):
    # as a value assigned straight to the attribute, which set_value would have checked
    setattr(track, DatabaseV2.Fields.GENRE, 1)
    return track


@pytest.mark.parametrize(
    "change, error",
    [
        pytest.param(
            lambda db: db.modify_tracks(_raises_for_the_second_track()),
            RuntimeError,
            id="func raising for a later track",
        ),
        pytest.param(lambda db: db.modify_tracks(_skips_set_value), DataTypeError, id="a value that skipped set_value"),
        pytest.param(
            lambda db: db.modify([{"field": DatabaseV2.Fields.GENRE, "func": lambda *_: 1}]),
            DataTypeError,
            id="modify with a value of the wrong type",
        ),
    ],
)
def test_modify_tracks_that_fails_changes_nothing(change, error: type[Exception]):
    db = DatabaseV2(TEST_DATABASE)
    with pytest.raises(error):
        change(db)
    assert not db.has_changed, "the tracks before it left as they were"


def test_remove_tracks():
    db = DatabaseV2(TEST_DATABASE)
    paths = db.get_track_paths()
    assert len(paths) > 2

    assert db.remove_tracks(paths[:2]) is True, "reports removal"
    assert db.get_track_paths() == paths[2:], "removes exactly the given tracks, keeping order"
    assert db.remove_tracks(paths[:2]) is False, "reports no change when already gone"

    # a path in another case, as a case-insensitive drive allows, matches as modify's files do
    assert db.remove_tracks([paths[2].upper()]) is True
    assert db.get_track_paths() == paths[3:]


def test_remove_duplicates():
    db = DatabaseV2("test/data/database_v2_duplicates.bin")
    assert db.__str__() == read_text("test/data/database_v2_duplicates_output.txt"), "original"
    assert db.remove_duplicates() is True, "reports removal"
    assert db.__str__() == read_text("test/data/database_v2_duplicates_output_deduped.txt"), "deduped"
    assert db.remove_duplicates() is False, "nothing left to remove"


def test_remove_duplicates_removes_a_repeat_in_another_case():
    db = DatabaseV2(TEST_DATABASE)
    paths = db.get_track_paths()
    db._entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, paths[0].upper())]))

    assert db.remove_duplicates() is True
    assert db.get_track_paths() == paths, "the first kept"


def test_get_entries_matching_tracks():
    db = DatabaseV2(TEST_DATABASE)

    def track_paths(entries: Iterable[DatabaseV2.EntryFull]) -> list[str]:
        return [
            str({f: v for f, _, v in value}[DatabaseV2.Fields.FILE_PATH])
            for field, _, value in entries
            if field == DatabaseV2.Fields.TRACK and isinstance(value, list)
        ]

    def not_tracks(entries: Iterable[DatabaseV2.EntryFull]) -> list[DatabaseV2.EntryFull]:
        return [entry for entry in entries if entry[0] != DatabaseV2.Fields.TRACK]

    assert track_paths(db.get_entries()) == db.get_track_paths(), "every track by default"
    matched = track_paths(db.get_entries(track_matcher="d'EVILS"))
    assert matched == [f"{TRACKS_DIR}/{MP3_FILENAMES.SIR_DEVILS}"], "only the tracks the regex matches, ignoring case"
    assert not_tracks(db.get_entries("d'evils")) == not_tracks(db.get_entries()), "every other entry"


def test_change_track_path(new_crate: Crate, tmp_dir: str):
    src, other = (os.path.join(tmp_dir, name) for name in ["Old.mp3", "Other.mp3"])
    [dest] = mock_files({tmp_dir: ["New.mp3"]})
    new_crate.add_tracks([src, other])

    assert new_crate.change_track_path(src, dest) is True, "reports that the file had the track"
    assert new_crate.get_track_paths() == [SeratoBinFile.get_relative_path(p) for p in [dest, other]], "in its place"


def test_change_track_path_of_a_track_the_file_doesnt_have(crate_file: str, tmp_dir: str):
    crate = Crate(crate_file)
    [dest] = mock_files({tmp_dir: ["New.mp3"]})
    assert crate.change_track_path(os.path.join(tmp_dir, "Not In Crate.mp3"), dest) is False
    assert not crate.has_changed


def test_change_track_path_to_a_file_that_doesnt_exist_raises(new_crate: Crate, tmp_dir: str):
    src = os.path.join(tmp_dir, "Old.mp3")
    new_crate.add_tracks([src])
    new_crate.save()

    with pytest.raises(FileNotFoundError):
        new_crate.change_track_path(src, os.path.join(tmp_dir, "Missing.mp3"))
    assert not new_crate.has_changed
    assert new_crate.get_track_paths() == [SeratoBinFile.get_relative_path(src)]


# a track's fields


def test_a_nested_entry_list_raises_naming_the_field():
    path = SeratoBinFile.Fields.FILE_PATH.value
    entries = [(path, "a.mp3"), ("onst", [(path, "b.mp3")])]
    with pytest.raises(DeeplyNestedListError, match="in field onst"):
        SeratoBinFile.Track(entries, path_key=path)

    db = DatabaseV2(TEST_DATABASE)
    db._entries.append((SeratoBinFile.Fields.TRACK.value, entries))
    with pytest.raises(DeeplyNestedListError, match=rf"in field {SeratoBinFile.Fields.TRACK.value}.*a\.mp3"):
        list(db.get_entries())


def test_set_value_refuses_a_value_its_field_cant_hold():
    fields = SeratoBinFile.Fields
    path, genre = fields.FILE_PATH.value, fields.GENRE.value
    track = SeratoBinFile.Track([(path, "Music/a.mp3"), (genre, "House")], path_key=path)
    with pytest.raises(DataTypeError):  # the path
        track.set_value(path, 1)
    with pytest.raises(DataTypeError):  # another text field
        track.set_value(genre, 1)
    with pytest.raises(ValueError, match="holds a number from 0 to 4294967295"):  # a number too big
        track.set_value(fields.PLAY_COUNT.value, 2**32)
    assert track.to_entries() == [(path, "Music/a.mp3"), (genre, "House")], "values kept"


def test_remove_field():
    path, genre = SeratoBinFile.Fields.FILE_PATH.value, SeratoBinFile.Fields.GENRE.value
    track = SeratoBinFile.Track([(path, "a.mp3"), (genre, "House")], path_key=path)
    only_path = [(path, "a.mp3")]

    assert track.remove_field(genre) is True, "reports removal"
    assert track.to_entries() == only_path, "removed from the entries written back"
    assert track.remove_field(genre) is False, "reports no change when already gone"

    # as Serato does when a tag is cleared
    track.set_value(genre, "House")
    track.set_value(genre, "")
    assert track.to_entries() == only_path, "set_value empty removes it, rather than setting it empty"
    track.set_value(genre, "")
    assert track.to_entries() == only_path, "set_value empty doesn't add it when already gone"

    # a track can't be without its path
    with pytest.raises(ValueError, match="can't remove a track's path"):
        track.remove_field(path)
    with pytest.raises(ValueError, match="can't remove a track's path"):
        track.set_value(path, "")
    assert track.to_entries() == only_path, "path kept"


# has_changed and save, mostly through Crate, the smallest of the bin file classes


@pytest.fixture
def crate_file(tmp_dir: str) -> str:
    """A copy of the test crate, under its own name, so a test can also take `new_crate`."""
    return copy_into(tmp_dir, TEST_CRATE)


def test_save_writes_its_own_file_only_when_changed(tmp_dir: str, crate_file: str, bin_file_writes: list[str]):
    crate = Crate(crate_file)
    assert not crate.has_changed, "as loaded"
    assert crate.save() is False, "unchanged"
    assert bin_file_writes == [], "unchanged, so not written"
    assert crate.save(force=True) is True, "forced"
    assert bin_file_writes == [os.path.basename(crate_file)], "forced, so written"
    copy_file = os.path.join(tmp_dir, "Copy.crate")
    assert crate.save(copy_file) is True, "saving elsewhere always writes"
    assert read_bytes(copy_file) == read_bytes(crate_file), "as it was"

    crate.add_tracks(["/music/track1.mp3"])
    assert crate.has_changed, "track added"
    crate.save(copy_file)
    assert crate.has_changed, "saving a copy elsewhere leaves its own file unsaved"
    with mock.patch.object(Crate, "to_bytes", autospec=True, side_effect=Crate.to_bytes) as to_bytes:
        assert crate.save() is True
    assert to_bytes.call_count == 1, "serialized once, to check and to write"
    assert Crate(crate_file).get_track_paths() == crate.get_track_paths(), "written"
    assert not crate.has_changed, "saved"
    assert crate.save() is False, "not written again"


def test_has_changed_sees_in_place_edits(crate_file: str):
    crate = Crate(crate_file)
    sorting = crate._entries[1][1]
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


def test_new_file_has_changed_until_saved(new_crate: Crate):
    assert new_crate.has_changed, "saving creates the file"
    new_crate.add_tracks(["/music/track1.mp3"])
    new_crate.save()
    assert not new_crate.has_changed
    assert Crate(new_crate.filepath).get_track_paths() == new_crate.get_track_paths(), "created with its tracks"


def test_file_loaded_from_json_hasnt_changed(tmp_dir: str, crate_file: str):
    json_file = os.path.join(tmp_dir, "Test.json")
    Crate(crate_file).write_json(json_file)
    crate = Crate(json_file)
    assert not crate.has_changed
    crate.add_tracks(["/music/track1.mp3"])
    assert crate.has_changed


@pytest.mark.parametrize(
    "field, value",
    [
        pytest.param("utkn", 2**32 - 1, id="the biggest u32"),
        pytest.param("sxyz", 2**16 - 1, id="the biggest u16"),
        pytest.param("tsng", "A Title", id="text"),
        pytest.param("bbgl", False, id="a boolean"),
        pytest.param(SeratoBinFile.Fields.TRACK.value, [], id="an entry list"),
    ],
)
def test_check_value_takes_a_value_its_field_can_hold(field: str, value: SeratoBinFile.Value):
    SeratoBinFile.check_value(field, value)


# as saving it would raise, but without changing anything
@pytest.mark.parametrize(
    "field, value, error, message",
    [
        pytest.param(
            "utkn", 2**32, ValueError, "utkn holds a number from 0 to 4294967295, not 4294967296", id="u32 + 1"
        ),
        pytest.param("utkn", -1, ValueError, "not -1", id="a negative u32"),
        pytest.param("sxyz", 2**16, ValueError, "sxyz holds a number from 0 to 65535, not 65536", id="u16 + 1"),
        pytest.param("utkn", "3", DataTypeError, "must be int", id="text in a number field"),
        pytest.param("bbgl", "yes", DataTypeError, "must be bool", id="text in a boolean field"),
        pytest.param(SeratoBinFile.Fields.TRACK.value, "x", DataTypeError, "must be list", id="text for an entry list"),
    ],
)
def test_check_value_raises_for_a_value_its_field_cant_hold(
    field: str, value: SeratoBinFile.Value, error: type[Exception], message: str
):
    with pytest.raises(error, match=message):
        SeratoBinFile.check_value(field, value)


@pytest.mark.parametrize(
    "entry, error, message",
    [
        pytest.param(
            (SeratoBinFile.Fields.TRACK, "not a list"), DataTypeError, "must be list", id="a track that isn't a list"
        ),
        pytest.param(
            (SeratoBinFile.Fields.VERSION, "9.9/Serato ScratchLive Crate"),
            ValueError,
            "Untested version",
            id="a version",
        ),
        pytest.param(
            (SeratoBinFile.Fields.REVERSE_ORDER.value, "x"), DataTypeError, "must be bool", id="text in a boolean field"
        ),
        pytest.param(("tvcn", 5), DataTypeError, "must be str", id="a number in a text field"),
        pytest.param(("uadd", "1"), DataTypeError, "must be int", id="text in a number field"),
        pytest.param(
            (SeratoBinFile.Fields.TRACK_PATH.value, b"x"), DataTypeError, "must be str", id="bytes in a text field"
        ),
        pytest.param(("abcde", "x"), ValueError, "field names are 4 characters", id="a 5-character field name"),
        pytest.param(
            ("utkn", -1), ValueError, "utkn holds a number from 0 to 4294967295, not -1", id="a negative number"
        ),
        pytest.param(("utkn", 2**32), ValueError, "not 4294967296", id="a number too big for its field"),
    ],
)
def test_saving_a_value_it_cant_write_raises_and_leaves_the_file(
    crate_file: str, entry: SeratoBinFile.Entry, error: type[Exception], message: str
):
    orig = read_bytes(crate_file)
    crate = Crate(crate_file)
    if entry[0] == SeratoBinFile.Fields.VERSION:
        crate._entries[0] = entry
    else:
        crate._entries.append(entry)
    with pytest.raises(error, match=message):
        crate.save()
    assert read_bytes(crate_file) == orig, "serialized before the file is opened, so it isn't emptied"


def test_saving_before_parsing_finished_raises_and_leaves_the_file(db_file: str):
    class SavesTooEarly(DatabaseV2):
        def __init__(self, file: str):
            self.filepath = file
            self.save()
            super().__init__(file)

    with pytest.raises(RuntimeError):
        SavesTooEarly(db_file)
    assert read_bytes(db_file) == read_bytes(TEST_DATABASE)


def test_find_missing_relocates_tracks(new_crate: Crate, tmp_dir: str, bin_file_writes: list[str]):
    old_dir, new_dir = os.path.join(tmp_dir, "old"), os.path.join(tmp_dir, "new")
    mock_files({new_dir: ["A.mp3", "B.mp3", "C.mp3"]})
    new_crate.add_tracks([os.path.join(old_dir, name) for name in ["A.mp3", "B.mp3", "C.mp3", "Z.mp3"]])
    new_crate.save()
    bin_file_writes.clear()

    # a folder for the first: the rest that are in it are found there without asking; then "s" skips Z
    with mock.patch("builtins.input", side_effect=[new_dir, "s"]) as answers, mock.patch("builtins.print"):
        new_crate.find_missing()

    assert answers.call_count == 2, "asked for A and Z only"
    assert new_crate.get_track_paths() == [
        *(SeratoBinFile.get_relative_path(os.path.join(new_dir, name)) for name in ["A.mp3", "B.mp3", "C.mp3"]),
        SeratoBinFile.get_relative_path(os.path.join(old_dir, "Z.mp3")),
    ]
    assert bin_file_writes == ["Test.crate"], "saved once"
    assert not new_crate.has_changed


@pytest.fixture
def crate_of_missing_tracks(new_crate: Crate, tmp_dir: str, bin_file_writes: list[str]) -> Crate:
    """A saved crate of A.mp3 and B.mp3 in tmp_dir's "old" folder, which doesn't exist."""
    new_crate.add_tracks([os.path.join(tmp_dir, "old", name) for name in ["A.mp3", "B.mp3"]])
    new_crate.save()
    bin_file_writes.clear()
    return new_crate


def test_find_missing_takes_a_files_new_path(crate_of_missing_tracks: Crate, tmp_dir: str):
    crate = crate_of_missing_tracks
    b = crate.get_track_paths()[1]
    [renamed] = mock_files({tmp_dir: ["Renamed.mp3"]})

    # a file for A, rather than a folder; then "s" skips B
    with mock.patch("builtins.input", side_effect=[renamed, "s"]), mock.patch("builtins.print"):
        crate.find_missing()

    assert Crate(crate.filepath).get_track_paths() == [SeratoBinFile.get_relative_path(renamed), b], "saved"


def test_find_missing_interrupted_changes_nothing(
    crate_of_missing_tracks: Crate, tmp_dir: str, bin_file_writes: list[str]
):
    crate = crate_of_missing_tracks
    [renamed] = mock_files({tmp_dir: ["Renamed.mp3"]})

    # A is relocated, then the prompt for B is interrupted
    with (
        mock.patch("builtins.input", side_effect=[renamed, KeyboardInterrupt()]),
        mock.patch("builtins.print"),
        pytest.raises(KeyboardInterrupt),
    ):
        crate.find_missing()

    assert not crate.has_changed, "A's relocation undone"
    assert bin_file_writes == []


# a rule for a track the test database doesn't have, so it changes nothing
NO_MATCH: list[DatabaseV2.ModifyRule] = [
    {"field": DatabaseV2.Fields.GROUPING, "files": ["Not In Library.mp3"], "func": lambda *args: "X"}
]


def test_methods_that_save_skip_it_when_unchanged(db_file: str, bin_file_writes: list[str]):
    db = DatabaseV2(db_file)
    db.modify_and_save(NO_MATCH)
    assert bin_file_writes == [], "modify_and_save unchanged, so not saved"

    # the fixture's tracks don't exist here, so each one prompts; "s" skips it
    with mock.patch("builtins.input", return_value="s"), mock.patch("builtins.print"):
        db.find_missing()
    assert bin_file_writes == [], "find_missing relocated nothing, so not saved"

    db.modify_and_save(NO_MATCH, os.path.join(os.path.dirname(db_file), "copy"))
    assert bin_file_writes == ["copy"], "saved anyway when given another file"

    db.modify_and_save([{"field": DatabaseV2.Fields.GROUPING, "func": lambda *args: "X"}])
    assert bin_file_writes == ["copy", DatabaseV2.FILENAME], "changed, so saved"


@WINDOWS_ONLY  # paths are only case-insensitive on Windows
def test_modify_and_save_to_its_own_path_in_another_case_skips_it_when_unchanged(
    db_file: str, bin_file_writes: list[str]
):
    DatabaseV2(db_file).modify_and_save(NO_MATCH, db_file.upper())
    assert bin_file_writes == []
