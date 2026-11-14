import os
import unittest

from serato_tools.database_v2 import DatabaseV2

from test.helpers import TEST_DATABASE, read_bytes, read_text


class TestCase(unittest.TestCase):
    """What only the database has. What every bin file has is tested in test_bin_file_base, through DatabaseV2."""

    def test_parse_and_serialize(self):
        file = os.path.abspath(TEST_DATABASE)
        db = DatabaseV2(file)

        self.maxDiff = None
        self.assertEqual(db.to_bytes(), read_bytes(file), "to_bytes")
        self.assertEqual(db.__str__(), read_text("test/data/database_v2_test_output.txt", "utf-16"), "parse")

    def test_get_corrupt_tracks(self):
        db = DatabaseV2(TEST_DATABASE)
        self.assertEqual(db.get_corrupt_tracks(), {}, "no corrupt tracks in the test database")

        fields = DatabaseV2.Fields
        db.entries += [
            (
                fields.TRACK,
                [(fields.FILE_PATH, "Music/Bad.mp3"), (fields.CORRUPT, True), (fields.CORRUPT_REASON, "why")],
            ),
            (fields.TRACK, [(fields.FILE_PATH, "Music/No Reason.mp3"), (fields.CORRUPT, True)]),
            (fields.TRACK, [(fields.FILE_PATH, "Music/Fine.mp3"), (fields.CORRUPT, False)]),
        ]
        self.assertEqual(
            db.get_corrupt_tracks(),
            {DatabaseV2.get_full_path("Music/Bad.mp3"): "why", DatabaseV2.get_full_path("Music/No Reason.mp3"): ""},
        )


if __name__ == "__main__":
    unittest.main()
