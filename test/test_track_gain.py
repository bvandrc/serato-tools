import pytest

from serato_tools.track_gain import TrackGain

from test.helpers.track_tags import TEST_MP3


def test_read():
    tags = TrackGain(TEST_MP3)
    assert tags.gain == 0.0, "gain read from RVA2:SeratoGain frame"
    assert tags.peak == 0.0, "peak read from RVA2:SeratoGain frame"


def test_set_waits_for_save(mp3: str):
    tags = TrackGain(mp3)
    tags.set(gain=-3.5)
    assert TrackGain(mp3).gain == 0.0, "not written until saved"
    tags.save()

    saved = TrackGain(mp3)
    assert saved.gain == pytest.approx(-3.5, abs=0.005), "written on save"
    assert saved.peak == 0.0, "unset peak keeps its previous value"

    saved.set_and_save(gain=-1.5)
    assert TrackGain(mp3).gain == pytest.approx(-1.5, abs=0.005), "set_and_save writes at once"


def test_delete(mp3: str):
    tags = TrackGain(mp3)
    assert tags.delete(), "returns that it had the frame"
    tags.save()

    saved = TrackGain(mp3)
    assert saved.gain is None, "no frame reads as no gain"
    assert saved.peak is None, "no frame reads as no peak"
    with pytest.raises(ValueError):  # needs both values to create the frame
        saved.set_and_save(gain=-3.5)


def test_has_changed():
    tags = TrackGain(TEST_MP3)
    assert not tags.has_changed, "as read"
    tags.set(gain=-3.5)
    assert tags.has_changed, "set"
    tags.set(gain=0.0)
    assert not tags.has_changed, "set back"
    tags.delete()
    assert tags.has_changed, "deleted"
