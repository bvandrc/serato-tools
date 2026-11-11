"""A track file's ID3 text frames, such as `TIT2` (title), and its comment. Needs the `track_tags` extra."""

from enum import StrEnum, unique

from mutagen.id3 import COMM, ID3, Encoding, Frames, TextFrame

from serato_tools.utils.track_tags import ID3File, ID3FileOrPath, ID3FileTag, del_tag

# Serato writes a comment to an empty-description COMM frame, and to an "ID3v1 Comment" one too when ID3v1 can hold the
# text (Latin-1). It removes both when the comment is cleared. It reads the file's first COMM frame, whatever its
# description or language, except iTunes' own (iTunNORM, iTunSMPB, ...), which hold data rather than a comment.
_COMMENT_LANG = "eng"
_V1_COMMENT_DESC = "ID3v1 Comment"
_COMMENT_KEY = f"COMM::{_COMMENT_LANG}"
_V1_COMMENT_KEY = f"COMM:{_V1_COMMENT_DESC}:{_COMMENT_LANG}"


def _is_latin1(text: str) -> bool:
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


def _get_texts(tagfile: ID3File, key: str) -> list[str]:
    frame = tagfile.get(key)
    # str(), since some frames hold other types (TDRC holds ID3TimeStamps)
    return [str(text) for text in frame.text] if frame is not None else []


def _get_text(tagfile: ID3File, key: str) -> str | None:
    texts = _get_texts(tagfile, key)
    return texts[0] if texts else None


def _comment_keys(tagfile: ID3File) -> list[str]:
    """The keys of the file's COMM frames that Serato could show, in the file's order: all but iTunes' data."""
    return [key for key in tagfile.keys() if key.startswith("COMM:") and not key.startswith("COMM:iTun")]


def _read_comment(tagfile: ID3File) -> str | None:
    # the file's first, as Serato reads it: mutagen keeps the frames in the file's order
    keys = _comment_keys(tagfile)
    return _get_text(tagfile, keys[0]) if keys else None


def _comment_changes(tagfile: ID3File, text: str) -> dict[str, str | None]:
    """Each COMM frame, by key, whose text would change for a comment of `text`, with its new text; None removes it."""
    # every other frame goes: mutagen saves frames smallest first, so a shorter one would come first in the file, and
    # Serato would show it
    texts: dict[str, str | None] = {key: None for key in _comment_keys(tagfile)}
    texts[_COMMENT_KEY] = text or None
    texts[_V1_COMMENT_KEY] = text if text and _is_latin1(text) else None
    return {key: new for key, new in texts.items() if _get_texts(tagfile, key) != ([new] if new else [])}


def _write_comment(tagfile: ID3File, text: str) -> bool:
    """Puts the comment in the frames Serato writes it to, without saving; returns whether anything changed."""
    changes = _comment_changes(tagfile, text)
    for key, new in changes.items():
        if new is None:
            del_tag(tagfile, key)
        elif key == _COMMENT_KEY:
            # Latin-1 when it fits, as Serato writes it, and UTF-16 otherwise
            encoding = Encoding.LATIN1 if _is_latin1(new) else Encoding.UTF16
            tagfile[key] = COMM(encoding=encoding, lang=_COMMENT_LANG, desc="", text=[new])
        else:
            tagfile[key] = COMM(encoding=Encoding.LATIN1, lang=_COMMENT_LANG, desc=_V1_COMMENT_DESC, text=[new])
    return bool(changes)


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

    def get(self, frame_id: str) -> str | None:
        """The frame's text, including any not yet saved, or None if the file has no such frame.

        `COMM` gives the comment Serato shows: the file's first comment frame, whatever its description or language,
        except iTunes' data frames (`iTunNORM`, ...).
        """
        if frame_id in self._unsaved:
            return self._unsaved[frame_id] or None
        return _read_comment(self.tagfile) if frame_id == self.Fields.COMMENT else _get_text(self.tagfile, frame_id)

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
        # a frame that can't hold the text drops it, as a timestamp frame (TDRC) does text that isn't a date; mutagen
        # sets a frame's attributes from its specs at runtime, so its types don't declare `text`
        if [str(t) for t in frame.text] != [text]:  # pyright: ignore[reportAttributeAccessIssue]
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
        loaded = [str(t) for t in tags[frame_id].text]
        if text and loaded != [text]:
            raise ValueError(f"loading reads {frame_id} {text!r} as {loaded}")
        self._unsaved[frame_id] = text

    def _changed_frames(self) -> dict[str, str | None]:
        """Each text frame, by ID, whose text would change on saving, with its new text; None removes it."""
        return {
            frame_id: text or None
            for frame_id, text in self._unsaved.items()
            if frame_id != self.Fields.COMMENT
            # compared with all the frame's values, so setting one of several replaces them all
            and _get_texts(self.tagfile, frame_id) != ([text] if text else [])
        }

    @property
    def has_changed(self) -> bool:
        """Whether a frame set since the file was read or last saved differs from it, so that saving would write."""
        comment = self._unsaved.get(self.Fields.COMMENT)
        return bool(self._changed_frames()) or (comment is not None and bool(_comment_changes(self.tagfile, comment)))

    def _write_to_tagfile(self) -> bool:
        changed = self._changed_frames()
        for frame_id, text in changed.items():
            if text is None:
                del_tag(self.tagfile, frame_id)
            else:
                self.tagfile[frame_id] = Frames[frame_id](encoding=Encoding.UTF8, text=[text])
        comment = self._unsaved.get(self.Fields.COMMENT)
        comment_changed = comment is not None and _write_comment(self.tagfile, comment)
        self._unsaved = {}
        return bool(changed) or comment_changed

    def save(self, force: bool = False):
        """Writes the frames set since the file was read or last saved, if any changed, or if `force`."""
        if self._write_to_tagfile() or force:
            self.tagfile.save()
