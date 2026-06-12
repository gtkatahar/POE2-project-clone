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
    "energy shield:", "armour:", "evasion:", "ward:",
)

_STAT_HINT = re.compile(
    r"[+\-\d%]|increased|reduced|adds|gain|leeche|"
    r"level|chance|damage|speed|life|mana|resist|skill|"
    r"attack|penetrate|conver|regenerat|critical|recover|stun|accuracy",
    re.IGNORECASE,
)

# Matches the "Implicit Modifiers: N" / "Explicit Modifiers: N" header lines.
_MOD_COUNT_RE = re.compile(r"^\s*(implicit|explicit)\s+modifiers:\s*(\d+)\s*$", re.IGNORECASE)

# Matches the "(implicit)" suffix used in live game clipboard text.
_IMPLICIT_SUFFIX_RE = re.compile(r"\s*\(implicit\)\s*$", re.IGNORECASE)

# Matches inline modifier section headers: { Implicit Modifier — Life }, { Prefix Modifier "X" ... }, etc.
_MOD_INLINE_HEADER_RE = re.compile(r"^\s*\{[^}]*\bmodifier\b[^}]*\}\s*$", re.IGNORECASE)

# Line prefixes that are always base implicits, never craftable affixes.
_IMPLICIT_PREFIXES = ("grants skill:",)


def parse_item_text(text: str) -> dict:
    """
    Parse a raw POE2 clipboard item block.

    Returns a dict with:
        item_class           e.g. "Talismans"
        rarity               e.g. "Rare"
        name                 item name line
        base                 base type line
        item_level           int or None
        stat_lines           explicit modifier/stat lines
        implicit_stat_lines  implicit-only modifier/stat lines
    """
    sections = [s.strip() for s in text.strip().split("--------")]
    item: dict = {
        "item_class": "", "rarity": "", "name": "",
        "base": "", "item_level": None,
        "stat_lines": [], "implicit_stat_lines": [],
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

    implicit_remaining: int | None = None
    explicit_remaining: int | None = None
    next_stat_is_implicit: bool | None = None

    for section in sections[1:]:
        for line in (l.strip() for l in section.splitlines() if l.strip()):
            low = line.lower()

            # Handle "Implicit Modifiers: N" / "Explicit Modifiers: N" headers.
            mod_count_match = _MOD_COUNT_RE.match(line)
            if mod_count_match:
                kind, count = mod_count_match.group(1).lower(), int(mod_count_match.group(2))
                if kind == "implicit":
                    implicit_remaining = count
                    explicit_remaining = None
                else:
                    explicit_remaining = count
                    implicit_remaining = None
                continue

            if _MOD_INLINE_HEADER_RE.match(line):
                next_stat_is_implicit = "implicit" in low
                continue

            if any(low.startswith(p) for p in _SKIP_PREFIXES):
                continue
            if low.startswith("item level:"):
                try:
                    item["item_level"] = int(low.split(":", 1)[1].strip())
                except ValueError:
                    pass
                continue
            if low.startswith("stack size:"):
                item["stat_lines"].append(line)
                continue

            if not _STAT_HINT.search(line):
                continue

            # Lines that are always base implicits regardless of formatting.
            if any(line.lower().startswith(p) for p in _IMPLICIT_PREFIXES):
                item["implicit_stat_lines"].append(line)
                continue

            # Handle the live game "(implicit)" suffix notation.
            if _IMPLICIT_SUFFIX_RE.search(line):
                clean = _IMPLICIT_SUFFIX_RE.sub("", line).strip()
                item["implicit_stat_lines"].append(clean)
                continue

            # Route based on inline { ... Modifier ... } header flag.
            if next_stat_is_implicit is True:
                item["implicit_stat_lines"].append(line)
                next_stat_is_implicit = None
                continue
            if next_stat_is_implicit is False:
                item["stat_lines"].append(line)
                next_stat_is_implicit = None
                continue

            # Handle counted implicit/explicit blocks from header notation.
            if implicit_remaining is not None and implicit_remaining > 0:
                item["implicit_stat_lines"].append(line)
                implicit_remaining -= 1
                continue

            if explicit_remaining is not None:
                if explicit_remaining <= 0:
                    continue
                explicit_remaining -= 1

            item["stat_lines"].append(line)

    return item
