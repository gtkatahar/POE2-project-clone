"""
scraping/poe2db.py
------------------
Generic scraper for any poe2db.tw item-class modifiers page.

Public API
----------
  fetch_modifiers(item_slug)  → list[dict]
      Fetch and return all flat modifier dicts for the given item slug.
      e.g. fetch_modifiers("Talismans"), fetch_modifiers("Swords")

  fetch_tiered_modifiers(item_slug) → list[dict]
      Same as above but returns modifiers grouped into tiered entries.

  save_json(data, path)
      Convenience: write any object to a JSON file.
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://poe2db.tw/us/{slug}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ModGenerationTypeID → human label
GEN_TYPE: dict[str, str] = {
    "1": "Prefix",
    "2": "Suffix",
    "3": "Unique Implicit",
    "4": "Corrupted",
    "5": "Enchantment",
}

# Raw section keys → friendly display names
SECTION_LABELS: dict[str, str] = {
    "normal":              "Base Modifiers",
    "corrupted":           "Corrupted (Vaal Orb)",
    "desecrated":          "Desecrated Modifiers",
    "master":              "Crafting Bench",
    "essence":             "Essence",
    "perfect_essence":     "Perfect Essence",
    "socketable":          "Rune / Augment",
    "bonded":              "Bonded (Shaman Runes)",
    "enchant":             "Enchantments",
    "delve":               "Fossil (Delve)",
    "incursion":           "Incursion",
    "elder":               "Elder",
    "shaper":              "Shaper",
    "crusader":            "Crusader",
    "redeemer":            "Redeemer",
    "hunter":              "Hunter",
    "warlord":             "Warlord",
    "veiled":              "Veiled",
    "scourgeup":           "Scourge Up",
    "scourgedown":         "Scourge Down",
    "bestiary":            "Bestiary",
    "haunted":             "Haunted",
    "sentinel":            "Sentinel",
    "synthesis":           "Synthesis",
    "synthesis_corrupted": "Synthesis Corrupted",
    "infamous":            "Infamous",
    "searing":             "Searing Exarch",
    "eater":               "Eater of Worlds",
    "warbands":            "Warbands",
    "graft_corrupted":     "Graft Corrupted",
    "gen":                 "Generated Modifiers",
}

_SKIP_KEYS = {"baseitem", "config", "opt"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._parts)).strip()


def _strip_html(raw: str) -> str:
    p = _HTMLStripper()
    p.feed(raw)
    return p.get_text()


def _extract_modsview_json(html: str) -> dict:
    """
    Extract and parse the JSON object passed to `new ModsView(...)` in the
    page source using a bracket-counter (handles nested braces correctly).
    """
    marker = "new ModsView("
    try:
        start = html.index(marker) + len(marker)
    except ValueError:
        raise ValueError("ModsView data not found on this page. Is the slug correct?")

    depth, i, in_str, escape = 0, start, False, False
    while i < len(html):
        c = html[i]
        if escape:
            escape = False
        elif c == "\\" and in_str:
            escape = True
        elif c == '"' and not escape:
            in_str = not in_str
        elif not in_str:
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(html[start : i + 1])
        i += 1
    raise ValueError("Could not find matching closing brace for ModsView JSON.")


def normalize_stat_template(stat: str) -> str:
    """Replace every numeric value / range with # to make a match template."""
    stat = re.sub(r"[+\-]?\(\d+[\u2014\u2013\-]\d+\)", "#", stat)
    stat = re.sub(r"[+\-]?\d+\.?\d*", "#", stat)
    stat = re.sub(r"#\s+%", "#%", stat)
    return re.sub(r"\s+", " ", stat).strip()


def extract_values(stat: str) -> list:
    """
    Pull every numeric token from a stat string.
    Ranges like (112—124) become [112, 124]; plain numbers become ints/floats.
    """
    values: list = []
    for m in re.finditer(r"[+\-]?\s*\((\d+)[\u2014\u2013\-](\d+)\)", stat):
        values.append([int(m.group(1)), int(m.group(2))])
    plain = re.sub(r"[+\-]?\s*\(\d+[\u2014\u2013\-]\d+\)", "", stat)
    for m in re.finditer(r"[+\-]?\d+\.?\d*", plain):
        values.append(float(m.group()) if "." in m.group() else int(m.group()))
    return values


# ---------------------------------------------------------------------------
# Core scraping
# ---------------------------------------------------------------------------

def _fetch_html(slug: str) -> tuple[str, str]:
    """Return (url, html) for the given item slug."""
    url = BASE_URL.format(slug=slug)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return url, resp.text


def _parse_flat_modifiers(raw_data: dict, source_url: str) -> list[dict]:
    """Convert the raw ModsView JSON into a flat list of clean modifier dicts."""
    mods: list[dict] = []
    for key, entries in raw_data.items():
        if key in _SKIP_KEYS or not isinstance(entries, list) or not entries:
            continue
        section_label = SECTION_LABELS.get(key, key)
        for entry in entries:
            gen_id = str(entry.get("ModGenerationTypeID", ""))
            mods.append({
                "section":     section_label,
                "section_key": key,
                "name":        _strip_html(entry.get("Name", "")),
                "type":        GEN_TYPE.get(gen_id, f"Type {gen_id}"),
                "min_ilvl":    int(entry["Level"]) if str(entry.get("Level", "")).isdigit() else entry.get("Level", ""),
                "weight":      int(entry["DropChance"]) if str(entry.get("DropChance", "")).isdigit() else entry.get("DropChance", ""),
                "stat":        _strip_html(entry.get("str", "")),
                "families":    entry.get("ModFamilyList") or [],
                "tags":        entry.get("fossil_no") or [],
                "spawn_tags":  entry.get("spawn_no") or [],
            })
    return mods


def _group_into_tiers(flat_mods: list[dict], source_url: str) -> list[dict]:
    """Group flat modifiers by (section, type, family) and build tiered entries."""
    from collections import defaultdict

    def _group_key(m: dict) -> tuple:
        # Use the normalised stat template as primary key so variants of the same
        # family but different subtypes (e.g. Fire/Cold/Lightning spell levels)
        # are kept as separate groups instead of being merged.
        return (m["section"], m["type"], normalize_stat_template(m["stat"]))

    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for mod in flat_mods:
        buckets[_group_key(mod)].append(mod)

    grouped: list[dict] = []
    for (section, mod_type, family), mods in buckets.items():
        mods_sorted = sorted(mods, key=lambda m: (m.get("min_ilvl") or 0), reverse=True)
        first = mods_sorted[0]
        tiers = [
            {
                "tier":     idx + 1,
                "name":     _strip_html(m["name"]),
                "min_ilvl": m["min_ilvl"],
                "weight":   m["weight"],
                "values":   extract_values(m["stat"]),
            }
            for idx, m in enumerate(mods_sorted)
        ]
        grouped.append({
            "section":       section,
            "section_key":   first["section_key"],
            "type":          mod_type,
            "family":        family,
            "tags":          first["tags"],
            "spawn_tags":    first["spawn_tags"],
            "stat_template": normalize_stat_template(first["stat"]),
            "num_tiers":     len(tiers),
            "tiers":         tiers,
        })

    grouped.sort(key=lambda e: (e["section"], e["type"], e["family"]))
    return grouped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_modifiers(item_slug: str) -> dict:
    """
    Scrape poe2db.tw for the given item class and return a flat modifier dict.

    Parameters
    ----------
    item_slug : str
        The URL slug for the item class, e.g. "Talismans", "Swords", "Axes".

    Returns
    -------
    dict with keys:
        source_url  – the page URL
        item_slug   – the slug used
        total       – total number of modifiers
        modifiers   – list of flat modifier dicts
    """
    print(f"Fetching modifiers for '{item_slug}' …")
    url, html = _fetch_html(item_slug)
    raw = _extract_modsview_json(html)
    mods = _parse_flat_modifiers(raw, url)
    print(f"  {len(mods)} modifiers found.")
    return {
        "source_url": url,
        "item_slug":  item_slug,
        "total":      len(mods),
        "modifiers":  mods,
    }


def fetch_tiered_modifiers(item_slug: str) -> dict:
    """
    Scrape poe2db.tw and return modifiers grouped into tiered entries.

    Parameters
    ----------
    item_slug : str
        E.g. "Talismans", "Swords", "Bows".

    Returns
    -------
    dict with keys:
        source_url    – the page URL
        item_slug     – the slug used
        total_groups  – number of distinct modifier families
        total_mods    – total number of modifier tiers
        modifiers     – list of tiered group dicts
    """
    print(f"Fetching tiered modifiers for '{item_slug}' …")
    url, html = _fetch_html(item_slug)
    raw = _extract_modsview_json(html)
    flat = _parse_flat_modifiers(raw, url)
    tiered = _group_into_tiers(flat, url)
    total_mods = sum(e["num_tiers"] for e in tiered)
    print(f"  {total_mods} tiers across {len(tiered)} modifier groups.")
    return {
        "source_url":   url,
        "item_slug":    item_slug,
        "total_groups": len(tiered),
        "total_mods":   total_mods,
        "modifiers":    tiered,
    }


def fetch_modifier_slugs() -> list[dict]:
    """
    Scrape https://poe2db.tw/us/Modifiers and return every item-class slug
    that has a ModifiersCalc page.

    Returns a list of dicts:
        [{"category": "One Handed Weapons", "name": "Claws", "slug": "Claws"}, ...]
    """
    INDEX_URL = "https://poe2db.tw/us/Modifiers"
    resp = requests.get(INDEX_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    results: list[dict] = []
    current_category = "Unknown"

    # The page uses <h5> / <b> tags for category headers and <a href=...#ModifiersCalc>
    # We walk all tags in document order to capture the category context.
    for tag in soup.find_all(["h5", "b", "a"]):
        if tag.name in ("h5", "b") and tag.get_text(strip=True):
            text = tag.get_text(strip=True)
            # Category headings are short and don't contain "ModifiersCalc"
            if "ModifiersCalc" not in text and len(text) < 60:
                current_category = text
        elif tag.name == "a":
            href = tag.get("href", "")
            if "#ModifiersCalc" in href:
                # e.g. https://poe2db.tw/us/One_Hand_Swords#ModifiersCalc
                slug = href.split("/us/")[-1].replace("#ModifiersCalc", "")
                name = tag.get_text(strip=True)
                results.append({
                    "category": current_category,
                    "name":     name,
                    "slug":     slug,
                })

    return results


def save_json(data: object, path: str | Path) -> None:
    """Write data to a JSON file (UTF-8, pretty-printed)."""
    path = Path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved → '{path.name}'")
