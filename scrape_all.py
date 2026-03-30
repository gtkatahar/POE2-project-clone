"""
scrape_all.py
-------------
Fetch and save tiered modifier data for every item category listed on
https://poe2db.tw/us/Modifiers.

Usage:
    python scrape_all.py              # skip already-downloaded files
    python scrape_all.py --force      # re-download everything
    python scrape_all.py --list       # print all slugs and exit (no download)
    python scrape_all.py --delay 1.5  # seconds between requests (default 1.0)
"""

import time
from pathlib import Path

import click

from scraping.poe2db import fetch_modifier_slugs, fetch_tiered_modifiers, save_json

DATA_DIR = Path(__file__).parent / "data"


@click.command()
@click.option("--force",  is_flag=True, help="Re-download even if the file already exists.")
@click.option("--list",   "list_only", is_flag=True, help="Print all slugs and exit.")
@click.option("--delay",  default=1.0, show_default=True,
              help="Seconds to wait between requests.")
@click.option("--filter", "category_filter", default=None,
              help="Only scrape slugs whose category contains this string (case-insensitive).")
def main(force: bool, list_only: bool, delay: float, category_filter: str | None):
    """Download modifier DBs for all item categories from poe2db.tw."""

    click.echo("Fetching modifier slug list from poe2db.tw/us/Modifiers …")
    slugs = fetch_modifier_slugs()
    click.echo(f"  Found {len(slugs)} item categories.\n")

    if category_filter:
        slugs = [s for s in slugs if category_filter.lower() in s["category"].lower()]
        click.echo(f"  Filtered to {len(slugs)} categories matching '{category_filter}'.\n")

    if list_only:
        current_cat = None
        for s in slugs:
            if s["category"] != current_cat:
                current_cat = s["category"]
                click.echo(f"\n  {current_cat}")
            out = DATA_DIR / f"{s['slug'].lower()}_modifiers_tiered.json"
            status = "✓" if out.exists() else "·"
            click.echo(f"    {status}  {s['name']:35s}  {s['slug']}")
        return

    DATA_DIR.mkdir(exist_ok=True)
    done, skipped, failed = 0, 0, 0

    for i, entry in enumerate(slugs):
        slug = entry["slug"]
        name = entry["name"]
        out  = DATA_DIR / f"{slug.lower()}_modifiers_tiered.json"

        if out.exists() and not force:
            click.echo(f"  [{i+1:3d}/{len(slugs)}] SKIP  {name} ({slug})")
            skipped += 1
            continue

        try:
            click.echo(f"  [{i+1:3d}/{len(slugs)}]  {name} ({slug}) …")
            data = fetch_tiered_modifiers(slug)
            save_json(data, out)
            done += 1
        except Exception as exc:
            click.echo(f"    ERROR: {exc}", err=True)
            failed += 1

        if i < len(slugs) - 1:
            time.sleep(delay)

    click.echo(f"\nDone: {done} downloaded, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    main()
