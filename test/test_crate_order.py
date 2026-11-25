import os

import pytest

from serato_tools.crate_order import CrateOrder

from test.helpers.files import copy_into, read_bytes

# Serato's crate order file, trimmed from a real library's: UTF-16-BE with \n line endings, and a smart crate's
# subcrates separated with ≫≫
ORDER_FILE = "test/data/neworder.pref"


@pytest.fixture
def order_file(tmp_dir: str) -> str:
    """A copy of the order fixture, to change and save."""
    return copy_into(tmp_dir, ORDER_FILE)


def saved_lines(path: str) -> list[str]:
    """The file's lines, decoded as Serato writes it, so a byte out of place fails to decode."""
    return read_bytes(path).decode("utf-16-be").split("\n")


def test_crates_are_the_files_crate_names_in_order():
    assert CrateOrder(ORDER_FILE).crates == [
        "Stems",
        "House & Techno",
        "House & Techno≫≫Disco House",
        "Bass",
        "Bass%%Riddim",
        "Bass≫≫Riddim≫≫Wonky Monxxy Riddim",
        "Pop, Rap, Rock, etc.",
        "Sets",
        "Sets%%Riddim TODO",
        "Sets%%Riddim TODO%%Riddim MIX",
        "All Tagged",
    ]


def test_saving_unchanged_writes_the_same_bytes(tmp_dir: str):
    dest = os.path.join(tmp_dir, CrateOrder.FILENAME)
    CrateOrder(ORDER_FILE).save(dest)
    assert read_bytes(dest) == read_bytes(ORDER_FILE), "Serato's line endings kept on every OS"


def test_saving_writes_the_changed_crates_between_the_other_lines(order_file: str):
    order = CrateOrder(order_file)
    order.crates = ["Sets", "New", "Bass"]
    order.save()

    assert saved_lines(order_file) == ["[begin record]", "[crate]Sets", "[crate]New", "[crate]Bass", "[end record]", ""]


def test_crates_added_to_an_order_with_none_go_after_its_first_line(order_file: str):
    order = CrateOrder(order_file)
    order.crates = []
    order.save()
    order = CrateOrder(order_file)
    order.crates = ["House"]
    order.save()

    assert saved_lines(order_file) == ["[begin record]", "[crate]House", "[end record]", ""]
