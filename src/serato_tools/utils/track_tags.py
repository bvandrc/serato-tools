"""The base classes for Serato's tags in a track file, and functions that read and write its ID3 frames."""

import struct
import io
from enum import StrEnum
from typing import ClassVar

from mutagen.mp3 import MP3
from mutagen.id3 import ID3FileType, ID3
from mutagen.aiff import AIFF
from mutagen.id3._frames import GEOB

from serato_tools.utils import logger

# an open track file whose tags can be read and written: an ID3 file (.mp3), an AIFF file, or a file's bare ID3 tags
type ID3File = ID3FileType | ID3 | AIFF
type ID3FileOrPath = str | ID3File


class GeobKeys(StrEnum):
    """The GEOB frame key of each Serato tag in a track file, each tag class's `GEOB_KEY`."""

    AUTOTAGS = "Serato Autotags"
    BEATGRID = "Serato BeatGrid"
    CUES_V1 = "Serato Markers_"
    CUES_V2 = "Serato Markers2"
    WAVEFORM = "Serato Overview"


class MissingTagError(ValueError):
    """A track file without the Serato tag that was needed, such as one Serato hasn't analyzed yet.

    Catch a subclass to handle one tag's absence, without also catching other ValueErrors, such as a corrupt tag.
    """

    GEOB_KEY: ClassVar[GeobKeys]

    def __init__(self, filename: str | None = None):
        """`filename` is the track's, or None for a tag read from bytes."""
        self.filename = filename
        super().__init__(f"no {self.GEOB_KEY} tag" + (f": {filename}" if filename else ""))


class NoCuesError(MissingTagError):
    """A track without a `Serato Markers2` tag, so no cues, such as one that hasn't been analyzed or given any."""

    GEOB_KEY = GeobKeys.CUES_V2


class NoBeatgridError(MissingTagError):
    """A track without a `Serato BeatGrid` tag, such as one Serato hasn't analyzed yet."""

    GEOB_KEY = GeobKeys.BEATGRID


class NoWaveformError(MissingTagError):
    """A track without a `Serato Overview` tag, the waveform, such as one Serato hasn't analyzed yet."""

    GEOB_KEY = GeobKeys.WAVEFORM


def open_tagfile(file: ID3FileOrPath) -> ID3File:
    """Opens the track file at `file` with mutagen, or returns `file` if it's already open.

    Raises ValueError for a file type other than .mp3, .aiff, or .aif.
    """
    if not isinstance(file, str):
        return file
    try:
        if file.lower().endswith(".mp3"):
            return MP3(file)
        if file.lower().endswith((".aiff", ".aif")):
            return AIFF(file)
    except:
        logger.error(f"Mutagen error for file {file}")
        raise
    raise ValueError(f"unsupported file type (only .mp3, .aiff, and .aif are supported): {file}")


def del_tag(tagfile: ID3File, key: str) -> bool:
    """Deletes the file's frame `key` (e.g. `GEOB:Serato Markers_`), in memory; returns whether it had one."""
    if key in tagfile:
        del tagfile[key]
        return True
    return False


def get_geob(tagfile: ID3File, geob_key: str) -> bytes | None:
    """The data of the file's GEOB frame named `geob_key`, or None if it has none."""
    # matched exactly, as mutagen keys frames; whether Serato ever writes a name in another case, or two frames with
    # the same name, isn't known
    try:
        return tagfile[f"GEOB:{geob_key}"].data
    except KeyError:
        logger.debug(f'File is missing "GEOB:{geob_key}" tag, not yet set: {tagfile.filename}')
        return None


def set_geob(tagfile: ID3File, geob_key: str, data: bytes):
    """Sets the file's GEOB frame named `geob_key` to `data`, in memory."""
    tagfile[f"GEOB:{geob_key}"] = GEOB(
        encoding=0,
        mime="application/octet-stream",
        desc=geob_key,
        data=data,
    )


def del_geob(tagfile: ID3File, geob_key: str) -> bool:
    """Deletes the file's GEOB frame named `geob_key`, in memory; returns whether it had one."""
    return del_tag(tagfile, f"GEOB:{geob_key}")


class ID3FileTag:
    """A value stored in an ID3 file's tags, read from and written to `tagfile`, which tags can share."""

    def __init__(self, file: ID3FileOrPath):
        """Opens the track file at `file`, or uses `file` if it's an already open mutagen file."""
        self.tagfile: ID3File = open_tagfile(file)

    @property
    def has_changed(self) -> bool:
        """Whether the tag has changes that saving would write to the file."""
        # raises rather than returning False, as _write_to_tagfile does
        raise NotImplementedError(f"{type(self).__name__} doesn't implement has_changed")

    def _write_to_tagfile(self) -> bool:
        """Puts this tag's unsaved changes into `tagfile` without saving the file; returns whether it had any."""
        # raises rather than returning False, so a tag class that doesn't implement it fails loudly instead of having
        # its changes silently dropped
        raise NotImplementedError(f"{type(self).__name__} doesn't implement _write_to_tagfile")


class SeratoGeobTag(ID3FileTag):
    """One of Serato's GEOB tags, such as `Serato Markers2`: parsed from, and serialized back to, its frame's bytes."""

    GEOB_KEY: GeobKeys

    VERSION_FORMAT = "BB"
    VERSION_LEN = struct.calcsize(VERSION_FORMAT)
    type Version = tuple[int, int]
    VERSION: Version

    type FileOrData = ID3FileOrPath | bytes

    def __init__(self, file_or_data: FileOrData):
        """Reads the tag from a track file, as a path or an open mutagen file, or from the tag's own bytes.

        Read from bytes, the tag has no file, so `save()` raises. A file without the tag leaves its data None.
        """
        self.tagfile: ID3File | None = None  # pyright: ignore[reportIncompatibleVariableOverride]
        self._raw_data: bytes | None = None

        if isinstance(file_or_data, (bytes, bytearray, memoryview)):
            self._raw_data = file_or_data
        else:
            super().__init__(file=file_or_data)
            self._raw_data = self._get_geob()
        # the data the tagfile holds, saved to disk or not, so _write_to_tagfile can tell if there's anything to write
        self._tagged_raw_data = self._raw_data

    def __repr__(self) -> str:
        return str(self._raw_data)

    @property
    def filename(self) -> str | None:
        """The track file's path, or None for a tag read from bytes."""
        return self.tagfile.filename if self.tagfile else None

    def _require_tagfile(self) -> ID3File:
        """The tag's open file; raises if it was read from bytes."""
        if not self.tagfile:
            raise Exception("no tagfile, no saving")
        return self.tagfile

    def _get_geob(self):
        return get_geob(self._require_tagfile(), self.GEOB_KEY)

    def _set_geob(self):
        if self._raw_data is None:
            return
        set_geob(self._require_tagfile(), self.GEOB_KEY, self._raw_data)

    def _del_geob(self):
        return del_geob(self._require_tagfile(), self.GEOB_KEY)

    def _check_version(self, given: bytes):
        """Raises ValueError unless `given`, the tag's packed version bytes, is this class's `VERSION`."""
        given_version: SeratoGeobTag.Version = struct.unpack(SeratoGeobTag.VERSION_FORMAT, given)
        if given_version != self.VERSION:
            raise ValueError(f"""
                ERROR: Untested Serato tag version: {str(given_version)}
                Please contact the developer so we can get it tested and supported!
                We will have you send the file you are trying to parse so we can add support and tests for it.
                We do not want to risk damaging users' library database or crate files!

                Expected version: {str(self.VERSION)}
                """)

    def _pack_version(self):
        return struct.pack(SeratoGeobTag.VERSION_FORMAT, *self.VERSION)

    @staticmethod
    def _readbytes_gen(fp: io.BytesIO):
        for x in iter(lambda: fp.read(1), b""):
            if x == b"\00":
                break
            yield x

    @staticmethod
    def _readbytes(fp: io.BytesIO):
        """Reads past the next null byte, or to the end, and returns what came before it: a null-terminated string."""
        return b"".join(SeratoGeobTag._readbytes_gen(fp))

    def delete(self):
        """Deletes the tag in memory, returning whether the file had it; call `save()` to write the deletion."""
        was_deleted = self._del_geob() if self.tagfile else False
        # clear _raw_data so a later save() persists the deletion instead of re-tagging the old bytes
        self._raw_data = None
        return was_deleted

    def _put_in_tagfile(self):
        """Sets the tag's frame in `tagfile` to its data, or deletes the frame if it has none, without saving."""
        if self._raw_data:
            self._set_geob()
        else:
            self._del_geob()
        self._tagged_raw_data = self._raw_data

    @property
    def has_changed(self) -> bool:
        """Whether the tag's bytes differ from the file's as read or last saved, so that saving would change them.

        For a tag read from bytes, whether they differ from those bytes.
        """
        # compared with what was read rather than with the tagfile, so an unchanged tag doesn't count, or restore, a
        # frame that another tag sharing the tagfile deleted (TrackCuesV2 deleting a stale Serato Markers_)
        return self._raw_data != self._tagged_raw_data

    def _write_to_tagfile(self) -> bool:
        if not self.has_changed:
            return False
        self._put_in_tagfile()
        return True

    def save(self):
        """Writes the tag to the file, whether or not it changed; raises if it was read from bytes."""
        if not self.tagfile:
            raise Exception("no tagfile, no saving")
        self._put_in_tagfile()
        self.tagfile.save()
