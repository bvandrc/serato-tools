"""Running a console script with a command line."""

import contextlib
import io
from typing import Iterator
from unittest import mock


@contextlib.contextmanager
def cli_args(*argv: str) -> Iterator[io.StringIO]:
    """Runs the block with `argv` as the command line, collecting what it prints to stdout in the given StringIO.

    What it prints to stderr, such as argparse's errors, is dropped.
    """
    stdout = io.StringIO()
    with (
        mock.patch("sys.argv", list(argv)),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        yield stdout
