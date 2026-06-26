"""
main_test.py
------------
CLI entry point for the POE2 inventory scanner.

Usage:
    py main_test.py                        # scan, full output
    py main_test.py --simple               # scan, compact one-line-per-mod output
    py main_test.py --simple --slug Swords # use a different item database
    py main_test.py --slug Swords          # full output, different DB
"""

import json
import time
from pathlib import Path

import click

from crafting.materials import scan_mat_catalog
from crafting.targets import load_or_fetch_db
from item_parsing.parser import parse_item_text
from item_parsing.identifier import build_lookup, identify
from item_parsing.display import print_results, print_simple, build_simple_result
from windows.inventory import scan_inventory
from paths import MATS


def _load_or_fetch_db(slug: str) -> dict:
    from paths import db_path
    if not db_path(slug).exists():
        click.echo(f"Database for '{slug}' not found — scraping now …")
    return load_or_fetch_db(slug)


_BLUE   = "\033[94m"
_YELLOW = "\033[93m"
_DIM    = "\033[2m"
_WHITE  = "\033[97m"
_RESET  = "\033[0m"


def _cell_symbol(text: str | None) -> str:
    """Return a coloured single character representing the item in a cell."""
    if text is None:
        return f"{_DIM}.{_RESET}"
    low = text.lower()
    if "augmentation" in low:
        return f"{_BLUE}A{_RESET}"
    if "exalted" in low:
        return f"{_YELLOW}E{_RESET}"
    return f"{_WHITE}?{_RESET}"


def _print_grid(grid: list[list[str | None]]) -> None:
    cols = len(grid[0])
    header = "    " + " ".join(f"{c:1}" for c in range(cols))
    click.echo(header)
    click.echo("    " + "-" * (cols * 2 - 1))
    for r, row in enumerate(grid):
        cells = " ".join(_cell_symbol(cell) for cell in row)
        click.echo(f"  {r} | {cells}")
    click.echo("")
    click.echo(f"  {_BLUE}A{_RESET} = Augmentation   "
               f"{_YELLOW}E{_RESET} = Exalted   "
               f"{_DIM}.{_RESET} = Empty   "
               f"{_WHITE}?{_RESET} = Other")

@click.command()
@click.option("--simple",    is_flag=True, help="Compact one-line-per-mod output.")
@click.option("--slug",      default="Talismans", show_default=True,
              help="Item category slug to load the modifier database for.")
@click.option("--countdown", default=3, show_default=True,
              help="Seconds to wait before scanning (time to switch to the game).")
@click.option("--verbose",   is_flag=True, help="Print status of every cell (empty/dupe/found).")
@click.option("--debug",     is_flag=True, help="Dump raw clipboard text for filtered-out cells.")
@click.option("--mats",      is_flag=True, help="Crafting-mat mode: count stacks per item, save crafting_mats.json.")
def main(simple: bool, slug: str, countdown: int, verbose: bool, debug: bool, mats: bool):
    """Scan the POE2 inventory and identify item modifiers."""

    # ------------------------------------------------------------------ mats
    if mats:
        click.echo("Switch to POE2 and OPEN YOUR INVENTORY.")
        for i in range(countdown, 0, -1):
            click.echo(f"  Starting in {i}…")
            time.sleep(1)
        click.echo("Scanning…\n")

        sorted_mats = scan_mat_catalog(verbose=verbose)

        click.echo(f"\n{'='*45}")
        for name, info in sorted_mats.items():
            click.echo(f"  {info['count']:>4}/{info['max_stack']:<4}  {name}")
        click.echo(f"{'='*45}\n")

        MATS.write_text(json.dumps(sorted_mats, indent=2, ensure_ascii=False), encoding="utf-8")
        click.echo(f"Saved → {MATS}")
        return

    # ----------------------------------------------------------- normal scan
    db     = _load_or_fetch_db(slug)
    lookup = build_lookup(db["modifiers"])
    click.echo(f"Loaded {db['total_groups']} modifier groups.\n")

    click.echo("Switch to POE2 and OPEN YOUR INVENTORY.")
    for i in range(countdown, 0, -1):
        click.echo(f"  Starting in {i}…")
        time.sleep(1)
    click.echo("Scanning…\n")

    all_results = []

    def on_item(col: int, row: int, text: str):
        item    = parse_item_text(text)
        matches = identify(item["stat_lines"], lookup)
        name    = item.get("name") or item.get("base") or "Unknown"

        click.echo(f"  [{col:02d},{row:02d}] {name}")

        if simple:
            print_simple(item, matches)
            all_results.append(build_simple_result(item, matches))
        else:
            print_results(item, matches)
            all_results.append({"item": item, "results": matches})

    stats = scan_inventory(on_item=on_item, verbose=verbose, debug=debug)

    click.echo(f"\n{'='*45}")
    click.echo(f"  Cells scanned : {stats['total']}")
    click.echo(f"  Items found   : {stats['found']}")
    click.echo(f"  Empty cells   : {stats['empty']}")
    click.echo(f"{'='*45}\n")

    _print_grid(stats["grid"])


    out = Path("inventory_scan.json")
    out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(f"Results saved → {out}")


if __name__ == "__main__":
    main()
