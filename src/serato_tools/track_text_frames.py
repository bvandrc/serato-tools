"""A track file's ID3 text frames, such as `TIT2` (title). Needs the `track_tags` extra."""

from enum import StrEnum, unique

from mutagen.id3 import ID3, Encoding, Frames, TextFrame

from serato_tools.utils.track_tags import ID3File, ID3FileOrPath, ID3FileTag, del_tag


def _get_texts(tagfile: ID3File, key: str) -> list[str]:
    frame = tagfile.get(key)
    # str(), since some frames hold other types (TDRC holds ID3TimeStamps)
    return [str(text) for text in frame.text] if frame is not None else []


def _get_text(tagfile: ID3File, key: str) -> str | None:
    texts = _get_texts(tagfile, key)
    return texts[0] if texts else None


class TrackTextFrames(ID3FileTag):
    """A track file's ID3 text frames, such as `TIT2` (title), read and set by frame ID.

    Setting a frame to `""` removes it, as Serato does when a tag is cleared.
    """

    @unique
    class Tags(StrEnum):
        """The text frames Serato shows a column for, by Serato's name for each; each is the frame's ID."""

        TITLE = "TIT2"
        ARTIST = "TPE1"
        ALBUM = "TALB"
        GENRE = "TCON"
        KEY = "TKEY"
        GROUPING = "TIT1"
        # Serato's "label"
        PUBLISHER = "TPUB"
        COMPOSER = "TCOM"
        YEAR = "TDRC"
        REMIXER = "TPE4"
        BPM = "TBPM"
        TRACK_NUMBER = "TRCK"
        DISC_NUMBER = "TPOS"

    def __init__(self, file: ID3FileOrPath):
        super().__init__(file)
        self._unsaved: dict[str, str] = {}

    def get(self, frame_id: str) -> str | None:
        """The frame's text, including any not yet saved, or None if the file has no such frame."""
        if frame_id in self._unsaved:
            return self._unsaved[frame_id] or None
        return _get_text(self.tagfile, frame_id)

    def set(self, frame_id: str, text: str):
        """Sets the frame's text in memory, adding the frame if the file has none; call `save()` to write it."""
        frame_class = Frames.get(frame_id)
        # only a text frame stored under its bare ID: COMM and TXXX are text frames too, but stored under a key that
        # adds their description, so get() would never find what was written
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
            # compared with all the frame's values, so setting one of several replaces them all
            if _get_texts(self.tagfile, frame_id) != ([text] if text else [])
        }

    @property
    def has_changed(self) -> bool:
        """Whether a frame set since the file was read or last saved differs from it, so that saving would write."""
        return bool(self._changed_frames())

    def _write_to_tagfile(self) -> bool:
        changed = self._changed_frames()
        for frame_id, text in changed.items():
            if text is None:
                del_tag(self.tagfile, frame_id)
            else:
                self.tagfile[frame_id] = Frames[frame_id](encoding=Encoding.UTF8, text=[text])
        self._unsaved = {}
        return bool(changed)

    def save(self, force: bool = False):
        """Writes the frames set since the file was read or last saved, if any changed, or if `force`."""
        if self._write_to_tagfile() or force:
            self.tagfile.save()
