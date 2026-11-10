"""Helpers for the CLIs: parsing arguments argparse can't declare, terminal prompts, and the editors edit modes open."""

import os
import shutil
from typing import Mapping, Optional


def ui_ask(question: str, choices: Mapping[str, str], default: Optional[str] = None):
    """Asks `question` until the answer is one of `choices`' keys, then returns that answer.

    `choices` maps each answer to a description, which answering "?" (or anything not in `choices`) prints. An empty
    answer means `default`, which is shown in upper case.
    """
    choices_str = "/".join(x.upper() if x == default else x for x in (*choices.keys(), "?"))
    text = f"{question} [{choices_str}]? "

    while True:
        answer = input(text).lower()
        if default and answer == "":
            answer = default

        if answer in choices.keys():
            return answer
        else:
            print("\n".join(f"{choice} - {desc}" for choice, desc in (*choices.items(), ("?", "print help"))))


def get_text_editor():
    """The path to the program named by the `EDITOR` environment variable, or to vi; raises if it isn't found."""
    text_editor = shutil.which(os.getenv("EDITOR", "vi"))
    if not text_editor:
        raise Exception("No suitable EDITOR found.")
    return text_editor


def get_hex_editor():
    """The path to the program named by the `HEXEDITOR` environment variable, or to bvi; raises if it isn't found."""
    hex_editor = shutil.which(os.getenv("HEXEDITOR", "bvi"))
    if not hex_editor:
        raise Exception("No suitable HEXEDITOR found.")
    return hex_editor


def parse_cli_keys_and_values(args: list[str]):
    """Groups CLI arguments by the `--key` before them, e.g. `--a 1 2 --b` gives `{"a": ["1", "2"], "b": []}`.

    Arguments before the first key are dropped.
    """
    keys_and_values: dict[str, list[str | int]] = {}
    key = None
    for arg in args:
        if arg.startswith("--"):
            key = arg.lstrip("-")
            keys_and_values[key] = []
        elif key:
            keys_and_values[key].append(arg)

    # pairs[key] = True  # default to True if no value follows
    return keys_and_values
