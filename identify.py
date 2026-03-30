"""
identify.py
-----------
Identify the modifiers on a POE2 item.

Usage:
  python identify.py myitem.txt            # item from a text file
  python identify.py myitem.txt --slug Swords   # use a different DB slug
  python identify.py                       # uses built-in example item

The tiered modifier DB is loaded from data/<slug>_modifiers_tiered.json.
If it doesn't exist, it is scraped automatically first.
"""

import json
import sys
from pathlib import Path

from scraping.poe2db import fetch_tiered_modifiers, save_json
from item_parsing.parser import parse_item_text
from item_parsing.identifier import build_lookup, identify
from item_parsing.display import print_results, print_simple, build_simple_result

DATA_DIR = Path(__file__).parent / "data"

EXAMPLE_ITEM = """
Item Class: Talismans
Rarity: Rare
Corruption Invocation
Wildwood Talisman
--------
Physical Damage: 67-112
Critical Hit Chance: 8.00%
Attacks per Second: 1.25
--------
Requires: Level 70, 98 Str, 72 Int
--------
Item Level: 84
--------
+7 to Level of all Melee Skills (fractured)
+23% to Critical Damage Bonus
--------
Fractured Item
"""


def _load_or_fetch_db(slug: str) -> dict:
    db_path = DATA_DIR / f"{slug.lower()}_modifiers_tiered.json"
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            return json.load(f)
    print(f"Database for '{slug}' not found — scraping now …")
    DATA_DIR.mkdir(exist_ok=True)
    data = fetch_tiered_modifiers(slug)
    save_json(data, db_path)
    return data


def main() -> None:
    args = sys.argv[1:]
    item_file: str | None = None
    slug = "Talismans"
    simple = False

    i = 0
    while i < len(args):
        if args[i] == "--slug" and i + 1 < len(args):
            slug = args[i + 1]
            i += 2
        elif args[i] == "--simple":
            simple = True
            i += 1
        elif not args[i].startswith("--"):
            item_file = args[i]
            i += 1
        else:
            i += 1

    item_text = EXAMPLE_ITEM
    if item_file:
        path = Path(item_file)
        if not path.exists():
            print(f"ERROR: '{item_file}' not found.")
            sys.exit(1)
        item_text = path.read_text(encoding="utf-8")

    db = _load_or_fetch_db(slug)
    lookup = build_lookup(db["modifiers"])
    print(f"Loaded {db['total_groups']} modifier groups ({db['total_mods']} tiers).\n")

    item = parse_item_text(item_text)
    results = identify(item["stat_lines"], lookup)

    if simple:
        print_simple(item, results)
        result_data = build_simple_result(item, results)
    else:
        print_results(item, results)
        result_data = {"item": item, "results": results}

    out = Path(__file__).parent / "item_mod_result.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    print(f"Result saved → '{out.name}'")


if __name__ == "__main__":
    main()
