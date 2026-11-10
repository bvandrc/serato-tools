"""A track file's ID3 text frames, such as `TIT2` (title), and its comment. Needs the `track_tags` extra."""

from mutagen.id3 import COMM, Encoding, Frames

from serato_tools.utils.track_tags import ID3FileOrPath, ID3FileTag, del_tag

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


class TrackTextFrames(ID3FileTag):
    """A track file's ID3 text frames, such as `TIT2` (title), read and set by frame ID, and its comment.

    Setting a frame or the comment to `""` removes it, as Serato does when a tag is cleared.
    """

    def __init__(self, file: ID3FileOrPath):
        super().__init__(file)
        self._unsaved: dict[str, str] = {}
        self._unsaved_comment: str | None = None

    def get(self, frame_id: str) -> str | None:
        """The frame's text, including any not yet saved, or None if the file has no such frame."""
        if frame_id in self._unsaved:
            return self._unsaved[frame_id] or None
        return self._get_tagged(frame_id)

    def set(self, frame_id: str, text: str):
        """Sets the frame's text in memory, adding the frame if the file has none; call `save()` to write it."""
        if frame_id not in Frames:
            raise ValueError(f"not an ID3 frame ID: {frame_id}")
        self._unsaved[frame_id] = text

    def get_comment(self) -> str | None:
        """The comment Serato shows, including one not yet saved, or None if the file has none."""
        if self._unsaved_comment is not None:
            return self._unsaved_comment or None
        # the file's first, as Serato reads it: mutagen keeps the frames in the file's order
        keys = self._comment_keys()
        return self._get_tagged(keys[0]) if keys else None

    def set_comment(self, text: str):
        """Sets the comment in memory, in the frames Serato writes it to; call `save()` to write it.

        Every other comment frame is removed, such as one another tagger put a label or catalog number in, since Serato
        would show one that came first in the file instead. iTunes' data frames (`iTunNORM`, ...) are kept.
        """
        self._unsaved_comment = text

    def _comment_keys(self) -> list[str]:
        """The keys of the file's COMM frames that Serato could show, in the file's order: all but iTunes' data."""
        return [key for key in self.tagfile.keys() if key.startswith("COMM:") and not key.startswith("COMM:iTun")]

    def _get_tagged(self, key: str) -> str | None:
        frame = self.tagfile.get(key)
        # str(), since some frames hold other types (TDRC holds ID3TimeStamps)
        return str(frame.text[0]) if frame is not None and frame.text else None

    def _comment_texts(self, text: str) -> dict[str, str | None]:
        """Each comment frame's text for a comment of `text`, None where Serato would have no such frame."""
        # every other frame goes: mutagen saves frames smallest first, so a shorter one would come first in the file, and
        # Serato would show it
        texts: dict[str, str | None] = {key: None for key in self._comment_keys()}
        texts[_COMMENT_KEY] = text or None
        texts[_V1_COMMENT_KEY] = text if text and _is_latin1(text) else None
        return texts

    def _changed_frames(self) -> dict[str, str | None]:
        """Each frame, by key, whose text would change on saving, with its new text; None removes it."""
        changed: dict[str, str | None] = {
            frame_id: text or None
            for frame_id, text in self._unsaved.items()
            if self._get_tagged(frame_id) != (text or None)
        }
        if self._unsaved_comment is not None:
            for key, text in self._comment_texts(self._unsaved_comment).items():
                if self._get_tagged(key) != text:
                    changed[key] = text
        return changed

    @property
    def has_changed(self) -> bool:
        """Whether a frame set since the file was read or last saved differs from it, so that saving would write."""
        return bool(self._changed_frames())

    def _write_to_tagfile(self) -> bool:
        changed = self._changed_frames()
        for key, text in changed.items():
            if text is None:
                del_tag(self.tagfile, key)
            elif key == _COMMENT_KEY:
                # Latin-1 when it fits, as Serato writes it, and UTF-16 otherwise
                encoding = Encoding.LATIN1 if _is_latin1(text) else Encoding.UTF16
                self.tagfile[key] = COMM(encoding=encoding, lang=_COMMENT_LANG, desc="", text=[text])
            elif key == _V1_COMMENT_KEY:
                self.tagfile[key] = COMM(
                    encoding=Encoding.LATIN1, lang=_COMMENT_LANG, desc=_V1_COMMENT_DESC, text=[text]
                )
            else:
                self.tagfile[key] = Frames[key](encoding=Encoding.UTF8, text=[text])
        self._unsaved = {}
        self._unsaved_comment = None
        return bool(changed)

    def save(self, force: bool = False):
        """Writes the frames set since the file was read or last saved, if any changed, or if `force`."""
        if self._write_to_tagfile() or force:
            self.tagfile.save()
