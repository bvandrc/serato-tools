"""Terminal prompts, and the editors they open, for the CLIs' interactive edit modes."""

import ast
import configparser
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


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


def _entry_line(index: int, width: int, entry: object) -> str:
    return f"{index:{width}d}: {entry!r}"


def print_entries(entries: Sequence[object]):
    """Prints each entry's repr, numbered from 0."""
    width = len(str(len(entries)))
    for index, entry in enumerate(entries):
        print(_entry_line(index, width, entry))


def read_sections(contents: str, exactly_one: bool) -> list[tuple[str, dict[str, Any]]]:
    """Each section of INI text `edit_entries` wrote, in sorted order: its name and its fields' values.

    A section's name may be numbered (`[3: CUE]`), which is dropped. Each value is a Python literal. `exactly_one`
    raises ValueError unless there's exactly one section.
    """
    parser = configparser.ConfigParser()
    parser.read_string(contents)
    sections = sorted(parser.sections())
    if exactly_one and len(sections) != 1:
        raise ValueError(f"expected exactly one entry, got {len(sections)}")
    result: list[tuple[str, dict[str, Any]]] = []
    for section in sections:
        number, separator, name = section.partition(": ")
        values = {field: ast.literal_eval(text) for field, text in parser.items(section)}
        result.append((name if separator else number, values))
    return result


@dataclass(frozen=True)
class EntryEditing[E]:
    """How `edit_entries` writes one kind of tag's entries for an editor, and reads them back."""

    section_name: Callable[[E], str]
    """The entry's section name in the text editor, such as `CUE`."""
    field_values: Callable[[E], Iterable[tuple[str, object]]]
    """Each of the entry's fields, and the value to write as a Python literal."""
    from_section: Callable[[str, dict[str, Any]], E]
    """An entry from a section's name and its fields' values; raises if they don't make a valid entry."""
    to_bytes: Callable[[E], bytes]
    """The entry's bytes, for the hex editor."""
    from_bytes: Callable[[E, bytes], E]
    """An entry of the same kind as the one given, from bytes edited in the hex editor."""


_RETRY_CHOICES = {"y": "edit again", "n": "leave unchanged"}


def edit_entries[E](entries: Sequence[E], editing: EntryEditing[E]) -> list[E]:
    """Asks about each entry in turn, opening the text or hex editor to change it, and returns the entries after.

    The text editor shows entries as INI sections with a Python literal per field. Raises if the editors (`EDITOR`
    and `HEXEDITOR`) aren't found.
    """
    editors = {"text": get_text_editor(), "hex": get_hex_editor()}
    width = len(str(len(entries)))
    new_entries: list[E] = []
    action = None
    for index, entry in enumerate(entries):
        if action not in ("q", "_"):
            print(_entry_line(index, width, entry))
            action = ui_ask(
                "Edit this entry",
                {
                    "y": "edit this entry",
                    "n": "do not edit this entry",
                    "q": "quit; do not edit this entry or any of the remaining ones",
                    "a": "edit this entry and all later entries in the file",
                    "b": "edit raw bytes",
                    "r": "remove this entry",
                },
                default="n",
            )

        if action in ("y", "a", "b"):
            to_edit = entries[index:] if action == "a" else entries[index : index + 1]
            results = _edit(to_edit, index, width, action == "b", editing, editors)
            if results is None:
                new_entries.append(entry)
                if action == "a":
                    action = "q"  # the rest are left as they are
            else:
                new_entries.extend(results)
                if action == "a":
                    action = "_"  # the rest were edited along with this one
        elif action not in ("r", "_"):
            new_entries.append(entry)
    return new_entries


def _edit[E](
    entries: Sequence[E], start: int, width: int, as_bytes: bool, editing: EntryEditing[E], editors: dict[str, str]
) -> list[E] | None:
    """The entries after editing them in an editor, until they're valid and confirmed, or None to leave them."""
    while True:
        # closed before the editor opens it, which Windows needs, and deleted when the block ends
        with tempfile.NamedTemporaryFile(delete_on_close=False) as f:
            if as_bytes:
                f.write(editing.to_bytes(entries[0]))
            else:
                for index, entry in enumerate(entries, start=start):
                    name = editing.section_name(entry)
                    # numbered when there's more than one, since configparser needs unique section names
                    f.write(f"[{f'{index:{width}d}: ' if len(entries) > 1 else ''}{name}]\n".encode())
                    for field, value in editing.field_values(entry):
                        f.write(f"{field}: {value!r}\n".encode())
                    f.write(b"\n")
            f.close()
            status = subprocess.call((editors["hex" if as_bytes else "text"], f.name))
            with open(f.name, "rb") as edited:
                output = edited.read()

        if status != 0:
            if ui_ask("Command failed, retry", _RETRY_CHOICES) == "n":
                return None
            continue
        try:
            if as_bytes:
                results = [editing.from_bytes(entries[0], output)]
            else:
                sections = read_sections(output.decode(), exactly_one=len(entries) == 1)
                results = [editing.from_section(name, values) for name, values in sections]
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(str(e))
            if ui_ask("Content seems to be invalid, retry", _RETRY_CHOICES) == "n":
                return None
            continue

        for index, result in enumerate(results, start=start):
            print(_entry_line(index, width, result))
        answer = ui_ask(
            "Above content is valid, save changes",
            {"y": "save current changes", "n": "discard changes", "e": "edit again"},
            default="y",
        )
        if answer == "y":
            return results
        if answer == "n":
            return None
