"""What the CLIs share: terminal prompts, the editors their edit modes open, and saving a tag back to its file."""

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
        if (answer := input(text).lower() or default) in choices:
            return answer
        print("\n".join(f"{choice} - {desc}" for choice, desc in (*choices.items(), ("?", "print help"))))


def _find_editor(env_var: str, default: str) -> str:
    """The path to the program named by the environment variable `env_var`, or to `default`; raises if not found."""
    if not (editor := shutil.which(os.getenv(env_var, default))):
        raise Exception(f"No suitable {env_var} found.")
    return editor


def get_text_editor():
    """The path to the program named by the `EDITOR` environment variable, or to vi; raises if it isn't found."""
    return _find_editor("EDITOR", "vi")


def get_hex_editor():
    """The path to the program named by the `HEXEDITOR` environment variable, or to bvi; raises if it isn't found."""
    return _find_editor("HEXEDITOR", "bvi")


def save_tag_file_or_data(tag: "SeratoGeobTag", path: str) -> bool:
    """Saves a tag `open_tag_file_or_data` read from `path`, if it changed, and returns whether it wrote.

    A tag read from an audio file is saved to it; one read from the tag's own bytes writes its bytes back to `path`.
    """
    if tag.tagfile:
        return tag.save()
    if not tag.has_changed:
        return False
    with open(path, "wb") as f:
        f.write(tag._raw_data or b"")  # pylint: disable=protected-access
    return True
