"""The database and crate fixtures, and recording which Serato bin files a test writes."""

import os
import unittest
from unittest import mock

TEST_DATABASE = "test/data/database_v2_test.bin"
TEST_CRATE = "test/data/TestCrate.crate"
TEST_SMART_CRATE = "test/data/TestSmartCrate.scrate"


def bin_file_writes(testcase: unittest.TestCase) -> list[str]:
    """The name of each Serato bin file (database or crate) written from now until `testcase`'s test ends, in order.

    The returned list fills in as files are written.
    """
    written: list[str] = []

    def record_write(file, *args, **kwargs):
        if "w" in (args[0] if args else kwargs.get("mode", "r")):
            written.append(os.path.basename(file))
        return open(file, *args, **kwargs)  # pylint: disable=unspecified-encoding

    # every way of saving a bin file opens it for writing in its module
    patcher = mock.patch("serato_tools.utils.bin_file_base.open", side_effect=record_write, create=True)
    patcher.start()
    testcase.addCleanup(patcher.stop)
    return written
