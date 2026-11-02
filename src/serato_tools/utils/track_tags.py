import struct
import io

from mutagen.mp3 import MP3
from mutagen.id3 import ID3FileType, ID3
from mutagen.aiff import AIFF
from mutagen.id3._frames import GEOB

from serato_tools.utils import logger


class SeratoTrack:
    type Tagfile = ID3FileType | ID3 | AIFF
    type FileArg = str | Tagfile

    def __init__(self, file: FileArg):
        self.tagfile: SeratoTrack.Tagfile

        if isinstance(file, str):
            try:
                if file.lower().endswith(".mp3"):
                    self.tagfile = MP3(file)
                elif file.lower().endswith(".aiff"):
                    self.tagfile = AIFF(file)
            except:
                logger.error(f"Mutagen error for file {file}")
                raise
        else:
            self.tagfile = file

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
        given_version: SeratoTrack.Version = struct.unpack(SeratoTrack.VERSION_FORMAT, given)
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
        return struct.pack(SeratoTrack.VERSION_FORMAT, *version)

    @staticmethod
    def _readbytes_gen(fp: io.BytesIO):
        for x in iter(lambda: fp.read(1), b""):
            if x == b"\00":
                break
            yield x

    @staticmethod
    def _readbytes(fp: io.BytesIO):
        return b"".join(SeratoTrack._readbytes_gen(fp))


class SeratoTag(SeratoTrack):
    GEOB_KEY: str
    VERSION: SeratoTrack.Version

    type FileOrData = SeratoTrack.FileArg | bytes

    def __init__(self, file_or_data: FileOrData):
        self.tagfile: SeratoTrack.Tagfile | None = None  # pyright: ignore[reportIncompatibleVariableOverride]
        self.raw_data: bytes | None = None

        if isinstance(file_or_data, (bytes, bytearray, memoryview)):
            self.raw_data = file_or_data
        else:
            super().__init__(file=file_or_data)
            self.raw_data = self._get_geob()

    def __repr__(self) -> str:
        return str(self.raw_data)

    def _get_geob(self):  # pylint: disable=arguments-differ  # pyright: ignore[reportIncompatibleMethodOverride]
        return super()._get_geob(self.GEOB_KEY)

    def _tag_geob(self):  # pylint: disable=arguments-differ  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.raw_data is None:
            return
        return super()._tag_geob(self.GEOB_KEY, self.raw_data)

    def _del_geob(self):  # pylint: disable=arguments-differ  # pyright: ignore[reportIncompatibleMethodOverride]
        return super()._del_geob(self.GEOB_KEY)

    def _check_version(  # pylint: disable=arguments-renamed  # pyright: ignore[reportIncompatibleMethodOverride]
        self, given: bytes
    ):
        return super()._check_version(given, self.VERSION)

    def _pack_version(self):  # pylint: disable=arguments-renamed  # pyright: ignore[reportIncompatibleMethodOverride]
        return super()._pack_version(self.VERSION)

    def delete(self):
        return self._del_geob()

    def save(self):
        if not self.tagfile:
            raise Exception("no tagfile, no saving")
        if (self._get_geob() != None) and (self.raw_data is None):
            raise ValueError("no data to save")
        if self.raw_data:
            self._tag_geob()
        self.tagfile.save()
