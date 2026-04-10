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


def test_parse_item_text_splits_implicit_and_explicit_mods():
    text = """Item Class: Helmets
Rarity: Magic
Gale Crest
Strapped Helm
--------
Armour: 49
Item Level: 79
Implicit Modifiers: 2
--------
13% increased Armour
10% increased Cast Speed
--------
Explicit Modifiers: 1
+76 to Armour
"""

    item = parse_item_text(text)

    assert item["implicit_stat_lines"] == [
        "13% increased Armour",
        "10% increased Cast Speed",
    ]
    assert item["stat_lines"] == ["+76 to Armour"]


def test_parse_item_text_grants_skill_treated_as_implicit():
    """'Grants Skill:' lines must never land in stat_lines — they are base implicits
    and would otherwise trigger spurious annuls via needs_seed_roll."""
    text = """Item Class: Wands
Rarity: Magic
Dueling Wand
--------
Requires: Level 90, 157 (unmet) Int
--------
Item Level: 82
--------
Grants Skill: Level 20 Spellslinger
"""

    item = parse_item_text(text)

    assert item["stat_lines"] == []
    assert item["implicit_stat_lines"] == ["Grants Skill: Level 20 Spellslinger"]
    # Confirms needs_seed_roll = lambda item: not item["stat_lines"] returns True.
    assert not item["stat_lines"]


def test_parse_item_text_implicit_suffix_notation():
    """Live game clipboard uses (implicit) suffix, not a header. Those lines must
    go to implicit_stat_lines and NOT stat_lines, so needs_seed_roll works correctly."""
    text = """Item Class: Amulets
Rarity: Magic
Hoarder's Pearlescent Amulet of the Multiverse
--------
Requires: Level 60
--------
Item Level: 82
--------
+10% to all Elemental Resistances (implicit)
--------
17% increased Rarity of Items found
+21 to all Attributes
"""

    item = parse_item_text(text)

    assert item["implicit_stat_lines"] == ["+10% to all Elemental Resistances"]
    assert item["stat_lines"] == [
        "17% increased Rarity of Items found",
        "+21 to all Attributes",
    ]


def test_parse_item_text_implicit_suffix_only_no_explicits():
    """When a magic item has only an implicit and no explicit mods, stat_lines
    must be empty so that needs_seed_roll (lambda item: not item['stat_lines'])
    returns True correctly."""
    text = """Item Class: Amulets
Rarity: Magic
Pearlescent Amulet
--------
Requires: Level 60
--------
Item Level: 82
--------
+10% to all Elemental Resistances (implicit)
"""

    item = parse_item_text(text)

    assert item["implicit_stat_lines"] == ["+10% to all Elemental Resistances"]
    assert item["stat_lines"] == []
    # This is the actual gate: needs_seed_roll = lambda item: not item["stat_lines"]
    assert not item["stat_lines"]


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
