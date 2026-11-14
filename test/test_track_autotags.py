import pytest

from serato_tools.track_autotags import TrackAutotags

from test.helpers.files import read_bytes
from test.helpers.track_tags import AUTOTAGS_DATA, copy_mp3_without


def test_parse():
    tags = TrackAutotags(read_bytes(AUTOTAGS_DATA))
    assert tags.bpm == 75.0
    assert tags.autogain == -5.074
    assert tags.gaindb == 0.0


def test_set(mp3: str):
    tags = TrackAutotags(mp3)
    tags.set(bpm=tags.bpm)
    assert not tags.has_changed, "set to what it has"

    tags.set(bpm=128.456)
    autogain = tags.autogain
    tags.save()
    saved = TrackAutotags(mp3)
    assert saved.bpm == 128.46, "stored to 2 decimal places"
    assert saved.autogain == autogain, "values not given left as they were"


def test_set_on_a_track_without_the_tag_needs_every_value(tmp_dir: str):
    path = copy_mp3_without(tmp_dir, TrackAutotags.GEOB_KEY)
    with pytest.raises(ValueError, match="must be set to write the Serato Autotags tag: autogain, gaindb"):
        TrackAutotags(path).set(bpm=120)

    tags = TrackAutotags(path)
    tags.set(bpm=120, autogain=-1.5, gaindb=0.0)
    tags.save()
    saved = TrackAutotags(path)
    assert (saved.bpm, saved.autogain, saved.gaindb) == (120.0, -1.5, 0.0), "the tag added"
