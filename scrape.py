"""
scrape.py
---------
Scrape modifier data for any poe2db.tw item class and save to JSON.

Usage:
  python scrape.py                  # default: Talismans (flat + tiered)
  python scrape.py Swords           # scrape Swords
  python scrape.py Axes --flat      # flat modifiers only
  python scrape.py Bows --tiered    # tiered modifiers only (default)
"""

import sys
from pathlib import Path
from scraping.poe2db import fetch_modifiers, fetch_tiered_modifiers, save_json

DATA_DIR = Path(__file__).parent / "data"


def main() -> None:
    args = sys.argv[1:]

    slug   = "Talismans"
    mode   = "both"   # "flat" | "tiered" | "both"

    for arg in args:
        if arg == "--flat":
            mode = "flat"
        elif arg == "--tiered":
            mode = "tiered"
        elif not arg.startswith("--"):
            slug = arg

    DATA_DIR.mkdir(exist_ok=True)
    slug_lower = slug.lower()

    if mode in ("flat", "both"):
        data = fetch_modifiers(slug)
        out = DATA_DIR / f"{slug_lower}_modifiers.json"
        save_json(data, out)

    if mode in ("tiered", "both"):
        data = fetch_tiered_modifiers(slug)
        out = DATA_DIR / f"{slug_lower}_modifiers_tiered.json"
        save_json(data, out)


if __name__ == "__main__":
    main()
