import struct
import io
import warnings

from mutagen.mp3 import MP3
from mutagen.id3 import ID3FileType, ID3
from mutagen.aiff import AIFF
from mutagen.id3._frames import GEOB

from serato_tools.utils import logger


def open_tagfile(file: "SeratoTagBase.FileArg") -> "SeratoTagBase.Tagfile":
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


class SeratoTagBase:
    """A value Serato stores in a track file's tags, read from and written to `tagfile`, which tags can share.

    `SeratoGeobTag` is the base for the ones stored as a GEOB frame; `TrackGain` subclasses this directly.
    """

    type Tagfile = ID3FileType | ID3 | AIFF
    type FileArg = str | Tagfile

    def __init__(self, file: FileArg):
        self.tagfile: SeratoTagBase.Tagfile = open_tagfile(file)

    def _get_geob(self, geob_key: str) -> bytes | None:
        geob_key = f"GEOB:{geob_key}"
        try:
            return self.tagfile[geob_key].data
        except KeyError:
            logger.debug(f'File is missing "{geob_key}" tag, not yet set: {self.tagfile.filename}')
            return None

    def _tag_geob(self, geob_key: str, data: bytes):
        self.tagfile[f"GEOB:{geob_key}"] = GEOB(
            encoding=0,
            mime="application/octet-stream",
            desc=geob_key,
            data=data,
        )

    def _write_to_tagfile(self) -> bool:
        """Puts this object's unsaved changes into `tagfile` without saving the file; returns whether it had any.

        Lets `Track` save the changes of every tag sharing one file in a single write. Each tag class implements it.
        """
        # raises rather than returning False, so a tag class that doesn't implement it fails loudly in Track.save()
        # instead of having its changes silently dropped
        raise NotImplementedError(f"{type(self).__name__} doesn't implement _write_to_tagfile")

    def _del_tag(self, key: str):
        """
        Returns True if was deleted, False if no change
        """
        if key in self.tagfile:
            del self.tagfile[key]
            return True
        return False

    def _del_geob(self, geob_key: str):
        """
        Returns True if was deleted, False if no change
        """
        return self._del_tag(f"GEOB:{geob_key}")

    VERSION_FORMAT = "BB"
    VERSION_LEN = struct.calcsize(VERSION_FORMAT)
    type Version = tuple[int, int]

    @staticmethod
    def _check_version(given: bytes, expected: Version):
        given_version: SeratoTagBase.Version = struct.unpack(SeratoTagBase.VERSION_FORMAT, given)
        if given_version != expected:
            raise ValueError(f"""
                ERROR: Untested Serato tag version: {str(given_version)}
                Please contact the developer so we can get it tested and supported!
                We will have you send the file you are trying to parse so we can add support and tests for it.
                We do not want to risk damaging users' library database or crate files!

                Expected version: {str(expected)}
                """)

    @staticmethod
    def _pack_version(version: Version):
        return struct.pack(SeratoTagBase.VERSION_FORMAT, *version)

    @staticmethod
    def _readbytes_gen(fp: io.BytesIO):
        for x in iter(lambda: fp.read(1), b""):
            if x == b"\00":
                break
            yield x

    @staticmethod
    def _readbytes(fp: io.BytesIO):
        return b"".join(SeratoTagBase._readbytes_gen(fp))


class SeratoGeobTag(SeratoTagBase):
    """One of Serato's GEOB tags, such as `Serato Markers2`: parsed from, and serialized back to, its frame's bytes."""

    GEOB_KEY: str
    VERSION: SeratoTagBase.Version

    type FileOrData = SeratoTagBase.FileArg | bytes

    def __init__(self, file_or_data: FileOrData):
        self.tagfile: SeratoTagBase.Tagfile | None = None  # pyright: ignore[reportIncompatibleVariableOverride]
        self._raw_data: bytes | None = None

        if isinstance(file_or_data, (bytes, bytearray, memoryview)):
            self._raw_data = file_or_data
        else:
            super().__init__(file=file_or_data)
            self._raw_data = self._get_geob()
        # the data as the file holds it, so _write_to_tagfile can tell whether there's anything to write
        self._saved_raw_data = self._raw_data

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

    def _get_geob(self):  # pylint: disable=arguments-differ  # pyright: ignore[reportIncompatibleMethodOverride]
        return super()._get_geob(self.GEOB_KEY)

    def _tag_geob(self):  # pylint: disable=arguments-differ  # pyright: ignore[reportIncompatibleMethodOverride]
        if self._raw_data is None:
            return
        return super()._tag_geob(self.GEOB_KEY, self._raw_data)

    def _del_geob(self):  # pylint: disable=arguments-differ  # pyright: ignore[reportIncompatibleMethodOverride]
        return super()._del_geob(self.GEOB_KEY)

    def _check_version(  # pylint: disable=arguments-renamed  # pyright: ignore[reportIncompatibleMethodOverride]
        self, given: bytes
    ):
        return super()._check_version(given, self.VERSION)

    def _pack_version(self):  # pylint: disable=arguments-renamed  # pyright: ignore[reportIncompatibleMethodOverride]
        return super()._pack_version(self.VERSION)

    def delete(self):
        was_deleted = self._del_geob() if self.tagfile else False
        # clear _raw_data so a later save() persists the deletion instead of re-tagging the old bytes
        self._raw_data = None
        return was_deleted

    def _put_in_tagfile(self):
        if self._raw_data:
            self._tag_geob()
        else:
            self._del_geob()
        self._saved_raw_data = self._raw_data

    def _write_to_tagfile(self) -> bool:
        # compared with what was read rather than with the tagfile, so an unchanged tag doesn't restore one that
        # another tag deleted from the shared tagfile (TrackCuesV2 deleting a stale Serato Markers_)
        if self._raw_data == self._saved_raw_data:
            return False
        self._put_in_tagfile()
        return True

    def save(self):
        if not self.tagfile:
            raise Exception("no tagfile, no saving")
        self._put_in_tagfile()
        self.tagfile.save()


# the classes' names before 5.4.0, kept until the next major version
_DEPRECATED_NAMES = {"SeratoTrack": SeratoTagBase, "SeratoTag": SeratoGeobTag}


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
