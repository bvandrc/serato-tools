"""Helpers for the CLIs.

They parse arguments argparse can't declare, prompt in the terminal, find the editors edit modes open, and read a tag
from its audio file or from a file of its own bytes.
"""

import os
import shutil
from typing import TYPE_CHECKING, Mapping, Optional

if TYPE_CHECKING:
    # only for annotations, so this module doesn't need the track_tags extra (mutagen) to import
    from serato_tools.utils.track_tags import SeratoGeobTag


def ui_ask(question: str, choices: Mapping[str, str], default: Optional[str] = None):
    """Asks `question` until the answer is one of `choices`' keys, then returns that answer.

    `choices` maps each answer to a description, which answering "?" (or anything not in `choices`) prints. An empty
    answer means `default`, which is shown in upper case.
    """
    choices_str = "/".join(x.upper() if x == default else x for x in (*choices, "?"))
    text = f"{question} [{choices_str}]? "

    while True:
        answer = input(text).lower() or default
        if answer in choices:
            return answer
        print("\n".join(f"{choice} - {desc}" for choice, desc in (*choices.items(), ("?", "print help"))))


def _find_editor(env_var: str, default: str) -> str:
    """The path to the program named by the environment variable `env_var`, or to `default`.

    Raises FileNotFoundError if it isn't found.
    """
    editor = shutil.which(os.getenv(env_var, default))
    if not editor:
        raise FileNotFoundError(f"no editor found: set {env_var} to one")
    return editor


def get_text_editor():
    """The path to the program named by the `EDITOR` environment variable, or to vi; raises if it isn't found."""
    return _find_editor("EDITOR", "vi")


def get_hex_editor():
    """The path to the program named by the `HEXEDITOR` environment variable, or to bvi; raises if it isn't found."""
    return _find_editor("HEXEDITOR", "bvi")


def parse_cli_keys_and_values(args: list[str]):
    """Groups CLI arguments by the `--key` before them, e.g. `--a 1 2 --b` gives `{"a": ["1", "2"], "b": []}`.

    Arguments before the first key are dropped.
    """
    keys_and_values: dict[str, list[str]] = {}
    key = None
    for arg in args:
        if arg.startswith("--"):
            key = arg.lstrip("-")
            keys_and_values[key] = []
        elif key:
            keys_and_values[key].append(arg)
    return keys_and_values


def open_tag_file_or_data[T: SeratoGeobTag](tag_class: type[T], path: str) -> T:
    """The tag read from `path`, for a CLI: an audio file, or any other file as the tag's own bytes.

    A file of the tag's own bytes is one `serato_tagdump` writes (`Serato Markers2.octet-stream`), or a test fixture.
    """
    # imported here, not at the top, so the module imports without the track_tags extra (mutagen)
    # pylint: disable-next=import-outside-toplevel
    from serato_tools.utils.track_tags import _AIFF_EXTENSIONS, _MP3_EXTENSIONS

    if path.lower().endswith(_MP3_EXTENSIONS + _AIFF_EXTENSIONS):
        return tag_class(path)
    with open(path, "rb") as f:
        return tag_class(f.read())
