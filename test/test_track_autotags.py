import unittest

from serato_tools.track_autotags import TrackAutotags

from test.helpers.files import read_bytes


class TestCase(unittest.TestCase):
    def test_parse(self):
        tags = TrackAutotags(read_bytes("test/data/track_autotags.bin"))
        self.assertEqual(tags.bpm, 75.0, "parsed bpm")
        self.assertEqual(tags.autogain, -5.074, "parsed autogain")
        self.assertEqual(tags.gaindb, 0.0, "parsed gaindb")


if __name__ == "__main__":
    unittest.main()
