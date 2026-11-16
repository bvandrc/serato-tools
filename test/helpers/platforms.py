"""Marks for tests that only make sense on one OS family, each skipped on the others."""

import os

import pytest

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows drive letters and backslash separators")
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="POSIX paths")
