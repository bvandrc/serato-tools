from serato_tools.track_autotags import TrackAutotags

from test.helpers.files import read_bytes


def test_parse():
    tags = TrackAutotags(read_bytes("test/data/track_autotags.bin"))
    assert tags.bpm == 75.0
    assert tags.autogain == -5.074
    assert tags.gaindb == 0.0
