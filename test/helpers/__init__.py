"""Helpers shared by the test modules that aren't fixtures (those are in test/conftest.py), a module for each kind.

- `files`: copies of fixtures, mock files, and reading files back.
- `bin_files`: the database and crate fixtures, and a library folder built from them.
- `track_tags`: the test mp3 and copies of it with tags removed, AIFFs with its tags or none, and reading its tags. Needs the track_tags extra.
- `cli`: running a console script with a command line.
- `platforms`: marks for tests that only make sense on one OS family.
"""
