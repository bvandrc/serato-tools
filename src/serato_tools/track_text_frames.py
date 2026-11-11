"""A track file's ID3 text frames, such as `TIT2` (title), and its comment. Needs the `track_tags` extra."""

from enum import StrEnum, unique

from mutagen.id3 import COMM, ID3, Encoding, Frame, Frames, TextFrame

from serato_tools.utils.track_tags import ID3File, ID3FileOrPath, ID3FileTag, del_tag


def _is_latin1(text: str) -> bool:
    """Whether Latin-1 can hold the text."""
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


def _get_texts_from_frame(frame: Frame) -> list[str]:
    """Every value of a text frame, as text."""
    # str(), since some frames hold other types (TDRC holds ID3TimeStamps); mutagen sets a frame's attributes from its
    # specs at runtime, so its types don't declare `text`
    return [str(text) for text in frame.text]  # pyright: ignore[reportAttributeAccessIssue]


def _get_texts(tagfile: ID3File, key: str) -> list[str]:
    """Every value of the frame `key`, as text, or none if the file has no such frame."""
    frame = tagfile.get(key)
    return _get_texts_from_frame(frame) if frame is not None else []


def _get_text(tagfile: ID3File, key: str) -> str | None:
    """The first value of the frame `key`, as text, or None if the file has no such frame."""
    texts = _get_texts(tagfile, key)
    return texts[0] if texts else None


def _differs(tagfile: ID3File, key: str, text: str | None) -> bool:
    """Whether the frame `key` holds anything but `text` alone, or, for a None or `""` text, exists at all."""
    # compared with all the frame's values, so setting one of several replaces them all
    return _get_texts(tagfile, key) != ([text] if text else [])


def _put_frames(tagfile: ID3File, frames: dict[str, Frame | None]) -> bool:
    """Puts each frame in the file's tags by key, without saving; None removes it. Returns whether there were any."""
    for key, frame in frames.items():
        if frame is None:
            del_tag(tagfile, key)
        else:
            tagfile[key] = frame
    return bool(frames)


class _SeratoComment:
    """The comment Serato shows and writes, in the COMM frames of an open file's tags."""

    # Serato writes a comment to an empty-description COMM frame, and to an "ID3v1 Comment" one too when ID3v1 can
    # hold the text (Latin-1). It removes both when the comment is cleared. It reads the file's first COMM frame,
    # whatever its description or language, except iTunes' own (iTunNORM, iTunSMPB, ...), which hold data rather
    # than a comment.
    LANG = "eng"
    V1_DESC = "ID3v1 Comment"
    KEY = f"COMM::{LANG}"
    V1_KEY = f"COMM:{V1_DESC}:{LANG}"

    def __init__(self, tagfile: ID3File):
        self.tagfile = tagfile

    def keys(self) -> list[str]:
        """The keys of the file's COMM frames that Serato could show, in the file's order: all but iTunes' data."""
        return [key for key in self.tagfile.keys() if key.startswith("COMM:") and not key.startswith("COMM:iTun")]

    def read(self) -> str | None:
        """The comment Serato shows, or None if the file has none."""
        # the file's first, as Serato reads it: mutagen keeps the frames in the file's order
        keys = self.keys()
        return _get_text(self.tagfile, keys[0]) if keys else None

    def changes(self, text: str) -> dict[str, Frame | None]:
        """Each COMM frame, by key, that would change for a comment of `text`, as its new frame; None removes it."""
        # every other frame goes: mutagen saves frames smallest first, so a shorter one would come first in the
        # file, and Serato would show it
        texts: dict[str, str | None] = {key: None for key in self.keys()}
        texts[self.KEY] = text or None
        # the whole text, though Serato cuts its copy to about 29 characters: a cut-off copy is smaller, so mutagen
        # would save it before the main frame, and Serato would show the cut-off one; with the whole text, its longer
        # description keeps it after the main frame
        texts[self.V1_KEY] = text if text and _is_latin1(text) else None
        return {key: self._frame(key, new) for key, new in texts.items() if _differs(self.tagfile, key, new)}

    def _frame(self, key: str, text: str | None) -> COMM | None:
        """The COMM frame Serato writes under `key` for `text`, or None to remove it."""
        if text is None:
            return None
        if key == self.KEY:
            # Latin-1 when it fits, as Serato writes it, and UTF-16 otherwise
            encoding = Encoding.LATIN1 if _is_latin1(text) else Encoding.UTF16
            return COMM(encoding=encoding, lang=self.LANG, desc="", text=[text])
        return COMM(encoding=Encoding.LATIN1, lang=self.LANG, desc=self.V1_DESC, text=[text])

    def write(self, text: str) -> bool:
        """Puts the comment in the frames Serato writes it to, without saving; returns whether anything changed."""
        return _put_frames(self.tagfile, self.changes(text))


class TrackTextFrames(ID3FileTag):
    """A track file's ID3 text frames, such as `TIT2` (title), and its comment (`COMM`), read and set by frame ID.

    Setting a frame to `""` removes it, as Serato does when a tag is cleared.
    """

    @unique
    class Fields(StrEnum):
        """The text frames Serato shows a column for, each the frame's ID, named as `DatabaseV2.Fields` names them."""

        TITLE = "TIT2"
        ARTIST = "TPE1"
        ALBUM = "TALB"
        GENRE = "TCON"
        KEY = "TKEY"
        GROUPING = "TIT1"
        # Serato's "label" column
        PUBLISHER = "TPUB"
        COMPOSER = "TCOM"
        YEAR = "TDRC"
        REMIXER = "TPE4"
        BPM = "TBPM"
        TRACK_NUMBER = "TRCK"
        DISC_NUMBER = "TPOS"
        # the comment Serato shows and writes, rather than a single frame: see `get` and `set`
        COMMENT = "COMM"

    def __init__(self, file: ID3FileOrPath):
        super().__init__(file)
        self._unsaved: dict[str, str] = {}
        self._serato_comment = _SeratoComment(self.tagfile)

    def get(self, frame_id: str) -> str | None:
        """The frame's text, including any not yet saved, or None if the file has no such frame.

        `COMM` gives the comment Serato shows: the file's first comment frame, whatever its description or language,
        except iTunes' data frames (`iTunNORM`, ...).
        """
        if frame_id in self._unsaved:
            return self._unsaved[frame_id] or None
        if frame_id == self.Fields.COMMENT:
            return self._serato_comment.read()
        return _get_text(self.tagfile, frame_id)

    def set(self, frame_id: str, text: str):
        """Sets the frame's text in memory, adding the frame if the file has none; call `save()` to write it.

        `COMM` sets the comment, in the frames Serato writes it to. Every other comment frame is removed, such as one
        another tagger put a label or catalog number in, since Serato would show one that came first in the file
        instead. iTunes' data frames (`iTunNORM`, ...) are kept.
        """
        if frame_id == self.Fields.COMMENT:
            self._unsaved[frame_id] = text
            return
        frame_class = Frames.get(frame_id)
        # only a text frame stored under its bare ID: TXXX is a text frame too, but stored under a key that adds its
        # description, so get() would never find what was written
        frame = frame_class(encoding=Encoding.UTF8, text=[text]) if frame_class else None
        if not isinstance(frame, TextFrame) or frame.HashKey != frame_id:
            raise ValueError(f"not an ID3 text frame stored by its ID: {frame_id}")
        # a frame that can't hold the text drops it, as a timestamp frame (TDRC) does text that isn't a date
        if _get_texts_from_frame(frame) != [text]:
            raise ValueError(f"{frame_id} can't hold {text!r}")
        # loading a file updates its tags to ID3v2.4, which converts (TYER into TDRC, ...) or drops a few older frames,
        # so get() would never find what was written; mutagen lists them only inside that update, so it runs it here
        tags = ID3()
        tags.add(frame)
        tags.update_to_v24()
        if frame_id not in tags:
            raise ValueError(
                f"loading converts {frame_id} into {', '.join(tags)}; set that instead"
                if tags
                else f"loading drops {frame_id}"
            )
        # it rewrites some text too, as TCON's numeric genres ("128" reads as "Club-House"); "" removes the frame
        # instead, so isn't checked
        loaded = _get_texts_from_frame(tags[frame_id])
        if text and loaded != [text]:
            raise ValueError(f"loading reads {frame_id} {text!r} as {loaded}")
        self._unsaved[frame_id] = text

    def read_comment(self) -> str | None:
        """The comment Serato shows for the tags as they are in `tagfile` now, or None if it has none.

        For code that changes the open tags itself, such as a mutagen `EasyID3` key's getter; `get` with
        `Fields.COMMENT` also returns a comment `set` but not yet saved.
        """
        return self._serato_comment.read()

    def write_comment(self, text: str) -> bool:
        """Puts the comment in `tagfile` now, as Serato writes it, without saving; returns whether anything changed.

        For code that saves the open tags itself, such as a mutagen `EasyID3` key's setter. `set` with
        `Fields.COMMENT` instead holds the comment until `save()`; this replaces one set that way and not yet saved.
        """
        self._unsaved.pop(self.Fields.COMMENT, None)
        return self._serato_comment.write(text)

    def _changes(self) -> dict[str, Frame | None]:
        """Each frame, by key, that saving would change, as its new frame; None removes it."""
        changes: dict[str, Frame | None] = {}
        for frame_id, text in self._unsaved.items():
            if frame_id == self.Fields.COMMENT:
                changes.update(self._serato_comment.changes(text))
            elif _differs(self.tagfile, frame_id, text):
                changes[frame_id] = Frames[frame_id](encoding=Encoding.UTF8, text=[text]) if text else None
        return changes

    @property
    def has_changed(self) -> bool:
        """Whether a frame set since the file was read or last saved differs from it, so that saving would write."""
        return bool(self._changes())

    def _write_to_tagfile(self) -> bool:
        changed = _put_frames(self.tagfile, self._changes())
        self._unsaved = {}
        return changed

    def save(self, force: bool = False):
        """Writes the frames set since the file was read or last saved, if any changed, or if `force`."""
        if self._write_to_tagfile() or force:
            self.tagfile.save()
