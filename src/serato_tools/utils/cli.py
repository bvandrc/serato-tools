"""What the CLIs share: reading and saving a tag's file."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # only for annotations, so this module doesn't need the track_tags extra (mutagen) to import
    from serato_tools.utils.track_tags import SeratoGeobTag


def open_tag_file_or_data[T: SeratoGeobTag](tag_class: type[T], path: str | Path) -> T:
    """The tag read from `path`, for a CLI: an audio file, or any other file as the tag's own bytes.

    A file of the tag's own bytes is one `serato_tagdump` writes (`Serato Markers2.octet-stream`), or a test fixture.
    Write it back with `save_tag_file_or_data`.
    """
    # imported here, not at the top, so the module imports without the track_tags extra (mutagen)
    from serato_tools.utils.track_tags import TAGFILE_EXTENSIONS  # noqa: PLC0415

    path = Path(path)
    if path.suffix.lower() in TAGFILE_EXTENSIONS:
        return tag_class(path)
    return tag_class(path.read_bytes())


def save_tag_file_or_data(tag: "SeratoGeobTag", path: str | Path) -> bool:
    """Saves a tag `open_tag_file_or_data` read from `path`, if it changed, and returns whether it wrote.

    A tag read from an audio file is saved to it; one read from the tag's own bytes writes its bytes back to `path`.
    """
    if tag.tagfile:
        return tag.save()
    if not tag.has_changed:
        return False
    Path(path).write_bytes(tag._raw_data or b"")  # noqa: SLF001
    return True
