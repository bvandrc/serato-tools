import pytest
from mutagen.id3 import COMM, ID3, TPE1, Encoding, Frame

from serato_tools.track_text_frames import TrackTextFrames


def comments(path: str) -> dict[str, tuple[int, list[str]]]:
    """The COMM frames of the file at `path`, by key, with their encoding and text."""
    tags = ID3(path)
    return {key: (tags[key].encoding, list(tags[key].text)) for key in tags.keys() if key.startswith("COMM")}


def add_frames(path: str, *frames: Frame):
    """Adds `frames` to the file at `path`, and saves it."""
    tags = ID3(path)
    for frame in frames:
        tags.add(frame)
    tags.save(path)


def comment(desc: str, lang: str, *text: str) -> COMM:
    return COMM(encoding=Encoding.LATIN1, lang=lang, desc=desc, text=list(text))


def test_get(mp3: str):
    frames = TrackTextFrames(mp3)
    assert frames.get("TIT2") == "Frequency Shift"
    assert frames.get("TDRC") == "2019", "a timestamp frame read as text"
    assert frames.get("TPE4") is None, "no such frame"


def test_set_writes_on_save(mp3: str):
    frames = TrackTextFrames(mp3)
    assert not frames.has_changed, "as read"
    frames.set("TIT2", "Frequency Shift")
    assert not frames.has_changed, "set to what the file has"

    frames.set("TIT2", "New Title")
    frames.set("TPE4", "A Remixer")
    assert frames.has_changed, "set"
    assert frames.get("TIT2") == "New Title", "unsaved value read back"
    assert TrackTextFrames(mp3).get("TIT2") == "Frequency Shift", "not written until saved"

    frames.save()
    assert not frames.has_changed, "saved"
    saved = TrackTextFrames(mp3)
    assert saved.get("TIT2") == "New Title"
    assert saved.get("TPE4") == "A Remixer", "missing frame added"


def test_fields_name_the_frames_get_and_set_take(mp3: str):
    assert TrackTextFrames(mp3).get(TrackTextFrames.Fields.TITLE) == "Frequency Shift", "TIT2"
    texts = {field: "1" for field in TrackTextFrames.Fields}
    texts.update({TrackTextFrames.Fields.YEAR: "2020", TrackTextFrames.Fields.GENRE: "Dubstep"})
    frames = TrackTextFrames(mp3)
    for field, text in texts.items():
        frames.set(field, text)
    frames.save()

    saved = TrackTextFrames(mp3)
    assert {field: saved.get(field) for field in texts} == texts
    assert {field: saved.get(field.value) for field in texts} == texts, "the same frame as its ID"


# COMM and TXXX are text frames stored under a key with their description; TIPL is stored by its ID but holds pairs,
# not text; APIC, WOAR, and GEOB are neither
@pytest.mark.parametrize("frame_id", ["XXXX", "TXXX", "TIPL", "APIC", "WOAR", "GEOB"])
def test_set_raises_for_a_frame_id_that_isnt_a_text_frame_stored_by_its_id(mp3: str, frame_id: str):
    with pytest.raises(ValueError):
        TrackTextFrames(mp3).set(frame_id, "x")


# loading updates tags to ID3v2.4, which converts or drops these, so what was set would never be read back
@pytest.mark.parametrize("frame_id", ["TYER", "TDAT", "TIME", "TORY", "TRDA", "TSIZ"])
def test_set_raises_for_a_frame_loading_converts_or_drops(mp3: str, frame_id: str):
    with pytest.raises(ValueError, match="loading (converts|drops)"):
        TrackTextFrames(mp3).set(frame_id, "2020")


def test_set_names_the_frame_loading_converts_to(mp3: str):
    with pytest.raises(ValueError, match="into TDRC; set that instead"):
        TrackTextFrames(mp3).set("TYER", "2020")


# loading turns numeric genres into names, so the genre would silently change
@pytest.mark.parametrize("text", ["1", "128", "RX", "(1)Rock"])
def test_set_raises_for_a_genre_loading_rewrites(mp3: str, text: str):
    with pytest.raises(ValueError, match="loading reads TCON"):
        TrackTextFrames(mp3).set("TCON", text)


@pytest.mark.parametrize("text", ["Dubstep", ""])  # "" removes it, so nothing is read back
def test_set_takes_a_genre_loading_keeps(mp3: str, text: str):
    TrackTextFrames(mp3).set("TCON", text)


def test_set_raises_for_text_the_frame_cant_hold(mp3: str):
    frames = TrackTextFrames(mp3)
    with pytest.raises(ValueError):
        frames.set("TDRC", "not a date")
    assert not frames.has_changed, "nothing set"
    frames.set("TDRC", "2020-05-01")
    frames.save()
    assert TrackTextFrames(mp3).get("TDRC") == "2020-05-01"


@pytest.mark.parametrize(
    "frame_id, key, frame",
    [
        ("TPE1", "TPE1", TPE1(encoding=Encoding.UTF8, text=["A", "B"])),
        ("COMM", "COMM::eng", comment("", "eng", "A", "B")),
    ],
    ids=["TPE1", "COMM"],
)
def test_set_replaces_every_value_of_a_multi_valued_frame(mp3: str, frame_id: str, key: str, frame: Frame):
    add_frames(mp3, frame)
    frames = TrackTextFrames(mp3)
    assert frames.get(frame_id) == "A", "the first value"
    frames.set(frame_id, "A")
    assert frames.has_changed, "B would go"
    frames.save()
    assert ID3(mp3)[key].text == ["A"]


def test_set_empty_removes_the_frame(mp3: str):
    # as Serato does when a field is cleared, rather than keeping it empty
    frames = TrackTextFrames(mp3)
    frames.set("TIT2", "")
    assert frames.get("TIT2") is None, "unsaved"
    assert frames.has_changed
    frames.save()
    assert "TIT2" not in ID3(mp3)

    frames = TrackTextFrames(mp3)
    frames.set("TIT2", "")
    assert not frames.has_changed, "already removed"


def test_set_comm_writes_the_frames_serato_does(mp3: str):
    frames = TrackTextFrames(mp3)
    frames.set("COMM", "")
    assert not frames.has_changed, "no comment to remove"

    # Serato writes a Latin-1 comment to both of these, each Latin-1
    frames.set("COMM", "A Comment")
    assert frames.has_changed
    assert frames.get("COMM") == "A Comment", "unsaved value read back"
    frames.save()
    assert comments(mp3) == {
        "COMM::eng": (Encoding.LATIN1, ["A Comment"]),
        "COMM:ID3v1 Comment:eng": (Encoding.LATIN1, ["A Comment"]),
    }
    assert TrackTextFrames(mp3).get("COMM") == "A Comment"
    frames.set("COMM", "A Comment")
    assert not frames.has_changed, "set to what the file has"

    frames.set("COMM", "TEST ★")
    frames.save()
    # all of it, unlike Serato, which cuts it off by sizing the frame for UTF-16 by its character count
    assert comments(mp3) == {"COMM::eng": (Encoding.UTF16, ["TEST ★"])}, "ID3v1 copy removed"

    frames.set("COMM", "")
    assert frames.has_changed
    frames.save()
    assert comments(mp3) == {}, "both frames removed"
    assert TrackTextFrames(mp3).get("COMM") is None


def test_get_comm_is_the_first_comment_frame(mp3: str):
    # Serato shows the file's first COMM frame, whatever its description or language; mutagen saves the smaller first
    add_frames(
        mp3, comment("", "eng", "A comment longer than the other frame"), comment("Songs-DB_Custom1", "eng", "Short")
    )
    assert TrackTextFrames(mp3).get("COMM") == "Short"


def test_get_comm_skips_itunes_frames(mp3: str):
    add_frames(mp3, comment("iTunNORM", "eng", " 00000A2B 00000B1C"))
    assert TrackTextFrames(mp3).get("COMM") is None, "iTunes data, not a comment"


def test_set_comm_removes_every_other_comment_frame_but_itunes(mp3: str):
    add_frames(
        mp3,
        comment("", "\0\0\0", "No language"),
        comment("", "deu", "German"),
        comment("Songs-DB_Custom1", "eng", "Custom"),
        comment("iTunNORM", "eng", " 00000A2B"),
    )
    frames = TrackTextFrames(mp3)
    frames.set("COMM", "A Comment")
    frames.save()
    assert {key: text for key, (_, text) in comments(mp3).items()} == {
        "COMM::eng": ["A Comment"],
        "COMM:ID3v1 Comment:eng": ["A Comment"],
        "COMM:iTunNORM:eng": [" 00000A2B"],
    }, "iTunes' data kept"
    assert TrackTextFrames(mp3).get("COMM") == "A Comment", "now first"


def test_set_comm_has_changed_with_another_comment_frame(mp3: str):
    frames = TrackTextFrames(mp3)
    frames.set("COMM", "A Comment")
    frames.save()
    add_frames(mp3, comment("Songs-DB_Custom1", "eng", "A Label"))
    frames = TrackTextFrames(mp3)
    frames.set("COMM", "A Comment")
    assert frames.has_changed, "the other frame would be removed"


def test_read_and_write_comment_on_open_tags(mp3: str):
    tags = ID3(mp3)
    frames = TrackTextFrames(tags)
    assert frames.write_comment("A Comment")
    assert frames.read_comment() == "A Comment", "in memory, before saving"
    assert not frames.write_comment("A Comment"), "already set"
    assert TrackTextFrames(mp3).get("COMM") is None, "not written until saved"
    tags.save(mp3)
    assert TrackTextFrames(ID3(mp3)).read_comment() == "A Comment"

    tags = ID3(mp3)
    TrackTextFrames(tags).write_comment("")
    tags.save(mp3)
    assert comments(mp3) == {}, "both frames removed"


def test_write_comment_replaces_one_set_and_not_yet_saved(mp3: str):
    frames = TrackTextFrames(mp3)
    frames.set("COMM", "Set")
    frames.write_comment("Written")
    assert frames.get("COMM") == "Written"
    assert not frames.has_changed, "nothing left for save() to write"
    frames.tagfile.save()
    assert TrackTextFrames(mp3).get("COMM") == "Written"
