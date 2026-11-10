"""Helpers for the CLIs.

They parse arguments argparse can't declare, prompt in the terminal, and find the editors edit modes open.
"""

import os
import shutil
from typing import Mapping, Optional


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
    """The path to the program named by the environment variable `env_var`, or to `default`; raises if not found."""
    editor = shutil.which(os.getenv(env_var, default))
    if not editor:
        raise Exception(f"No suitable {env_var} found.")
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
