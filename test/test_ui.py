import unittest
from dataclasses import dataclass
from typing import Any, Callable
from unittest import mock

from serato_tools.utils.ui import EntryEditing, edit_entries, read_sections


@dataclass
class Item:
    value: int


EDITING = EntryEditing[Item](
    section_name=lambda item: "ITEM",
    field_values=lambda item: (("value", item.value),),
    from_section=lambda name, values: Item(values["value"]),
    to_bytes=lambda item: bytes([item.value]),
    from_bytes=lambda item, data: Item(data[0]),
)


class TestCase(unittest.TestCase):
    def edit(self, items: list[Item], answers: list[str], editor: Callable[[str], int]) -> list[Item]:
        """`edit_entries` on `items`, answering its prompts with `answers`, with `editor(path)` as both editors."""

        def call(args: tuple[str, str]) -> int:
            return editor(args[1])

        with (
            mock.patch("builtins.input", side_effect=answers),
            mock.patch("builtins.print"),
            mock.patch("serato_tools.utils.ui.shutil.which", return_value="editor"),
            mock.patch("serato_tools.utils.ui.subprocess.call", side_effect=call),
        ):
            return edit_entries(items, EDITING)

    @staticmethod
    def write(text: str) -> Callable[[str], int]:
        def editor(path: str) -> int:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return 0

        return editor

    def test_edits_keeps_and_removes_entries(self):
        result = self.edit(
            [Item(1), Item(2), Item(3)],
            ["y", "y", "n", "r"],  # edit the first, then save it; keep the second; remove the third
            self.write("[ITEM]\nvalue: 10\n"),
        )
        self.assertEqual(result, [Item(10), Item(2)])

    def test_the_editor_is_given_the_entry(self):
        seen: list[str] = []

        def editor(path: str) -> int:
            with open(path, encoding="utf-8") as f:
                seen.append(f.read())
            return 0

        self.edit([Item(1)], ["y", "y"], editor)
        self.assertEqual(seen, ["[ITEM]\nvalue: 1\n\n"])

    def test_edits_raw_bytes(self):
        def editor(path: str) -> int:
            with open(path, "r+b") as f:
                self.assertEqual(f.read(), b"\x01")
                f.seek(0)
                f.write(b"\x07")
            return 0

        self.assertEqual(self.edit([Item(1)], ["b", "y"], editor), [Item(7)])

    def test_edits_every_later_entry_at_once(self):
        result = self.edit(
            [Item(1), Item(2), Item(3)],
            ["n", "a", "y"],  # keep the first, then edit the rest together, and save them
            self.write("[1: ITEM]\nvalue: 20\n\n[2: ITEM]\nvalue: 30\n"),
        )
        self.assertEqual(result, [Item(1), Item(20), Item(30)])

    def test_leaving_unchanged_keeps_the_entry(self):
        for name, answers, editor in (
            ("editor failed", ["y", "n"], lambda path: 1),
            ("invalid content", ["y", "n"], self.write("not ini")),
            ("discarded", ["y", "n"], self.write("[ITEM]\nvalue: 10\n")),
        ):
            with self.subTest(name):
                # then don't edit the second
                self.assertEqual(self.edit([Item(1), Item(2)], [*answers, "n"], editor), [Item(1), Item(2)])

    def test_read_sections(self):
        sections = read_sections("[2: B]\nx: 'b'\n\n[1: A]\nx: 1\ny: [2]\n", exactly_one=False)
        expected: list[tuple[str, dict[str, Any]]] = [("A", {"x": 1, "y": [2]}), ("B", {"x": "b"})]
        self.assertEqual(sections, expected)
        self.assertEqual(read_sections("[CUE]\nx: 1\n", exactly_one=True), [("CUE", {"x": 1})])
        with self.assertRaises(ValueError):
            read_sections("[1: A]\n[2: B]\n", exactly_one=True)


if __name__ == "__main__":
    unittest.main()
