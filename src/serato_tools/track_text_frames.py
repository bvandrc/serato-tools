"""A track file's ID3 text frames, such as `TIT2` (title). Needs the `track_tags` extra."""

from typing import Literal, get_args

from mutagen.id3 import Encoding, Frames

from serato_tools.utils.track_tags import ID3File, ID3FileOrPath, ID3FileTag, del_tag

# the ID3 text frames mutagen implements, but COMM and TXXX, which a description identifies as well as an ID
TextFrameID = Literal[
    "GRP1",
    "MVIN",
    "MVNM",
    "TALB",
    "TBPM",
    "TCAT",
    "TCMP",
    "TCOM",
    "TCON",
    "TCOP",
    "TDAT",
    "TDEN",
    "TDES",
    "TDLY",
    "TDOR",
    "TDRC",
    "TDRL",
    "TDTG",
    "TENC",
    "TEXT",
    "TFLT",
    "TGID",
    "TIME",
    "TIT1",
    "TIT2",
    "TIT3",
    "TKEY",
    "TKWD",
    "TLAN",
    "TLEN",
    "TMED",
    "TMOO",
    "TOAL",
    "TOFN",
    "TOLY",
    "TOPE",
    "TORY",
    "TOWN",
    "TPE1",
    "TPE2",
    "TPE3",
    "TPE4",
    "TPOS",
    "TPRO",
    "TPUB",
    "TRCK",
    "TRDA",
    "TRSN",
    "TRSO",
    "TSIZ",
    "TSO2",
    "TSOA",
    "TSOC",
    "TSOP",
    "TSOT",
    "TSRC",
    "TSSE",
    "TSST",
    "TYER",
]
_TEXT_FRAME_IDS: frozenset[str] = frozenset(get_args(TextFrameID))


def _get_text(tagfile: ID3File, key: str) -> str | None:
    frame = tagfile.get(key)
    # str(), since some frames hold other types (TDRC holds ID3TimeStamps)
    return str(frame.text[0]) if frame is not None and frame.text else None


class TrackTextFrames(ID3FileTag):
    """A track file's ID3 text frames, such as `TIT2` (title), read and set by frame ID.

    Setting a frame to `""` removes it, as Serato does when a tag is cleared.
    """

    def __init__(self, file: ID3FileOrPath):
        super().__init__(file)
        self._unsaved: dict[TextFrameID, str] = {}

    def get(self, frame_id: TextFrameID) -> str | None:
        """The frame's text, including any not yet saved, or None if the file has no such frame."""
        if frame_id in self._unsaved:
            return self._unsaved[frame_id] or None
        return _get_text(self.tagfile, frame_id)

    def set(self, frame_id: TextFrameID, text: str):
        """Sets the frame's text in memory, adding the frame if the file has none; call `save()` to write it."""
        if frame_id not in _TEXT_FRAME_IDS:
            raise ValueError(f"not an ID3 text frame ID: {frame_id}")
        self._unsaved[frame_id] = text

    def _changed_frames(self) -> dict[TextFrameID, str | None]:
        """Each text frame, by ID, whose text would change on saving, with its new text; None removes it."""
        return {
            frame_id: text or None
            for frame_id, text in self._unsaved.items()
            if _get_text(self.tagfile, frame_id) != (text or None)
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
