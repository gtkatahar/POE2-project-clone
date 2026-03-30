"""
item_parsing/parser.py
----------------------
Parse a raw POE2 item clipboard text block into structured data.
"""

import re


_SKIP_PREFIXES = (
    "item class:", "rarity:", "physical damage:", "elemental damage:",
    "fire damage:", "cold damage:", "lightning damage:", "chaos damage:",
    "critical hit chance:", "attacks per second:", "requires:",
    "fractured item", "corrupted", "mirrored", "quality:", "sockets:",
    "note:", "unidentified",
)

_STAT_HINT = re.compile(
    r"[+\-\d%]|increased|reduced|adds|gain|leeche|"
    r"level|chance|damage|speed|life|mana|resist|skill|"
    r"attack|penetrate|conver|regenerat|critical|recover|stun|accuracy",
    re.IGNORECASE,
)


def parse_item_text(text: str) -> dict:
    """
    Parse a raw POE2 clipboard item block.

    Returns a dict with:
        item_class  – e.g. "Talismans"
        rarity      – e.g. "Rare"
        name        – item name line
        base        – base type line
        item_level  – int or None
        stat_lines  – list of modifier/stat lines
    """
    sections = [s.strip() for s in text.strip().split("--------")]
    item: dict = {
        "item_class": "", "rarity": "", "name": "",
        "base": "", "item_level": None, "stat_lines": [],
    }

    if sections:
        header = [l.strip() for l in sections[0].splitlines() if l.strip()]
        non_meta: list[str] = []
        for line in header:
            low = line.lower()
            if low.startswith("item class:"):
                item["item_class"] = line.split(":", 1)[1].strip()
            elif low.startswith("rarity:"):
                item["rarity"] = line.split(":", 1)[1].strip()
            else:
                non_meta.append(line)
        if non_meta:
            item["name"] = non_meta[0]
        if len(non_meta) > 1:
            item["base"] = non_meta[1]

    for section in sections[1:]:
        for line in (l.strip() for l in section.splitlines() if l.strip()):
            low = line.lower()
            if any(low.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if low.startswith("item level:"):
                try:
                    item["item_level"] = int(low.split(":", 1)[1].strip())
                except ValueError:
                    pass
                continue
            if _STAT_HINT.search(line):
                item["stat_lines"].append(line)

    return item
