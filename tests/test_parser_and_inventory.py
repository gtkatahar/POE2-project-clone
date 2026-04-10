from item_parsing.parser import parse_item_text
from windows.inventory import _is_duplicate_cell


def test_parse_item_text_keeps_stack_size_lines():
    text = """Item Class: Stackable Currency
Rarity: Currency
Orb of Annulment
--------
Stack Size: 7/20
--------
Right click this item then left click a magic item to apply it.
"""

    item = parse_item_text(text)

    assert "Stack Size: 7/20" in item["stat_lines"]


def test_duplicate_cell_detects_adjacent_same_item_only():
    adjacent_grid = [
        ["same", "same", None],
        [None, "other", "other"],
    ]
    separate_grid = [
        ["other", "same", None],
        [None, "other", "same"],
    ]

    assert _is_duplicate_cell(adjacent_grid, 0, 1, "same") is True
    assert _is_duplicate_cell(separate_grid, 1, 0, "same") is False
    assert _is_duplicate_cell(separate_grid, 1, 2, "same") is False


def test_duplicate_cell_does_not_merge_adjacent_stackable_currency():
    stack_text = """Item Class: Stackable Currency
Rarity: Currency
Orb of Augmentation
--------
Stack Size: 10/20
--------
Right click this item then left click a magic item to apply it.
"""
    grid = [[stack_text, stack_text, None]]

    assert _is_duplicate_cell(grid, 0, 1, stack_text) is False
