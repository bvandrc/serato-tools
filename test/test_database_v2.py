"""What only the database has. What every bin file has is tested in test_bin_file_base, through DatabaseV2."""

from serato_tools.database_v2 import DatabaseV2

from test.helpers.bin_files import MP3_FILENAMES, TEST_DATABASE, TRACKS_DIR
from test.helpers.files import read_bytes, read_text

# the test database parsed, as its __str__ prints it
TEST_DATABASE_TXT_FILE = "test/data/database_v2_test_output.txt"


def test_parse():
    db = DatabaseV2(TEST_DATABASE)
    assert db.to_bytes() == read_bytes(TEST_DATABASE), "round-trips byte-exact"
    assert db.__str__() == read_text(TEST_DATABASE_TXT_FILE)


def test_get_corrupt_tracks():
    db = DatabaseV2(TEST_DATABASE)
    assert db.get_corrupt_tracks() == {}, "no corrupt tracks in the test database"

    fields = DatabaseV2.Fields
    db._entries += [
        (
            fields.TRACK,
            [(fields.FILE_PATH, "Music/Bad.mp3"), (fields.CORRUPT, True), (fields.CORRUPT_REASON, "why")],
        ),
        (fields.TRACK, [(fields.FILE_PATH, "Music/No Reason.mp3"), (fields.CORRUPT, True)]),
        (fields.TRACK, [(fields.FILE_PATH, "Music/Fine.mp3"), (fields.CORRUPT, False)]),
    ]
    assert db.get_corrupt_tracks() == {
        DatabaseV2.get_full_path("Music/Bad.mp3"): "why",
        DatabaseV2.get_full_path("Music/No Reason.mp3"): "",
    }


def test_set_unanalyzed():
    db = DatabaseV2(TEST_DATABASE)
    overview_built = DatabaseV2.Fields.OVERVIEW_BUILT
    target = f"{TRACKS_DIR}/{MP3_FILENAMES.TRIPPST_ENLIGHTEN}"

    def unanalyzed() -> list[str]:
        return [t.relpath for t in db.get_tracks() if not t.get_value(overview_built)]

    before = unanalyzed()
    assert DatabaseV2.get_relative_path(target) not in before

    assert db.set_unanalyzed([target]) is True
    assert sorted(unanalyzed()) == sorted([*before, DatabaseV2.get_relative_path(target)]), "only the given track"

    assert db.set_unanalyzed([target]) is False, "no change when it's already marked"
