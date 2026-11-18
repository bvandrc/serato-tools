import contextlib
import logging
import os
import subprocess
import sys
from unittest import mock

import pytest

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.library import Library
from serato_tools.smart_crate import SmartCrate
from serato_tools.track_cues_v2 import TrackCuesV2
from serato_tools.track_text_frames import TrackTextFrames
from serato_tools.utils.bin_file_base import DataTypeError, SeratoBinFile

from test.helpers.bin_files import LibraryFolders
from test.helpers.files import mock_files
from test.helpers.track_tags import copy_mp3, copy_mp3_without_cues, has_tags_v1

relpath = DatabaseV2.get_relative_path
Colors = TrackCuesV2.TrackColors
# the test mp3's track color
FIXTURE_COLOR = b"\xbb\xbb\xbb"
# track colors as the database holds them, 0xRRGGBB
PURPLE_IN_DB = 0xBB99FF
RED_IN_DB = 0xFF9999
BLUE1_IN_DB = 0x99BBFF


@pytest.fixture
def folders(tmp_dir: str) -> LibraryFolders:
    return LibraryFolders(os.path.join(tmp_dir, "_Serato_"), os.path.join(tmp_dir, "Music"))


def track_paths(file: SeratoBinFile) -> list[str]:
    """The track paths in `file` as saved, read again from disk rather than from its entries in memory."""
    return type(file)(file.filepath).get_track_paths()


def set_genre(database: DatabaseV2, track: str):
    """Sets `track`'s genre to House in `database`, without saving it."""
    database.modify([{"field": DatabaseV2.Fields.GENRE, "files": [track], "func": lambda *args: "House"}])


def file_paths_named(library: Library, names: list[str]) -> list[str]:
    """The paths of the library's database and crates whose file names are in `names`, sorted."""
    files = [library.database, *library.crates, *library.smart_crates]
    return sorted(f.filepath for f in files if os.path.basename(f.filepath) in names)


def test_files_are_parsed_when_first_needed(folders: LibraryFolders):
    library = Library(os.path.join(folders.serato_dir, "does not exist"))
    with pytest.raises(FileNotFoundError):  # the database parsed on first access, not on init
        _ = library.database

    library = Library(folders.serato_dir)
    assert library.crates == [], "no Subcrates folder means no crates"
    assert library.smart_crates == [], "no SmartCrates folder means no smart crates"
    assert library.database is library.database, "database parsed once"


def test_crate_files(folders: LibraryFolders):
    library = Library(folders.serato_dir)
    assert library.crate_files == [], "no crate folders means no crate files"

    crate_dir, smart_crate_dir = (os.path.join(folders.serato_dir, c.DIR) for c in (Crate, SmartCrate))
    mock_files({crate_dir: ["House.crate", ".DS_Store"], smart_crate_dir: ["Deep.scrate"]})
    assert library.crate_files == [
        os.path.join(crate_dir, "House.crate"),
        os.path.join(smart_crate_dir, "Deep.scrate"),
    ], "crates made since the Library was, crates first, and only crate files"
    assert "crates" not in vars(library), "listing the files doesn't parse them"


def test_rename_track_file(folders: LibraryFolders, bin_file_writes: list[str]):
    src, dest = folders.make_track("Old.mp3"), folders.music_path("New.mp3")
    folders.add_to_database(src)
    folders.make_crate("With", [src])
    folders.make_crate("Without", [])
    folders.make_crate("Smart", [src], SmartCrate)
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    changed = library.rename_track_file(src, dest)

    assert os.path.exists(dest), "file at its new path"
    assert not os.path.exists(src), "file gone from its old path"
    assert sorted(bin_file_writes) == sorted([DatabaseV2.FILENAME, "With.crate", "Smart.scrate"]), "only those with it"
    assert sorted(changed) == file_paths_named(library, bin_file_writes), "returns those files"
    old_path, new_path = relpath(src), relpath(dest)
    db_paths = track_paths(library.database)
    assert new_path in db_paths, "db path updated"
    assert old_path not in db_paths, "db old path gone"
    crates = {os.path.basename(c.filepath): c for c in [*library.crates, *library.smart_crates]}
    assert track_paths(crates["With.crate"]) == [new_path], "crate path updated"
    assert track_paths(crates["Smart.scrate"]) == [new_path], "smart crate path updated"


def test_rename_track_file_in_a_given_database(folders: LibraryFolders, bin_file_writes: list[str]):
    src, dest = folders.make_track("Old.mp3"), folders.music_path("New.mp3")
    folders.add_to_database(src)
    db = DatabaseV2(folders.db_file)
    db._entries.append((DatabaseV2.Fields.TRACK, [(DatabaseV2.Fields.FILE_PATH, "Unsaved.mp3")]))
    bin_file_writes.clear()

    Library(folders.serato_dir, database=db).rename_track_file(src, dest)

    assert relpath(dest) in db.get_track_paths(), "the given database updated"
    assert bin_file_writes == [DatabaseV2.FILENAME], "and saved once"
    assert "Unsaved.mp3" in track_paths(db), "with its unsaved changes, rather than reparsed"


@pytest.mark.parametrize(
    "dest, rename_side_effect",
    [
        # os.rename made to overwrite on every OS, as on POSIX, so only Library's own check can refuse
        pytest.param(lambda folders: folders.make_track("Taken.mp3"), os.replace, id="dest exists"),
        # os.rename refusing, as on Windows, a clash os.path.exists misses, such as a case change on some filesystems
        pytest.param(lambda folders: folders.music_path("New.mp3"), FileExistsError, id="os.rename finds a clash"),
    ],
)
def test_rename_track_file_refuses_to_overwrite(
    folders: LibraryFolders, bin_file_writes: list[str], dest, rename_side_effect
):
    src = folders.make_track("Old.mp3")
    folders.add_to_database(src)
    dest_path = dest(folders)
    bin_file_writes.clear()

    with mock.patch("os.rename", side_effect=rename_side_effect), pytest.raises(FileExistsError):
        Library(folders.serato_dir).rename_track_file(src, dest_path)

    assert os.path.exists(src), "src left in place"
    assert bin_file_writes == [], "nothing saved"
    assert relpath(src) in track_paths(DatabaseV2(folders.db_file)), "db unchanged"


def test_rename_track_file_not_in_the_library(folders: LibraryFolders, bin_file_writes: list[str]):
    src, dest = folders.make_track("Unimported.mp3"), folders.music_path("New.mp3")

    changed = Library(folders.serato_dir).rename_track_file(src, dest)

    assert os.path.exists(dest), "file still at its new path"
    assert not os.path.exists(src), "file still gone from its old path"
    assert changed == [], "no library file changed"
    assert bin_file_writes == [], "nothing saved"


def test_remove_track_files(folders: LibraryFolders, bin_file_writes: list[str]):
    removed, missing, kept = (folders.make_track(name) for name in ["Removed.mp3", "Missing.mp3", "Kept.mp3"])
    folders.add_to_database(removed, missing, kept)
    folders.make_crate("With", [removed, kept])
    folders.make_crate("Without", [kept])
    folders.make_crate("Smart", [missing], SmartCrate)
    os.remove(missing)
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    result = library.remove_track_files([removed, missing])

    assert not os.path.exists(removed), "file deleted"
    assert os.path.exists(kept), "other file kept"
    assert result.files_deleted == [removed], "lists only the file that was there to delete"
    assert sorted(bin_file_writes) == sorted([DatabaseV2.FILENAME, "With.crate", "Smart.scrate"]), "only those with it"
    assert sorted(result.library_files_changed) == file_paths_named(library, bin_file_writes)
    kept_path = relpath(kept)
    db_paths = track_paths(library.database)
    assert kept_path in db_paths, "other track kept in db"
    for track in [removed, missing]:
        assert relpath(track) not in db_paths, f"{track} removed from db, even if missing"
    for crate in library.crates:
        assert track_paths(crate) == [kept_path], f"{crate.filepath} has only the kept track"
    assert track_paths(library.smart_crates[0]) == [], "missing track removed from smart crate"


def test_batch_writes_each_changed_file_once(folders: LibraryFolders, bin_file_writes: list[str]):
    first, second, removed = (folders.make_track(name) for name in ["First.mp3", "Second.mp3", "Removed.mp3"])
    folders.add_to_database(first, second, removed)
    folders.make_crate("With", [first, second])
    folders.make_crate("Without", [removed])
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    new_first, new_second = (folders.music_path(name) for name in ["New First.mp3", "New Second.mp3"])
    with library.batch():
        library.rename_track_file(first, new_first)
        library.rename_track_file(second, new_second)
        removed_result = library.remove_track_files([removed])

        assert bin_file_writes == [], "nothing written yet"
        # though they aren't written until the block ends
        assert sorted(removed_result.library_files_changed) == file_paths_named(
            library, [DatabaseV2.FILENAME, "Without.crate"]
        ), "lists the files it changed"
        assert os.path.exists(new_first), "track file renamed right away"
        assert not os.path.exists(removed), "track file deleted right away"

    assert sorted(bin_file_writes) == sorted([DatabaseV2.FILENAME, "With.crate", "Without.crate"]), "each once"
    new_paths = [relpath(p) for p in [new_first, new_second]]
    db_paths = track_paths(library.database)
    for path in new_paths:
        assert path in db_paths, "db path updated"
    assert relpath(removed) not in db_paths, "track removed from db"
    # by name: crates are listed in directory order, which isn't sorted on every filesystem
    crate = next(c for c in library.crates if os.path.basename(c.filepath) == "With.crate")
    assert track_paths(crate) == new_paths, "crate paths updated"


def test_batch_saves_when_the_block_raises(folders: LibraryFolders, bin_file_writes: list[str]):
    src, dest = folders.make_track("Old.mp3"), folders.music_path("New.mp3")
    folders.add_to_database(src)
    bin_file_writes.clear()

    library = Library(folders.serato_dir)

    def rename_then_fail():
        with library.batch():
            library.rename_track_file(src, dest)
            raise RuntimeError("stopped partway")

    with pytest.raises(RuntimeError, match="stopped partway"):  # the exception still propagates
        rename_then_fail()

    assert bin_file_writes == [DatabaseV2.FILENAME]
    assert relpath(dest) in track_paths(library.database), "points at renamed file"


def test_nested_batch_saves_when_the_outermost_ends(folders: LibraryFolders, bin_file_writes: list[str]):
    first, second = folders.make_track("First.mp3"), folders.make_track("Second.mp3")
    folders.add_to_database(first, second)
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    with library.batch():
        with library.batch():
            library.rename_track_file(first, folders.music_path("New First.mp3"))
        assert bin_file_writes == [], "inner batch doesn't save"
        library.rename_track_file(second, folders.music_path("New Second.mp3"))

    assert bin_file_writes == [DatabaseV2.FILENAME], "outer batch saves once"


def test_save_writes_direct_changes_serializing_each_parsed_file_once(
    folders: LibraryFolders, bin_file_writes: list[str]
):
    track = folders.make_track("Track.mp3")
    folders.add_to_database(track)
    folders.make_crate("Crate", [track])
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    set_genre(library.database, track)
    _ = library.crates
    with mock.patch.object(SeratoBinFile, "to_bytes", autospec=True, side_effect=SeratoBinFile.to_bytes) as to_bytes:
        assert library.save() == [library.database.filepath], "returns the files written"

    # the changed database and the unchanged crate, serialized once each
    assert sorted(os.path.basename(c.args[0].filepath) for c in to_bytes.call_args_list) == sorted(
        [DatabaseV2.FILENAME, "Crate.crate"]
    )
    assert bin_file_writes == [DatabaseV2.FILENAME], "only the changed database written"
    assert folders.db_values(DatabaseV2.Fields.GENRE)[relpath(track)] == "House"


def test_save_writes_a_passed_database_before_it_is_read(folders: LibraryFolders, bin_file_writes: list[str]):
    track = folders.make_track("Track.mp3")
    folders.add_to_database(track)
    database = DatabaseV2(folders.db_file)
    set_genre(database, track)
    bin_file_writes.clear()

    library = Library(folders.serato_dir, database=database)
    assert library.save() == [database.filepath]

    assert "database" not in vars(library), "save doesn't read library.database"
    assert bin_file_writes == [DatabaseV2.FILENAME]
    assert folders.db_values(DatabaseV2.Fields.GENRE)[relpath(track)] == "House"


def test_save_skips_unchanged_and_unparsed_files(folders: LibraryFolders, bin_file_writes: list[str]):
    folders.make_crate("Crate", [folders.make_track("Track.mp3")])
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    assert library.save() == [], "nothing parsed"
    assert "database" not in vars(library), "save doesn't parse anything"

    _ = library.database, library.crates
    assert library.save() == [], "nothing changed"
    assert bin_file_writes == []


def make_smart_crate(
    folders: LibraryFolders,
    name: str,
    rule: tuple[SmartCrate.RuleField, SmartCrate.RuleComparison, str],
    tracks: list[str],
) -> str:
    """A smart crate of `tracks` in the library folder, with `rule`, saved."""
    path = folders.make_crate(name, tracks, SmartCrate)
    crate = SmartCrate(path)
    crate.set_rule(*rule)
    crate.save()
    return path


HOUSE_RULE = (SmartCrate.RuleField.GENRE, SmartCrate.RuleComparison.STR_IS, "House")


@pytest.mark.parametrize("batched", [False, True], ids=["unbatched", "batched"])
def test_update_smart_crates(folders: LibraryFolders, bin_file_writes: list[str], batched: bool):
    house = folders.music_path("House.mp3")
    folders.add_to_database(house, fields=[(DatabaseV2.Fields.GENRE, "House")])
    make_smart_crate(folders, "Stale", HOUSE_RULE, [folders.music_path("Not House.mp3")])
    make_smart_crate(folders, "Current", HOUSE_RULE, [house])
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    with library.batch() if batched else contextlib.nullcontext():
        changed = library.update_smart_crates()
        assert bin_file_writes == ([] if batched else ["Stale.scrate"]), "saved now unless batching"

    assert bin_file_writes == ["Stale.scrate"], "only the crate whose tracks changed"
    assert changed == file_paths_named(library, ["Stale.scrate"])
    assert [track_paths(crate) for crate in library.smart_crates] == [[relpath(house)]] * 2


def test_update_smart_crates_changes_nothing_when_a_crate_cant_be_matched(
    folders: LibraryFolders, bin_file_writes: list[str]
):
    folders.add_to_database(folders.music_path("House.mp3"), fields=[(DatabaseV2.Fields.GENRE, "House")])
    make_smart_crate(folders, "A", HOUSE_RULE, [])
    make_smart_crate(folders, "B", (SmartCrate.RuleField.YEAR, SmartCrate.RuleComparison.STR_DATE_BEFORE, "2000"), [])
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    with pytest.raises(NotImplementedError):
        library.update_smart_crates()
    assert not any(crate.has_changed for crate in library.smart_crates), "no crate changed, whichever is listed first"
    assert bin_file_writes == []


def test_set_db_track_tags(folders: LibraryFolders, bin_file_writes: list[str]):
    track, other = copy_mp3(folders.music_dir, "Colored.mp3"), copy_mp3(folders.music_dir, "Other.mp3")
    folders.add_to_database(track, other)
    bin_file_writes.clear()

    result = Library(folders.serato_dir).set_db_track_tags(track, color=Colors.PURPLE, beatgrid_locked=True)

    assert result.database_changed
    assert result.files_written == [track]
    assert bin_file_writes == [DatabaseV2.FILENAME], "database saved once"
    tags = TrackCuesV2(track)
    assert tags.get_track_color() == Colors.PURPLE.value, "color set in tags"
    assert tags.is_beatgrid_locked() is True, "lock set in tags"
    colors, locks = folders.db_values(DatabaseV2.Fields.COLOR), folders.db_values(DatabaseV2.Fields.BEATGRID_LOCKED)
    assert colors[relpath(track)] == PURPLE_IN_DB, "color set in db, as 0xRRGGBB"
    assert locks[relpath(track)] is True, "lock set in db"
    assert relpath(other) not in colors, "other track's color left alone"
    assert relpath(other) not in locks, "other track's lock left alone"
    assert TrackCuesV2(other).get_track_color() == FIXTURE_COLOR, "other track's file left alone"


# key: (value, ID3 frame, database field); the frame holds the value as text, and the database as it is
TEXT_FRAMES = {
    "title": ("A Title", "TIT2", DatabaseV2.Fields.TITLE),
    "artist": ("An Artist", "TPE1", DatabaseV2.Fields.ARTIST),
    "album": ("An Album", "TALB", DatabaseV2.Fields.ALBUM),
    "genre": ("A Genre", "TCON", DatabaseV2.Fields.GENRE),
    "key": ("8A", "TKEY", DatabaseV2.Fields.KEY),
    "grouping": ("TAGGED", "TIT1", DatabaseV2.Fields.GROUPING),
    "publisher": ("A Publisher", "TPUB", DatabaseV2.Fields.PUBLISHER),
    "composer": ("A Composer", "TCOM", DatabaseV2.Fields.COMPOSER),
    "year": ("2020", "TDRC", DatabaseV2.Fields.YEAR),
    "remixer": ("A Remixer", "TPE4", DatabaseV2.Fields.REMIXER),
    "track_number": (3, "TRCK", DatabaseV2.Fields.TRACK_NUMBER),
    "disc_number": (2, "TPOS", DatabaseV2.Fields.DISC_NUMBER),
}


def test_set_db_track_tags_text_frames(folders: LibraryFolders):
    track = copy_mp3(folders.music_dir, "Text.mp3")
    folders.add_to_database(track)

    Library(folders.serato_dir).set_db_tracks_tags(
        {track: {key: value for key, (value, _, _) in TEXT_FRAMES.items()}}  # pyright: ignore[reportArgumentType]
    )

    frames = TrackTextFrames(track)
    assert {key: frames.get(frame_id) for key, (_, frame_id, _) in TEXT_FRAMES.items()} == {
        key: str(value) for key, (value, _, _) in TEXT_FRAMES.items()
    }, "file"
    saved = folders.db_track(track)
    assert {key: saved.get_value(field) for key, (_, _, field) in TEXT_FRAMES.items()} == {
        key: value for key, (value, _, _) in TEXT_FRAMES.items()
    }, "database"


def test_set_db_track_tags_comment(folders: LibraryFolders):
    track = copy_mp3(folders.music_dir, "Comment.mp3")
    folders.add_to_database(track)
    library = Library(folders.serato_dir)

    library.set_db_track_tags(track, comment="A Comment")
    assert TrackTextFrames(track).get(TrackTextFrames.Fields.COMMENT) == "A Comment", "file"
    assert folders.db_values(DatabaseV2.Fields.COMMENT)[relpath(track)] == "A Comment", "database"

    library.set_db_track_tags(track, comment="")
    assert TrackTextFrames(track).get(TrackTextFrames.Fields.COMMENT) is None, "removed from the file"
    assert relpath(track) not in folders.db_values(DatabaseV2.Fields.COMMENT), "removed from the database"


def test_set_db_track_tags_in_a_batch_saves_the_database_when_it_ends(
    folders: LibraryFolders, bin_file_writes: list[str]
):
    track = copy_mp3(folders.music_dir, "Colored.mp3")
    folders.add_to_database(track)
    bin_file_writes.clear()

    library = Library(folders.serato_dir)
    with library.batch():
        assert library.set_db_track_tags(track, color=Colors.PURPLE).database_changed
        assert bin_file_writes == [], "database not written yet"
        assert TrackCuesV2(track).get_track_color() == Colors.PURPLE.value, "file tagged right away"

    assert bin_file_writes == [DatabaseV2.FILENAME]
    assert folders.db_values(DatabaseV2.Fields.COLOR)[relpath(track)] == PURPLE_IN_DB


def test_set_db_tracks_tags_sets_each_its_own_values(folders: LibraryFolders, bin_file_writes: list[str]):
    red, blue = copy_mp3(folders.music_dir, "Red.mp3"), copy_mp3(folders.music_dir, "Blue.mp3")
    folders.add_to_database(red, blue)
    bin_file_writes.clear()

    Library(folders.serato_dir).set_db_tracks_tags({red: {"color": Colors.RED}, blue: {"color": Colors.BLUE1}})

    assert bin_file_writes == [DatabaseV2.FILENAME], "database saved once for every track"
    colors = folders.db_values(DatabaseV2.Fields.COLOR)
    assert colors[relpath(red)] == RED_IN_DB
    assert colors[relpath(blue)] == BLUE1_IN_DB
    assert TrackCuesV2(red).get_track_color() == Colors.RED.value
    assert TrackCuesV2(blue).get_track_color() == Colors.BLUE1.value


# passed to each file's save, not to the deprecated parameter on its edits
@pytest.mark.filterwarnings("error::DeprecationWarning")
@pytest.mark.parametrize(
    "delete_tags_v1", [pytest.param(True, id="delete_tags_v1=True"), pytest.param(False, id="delete_tags_v1=False")]
)
def test_set_db_track_tags_deletes_tags_v1_unless_told_not_to(folders: LibraryFolders, delete_tags_v1: bool):
    track = copy_mp3(folders.music_dir, "Track.mp3")
    folders.add_to_database(track)

    Library(folders.serato_dir).set_db_track_tags(track, color=Colors.RED, delete_tags_v1=delete_tags_v1)

    assert has_tags_v1(track) == (not delete_tags_v1)


def test_set_db_tracks_tags_writes_only_what_changed(folders: LibraryFolders, bin_file_writes: list[str]):
    changed, unchanged = copy_mp3(folders.music_dir, "Changed.mp3"), copy_mp3(folders.music_dir, "Unchanged.mp3")
    folders.add_to_database(changed, unchanged)
    library = Library(folders.serato_dir)
    library.set_db_track_tags(unchanged, color=Colors.GREY)
    bin_file_writes.clear()

    result = library.set_db_track_tags(unchanged, color=Colors.GREY)
    assert not result.database_changed
    assert result.files_written == [], "file not written"
    assert bin_file_writes == [], "database not saved"

    result = library.set_db_tracks_tags({changed: {"color": Colors.PURPLE}, unchanged: {"color": Colors.GREY}})
    assert result.database_changed
    assert result.files_written == [changed], "lists only the file it wrote"


def test_set_db_track_tags_creates_a_missing_tag(folders: LibraryFolders):
    track = copy_mp3_without_cues(folders.music_dir, "New.mp3")
    folders.add_to_database(track)

    Library(folders.serato_dir).set_db_track_tags(track, color=Colors.RED, beatgrid_locked=True)

    tags = TrackCuesV2(track)
    assert tags.get_track_color() == Colors.RED.value, "color added to the file"
    assert tags.is_beatgrid_locked() is True, "lock added to the file"
    assert folders.db_values(DatabaseV2.Fields.COLOR)[relpath(track)] == RED_IN_DB


def _then_a_track_with(tags: dict[str, object]):
    """A batch of the first track's color, then a second track with `tags`."""
    return lambda folders, first: {first: {"color": Colors.RED}, copy_mp3(folders.music_dir, "Second.mp3"): tags}


@pytest.mark.parametrize(
    "tracks, error, message",
    [
        pytest.param(
            lambda _folders, first: {first: {"color": Colors.RED, "rating": 5}},
            ValueError,
            "unknown track tags",
            id="an unknown key",
        ),
        pytest.param(
            lambda _folders, first: {first: {"color": Colors.RED}, "Second.flac": {"beatgrid_locked": True}},
            ValueError,
            "unsupported file type",
            id="a later track's file unreadable",
        ),
        pytest.param(
            _then_a_track_with({"track_number": -1}),
            ValueError,
            "holds a number from 0 to 4294967295, not -1",
            id="a later track's number the database can't hold",
        ),
        pytest.param(
            _then_a_track_with({"color": "red"}),
            DataTypeError,
            "must be TrackColors when field is color",
            id="a later track's color as text",
        ),
        pytest.param(
            _then_a_track_with({"beatgrid_locked": "yes"}),
            DataTypeError,
            "must be bool when field is beatgrid_locked",
            id="a later track's lock as text",
        ),
        pytest.param(
            _then_a_track_with({"title": 5}),
            DataTypeError,
            "must be str when field is title",
            id="a later track's title as a number",
        ),
        # a bool is an int, but True isn't a track number
        pytest.param(
            _then_a_track_with({"track_number": True}),
            DataTypeError,
            "must be int when field is track_number",
            id="a later track's number as a bool",
        ),
    ],
)
def test_set_db_tracks_tags_failing_changes_nothing(
    folders: LibraryFolders, bin_file_writes: list[str], tracks, error: type[Exception], message: str
):
    first = copy_mp3(folders.music_dir, "First.mp3")
    folders.add_to_database(first)
    batch = tracks(folders, first)
    bin_file_writes.clear()

    with pytest.raises(error, match=message):
        Library(folders.serato_dir).set_db_tracks_tags(batch)
    assert bin_file_writes == [], "database not saved"
    assert TrackCuesV2(first).get_track_color() == FIXTURE_COLOR, "first file not changed"


def test_set_db_tracks_tags_with_no_values_doesnt_open_the_file(folders: LibraryFolders):
    # an unsupported file type would raise when opened
    result = Library(folders.serato_dir).set_db_tracks_tags({"Unopened.flac": {}})
    assert not result.database_changed
    assert result.files_written == []


def test_set_db_track_tags_track_not_in_database_warns(folders: LibraryFolders, caplog: pytest.LogCaptureFixture):
    track = copy_mp3(folders.music_dir, "Unknown.mp3")

    with caplog.at_level(logging.WARNING):
        result = Library(folders.serato_dir).set_db_track_tags(track, color=Colors.RED)

    assert not result.database_changed, "database unchanged"
    assert result.files_written == [track], "file still written"
    assert "isn't in the database" in caplog.text
    assert TrackCuesV2(track).get_track_color() == Colors.RED.value, "file still set"


def test_set_db_track_tags_without_track_tags_extra(folders: LibraryFolders):
    # a fresh interpreter, with mutagen blocked as if the track_tags extra weren't installed
    code = """if True:
        import sys
        sys.modules["mutagen"] = None
        from serato_tools.library import Library
        library = Library(sys.argv[1])
        library.database  # the rest of Library still works
        try:
            library.set_db_track_tags("track.mp3", beatgrid_locked=True)
        except ImportError as error:
            print(error)
    """
    result = subprocess.run(
        [sys.executable, "-c", code, folders.serato_dir], capture_output=True, text=True, check=True
    )
    assert 'pip install "serato-tools[track_tags]"' in result.stdout
