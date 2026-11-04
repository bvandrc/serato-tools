import os
import shutil
from typing import Mapping, Optional


def ui_ask(question: str, choices: Mapping[str, str], default: Optional[str] = None):
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
    text_editor = shutil.which(os.getenv("EDITOR", "vi"))
    if not text_editor:
        raise Exception("No suitable EDITOR found.")
    return text_editor


def get_hex_editor():
    hex_editor = shutil.which(os.getenv("HEXEDITOR", "bvi"))
    if not hex_editor:
        raise Exception("No suitable HEXEDITOR found.")
    return hex_editor
