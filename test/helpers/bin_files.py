"""The database and crate fixtures."""

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
