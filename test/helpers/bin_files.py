"""The database and crate fixtures, and a library folder built from them."""

import os
from dataclasses import dataclass

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate
from serato_tools.utils.bin_file_base import SeratoBinFile

from test.helpers.files import copy_into, mock_files

TEST_DATABASE = "test/data/database_v2_test.bin"
TEST_CRATE = "test/data/TestCrate.crate"
TEST_SMART_CRATE = "test/data/TestSmartCrate.scrate"
# the folder the fixtures' tracks are in, as Serato stores it: from the drive's root, with no drive or leading separator
TRACKS_DIR = "Users/bvand/Music/DJ Tracks"


class MP3_FILENAMES:
    """The track filenames the tests' paths use, most of them tracks in the database and crate fixtures."""

    TRIPPST_ENLIGHTEN = "Tripp St. - Enlighten.mp3"
    ZEDSDEAD_INTHEBEGINNING = "Zeds Dead - In The Beginning.mp3"
    SIR_DEVILS = "SiR - D'Evils.mp3"
    SLAYCUB_VISCERALPLANET = "Slaycub - Visceral Planet.mp3"
    SOULACYBIN_ZEU = "Soulacybin - Zeu.mp3"
    THUNDERCAT_THEMCHANGES = "Thundercat - Them Changes.mp3"


@dataclass
class LibraryFolders:
    """A Serato library folder, holding a copy of the test database, and a music folder for its tracks.

    Constructing one creates both folders and copies the test database into the library folder.
    """

    serato_dir: str
    music_dir: str

    def __post_init__(self):
        mock_files({self.serato_dir: [], self.music_dir: []})
        copy_into(self.serato_dir, TEST_DATABASE, DatabaseV2.FILENAME)

    @property
    def db_file(self) -> str:
        return os.path.join(self.serato_dir, DatabaseV2.FILENAME)

    def music_path(self, name: str) -> str:
        """The path of `name` in the music folder, whether or not it exists."""
        return os.path.join(self.music_dir, name)

    def make_track(self, name: str, content: bytes = b"") -> str:
        """A file of `content` as `name` in the music folder, which `name` may put in a subfolder."""
        path = self.music_path(name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def make_crate(self, name: str, tracks: list[str], crate_class: type[Crate] | type[SmartCrate] = Crate) -> str:
        """A crate, or a smart crate, of `tracks` in the library folder, named as Serato names its file."""
        path = os.path.join(self.serato_dir, crate_class.DIR, name + crate_class.EXTENSION)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        crate = crate_class.new(path)
        crate.add_tracks(tracks)
        crate.save()
        return crate.filepath

    def add_to_database(self, *tracks: str, fields: SeratoBinFile.EntryList | None = None):
        """Adds `tracks` to the database, in order, each with `fields` beside its path."""
        db = DatabaseV2(self.db_file)
        for track in tracks:
            entries = [(DatabaseV2.Fields.FILE_PATH, DatabaseV2.get_relative_path(track)), *(fields or [])]
            # the database has no method that adds a track
            db._entries.append((DatabaseV2.Fields.TRACK, entries))
        db.save()

    def db_track(self, track: str) -> SeratoBinFile.Track:
        """`track`'s entry in the saved database."""
        path = DatabaseV2.get_relative_path(track)
        saved = next((t for t in DatabaseV2(self.db_file).get_tracks() if t.relpath == path), None)
        assert saved is not None, f"{path} isn't in the saved database"
        return saved

    def db_values(self, field: DatabaseV2.Fields) -> dict[str, SeratoBinFile.Value]:
        """Each saved database track's value of `field`, by path, for the tracks that have it."""
        return {t.relpath: t.get_value(field) for t in DatabaseV2(self.db_file).get_tracks() if field in t.fields}
