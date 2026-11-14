"""Helpers shared by the test modules that aren't fixtures (those are in test/conftest.py), a module for each kind.

- `files`: copies of fixtures, and reading files back.
- `bin_files`: the database and crate fixtures.
- `track_tags`: the test mp3 and copies of it with tags removed, and reading its tags. Needs the track_tags extra.
- `cli`: running a console script with a command line.
"""
