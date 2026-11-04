import struct
import io
import warnings

from mutagen.mp3 import MP3
from mutagen.id3 import ID3FileType, ID3
from mutagen.aiff import AIFF
from mutagen.id3._frames import GEOB

from serato_tools.utils import logger

# an open track file whose tags can be read and written: an ID3 file (.mp3), an AIFF file, or a file's bare ID3 tags
type ID3File = ID3FileType | ID3 | AIFF
type ID3FileOrPath = str | ID3File


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
    """A value stored in an ID3 file's tags, read from and written to `tagfile`, which tags can share.

    `SeratoGeobTag` is the base for Serato's tags stored as a GEOB frame; `TrackGain` subclasses this directly.
    """

    def __init__(self, file: ID3FileOrPath):
        self.tagfile: ID3File = open_tagfile(file)


class SeratoGeobTag(ID3FileTag):
    """One of Serato's GEOB tags, such as `Serato Markers2`: parsed from, and serialized back to, its frame's bytes."""

    GEOB_KEY: str

    VERSION_FORMAT = "BB"
    VERSION_LEN = struct.calcsize(VERSION_FORMAT)
    type Version = tuple[int, int]
    VERSION: Version

    type FileOrData = ID3FileOrPath | bytes

    def __init__(self, file_or_data: FileOrData):
        self.tagfile: ID3File | None = None  # pyright: ignore[reportIncompatibleVariableOverride]
        self._raw_data: bytes | None = None

        if isinstance(file_or_data, (bytes, bytearray, memoryview)):
            self._raw_data = file_or_data
        else:
            super().__init__(file=file_or_data)
            self._raw_data = self._get_geob()

    def __repr__(self) -> str:
        return str(self._raw_data)

    @property
    def raw_data(self) -> bytes | None:
        """Deprecated, to be removed in the next major version: read-only. Use the tag's own parse, modify, and serialize methods instead of the stored bytes."""
        warnings.warn(
            "raw_data is deprecated and will be removed in version 6, use the tag's own parse, modify, and serialize methods instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._raw_data

    def _require_tagfile(self) -> ID3File:
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
        return b"".join(SeratoGeobTag._readbytes_gen(fp))

    def delete(self):
        was_deleted = self._del_geob() if self.tagfile else False
        # clear _raw_data so a later save() persists the deletion instead of re-tagging the old bytes
        self._raw_data = None
        return was_deleted

    def save(self):
        if not self.tagfile:
            raise Exception("no tagfile, no saving")
        if self._raw_data:
            self._set_geob()
        else:
            self._del_geob()
        self.tagfile.save()


# the classes' names before 5.4.0, kept until the next major version
_DEPRECATED_NAMES = {"SeratoTrack": ID3FileTag, "SeratoTag": SeratoGeobTag}


def __getattr__(name: str):
    if name in _DEPRECATED_NAMES:
        new = _DEPRECATED_NAMES[name]
        warnings.warn(
            f"{name} is deprecated and will be removed in version 6, use {new.__name__} instead",
            DeprecationWarning,
            stacklevel=2,
        )
        return new
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
