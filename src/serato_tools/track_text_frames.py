"""A track file's ID3 text frames, such as `TIT2` (title). Needs the `track_tags` extra."""

from mutagen.id3 import Encoding, Frames

from serato_tools.utils.track_tags import ID3FileOrPath, ID3FileTag


class TrackTextFrames(ID3FileTag):
    """A track file's ID3 text frames, such as `TIT2` (title), read and set by frame ID."""

    def __init__(self, file: ID3FileOrPath):
        super().__init__(file)
        self._unsaved: dict[str, str] = {}

    def get(self, frame_id: str) -> str | None:
        """The frame's text, including any not yet saved, or None if the file has no such frame."""
        if frame_id in self._unsaved:
            return self._unsaved[frame_id]
        return self._get_tagged(frame_id)

    def set(self, frame_id: str, text: str):
        """Sets the frame's text in memory, adding the frame if the file has none; call `save()` to write it."""
        if frame_id not in Frames:
            raise ValueError(f"not an ID3 frame ID: {frame_id}")
        self._unsaved[frame_id] = text

    def _get_tagged(self, frame_id: str) -> str | None:
        frame = self.tagfile.get(frame_id)
        # str(), since some frames hold other types (TDRC holds ID3TimeStamps)
        return str(frame.text[0]) if frame is not None and frame.text else None

    def _write_to_tagfile(self) -> bool:
        changed = False
        for frame_id, text in self._unsaved.items():
            if self._get_tagged(frame_id) != text:
                self.tagfile[frame_id] = Frames[frame_id](encoding=Encoding.UTF8, text=[text])
                changed = True
        self._unsaved = {}
        return changed

    def save(self, force: bool = False):
        """Writes the frames set since the file was read or last saved, if any changed, or if `force`."""
        if self._write_to_tagfile() or force:
            self.tagfile.save()
