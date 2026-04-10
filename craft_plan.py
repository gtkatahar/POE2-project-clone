"""
craft_plan.py
-------------
Read the target item at inventory cell [0,0], scan the inventory for crafting
materials and spare bases, save the resulting plan, and optionally execute a
chosen crafting strategy.
"""

import json
import time
from pathlib import Path

import click
from InquirerPy import inquirer
from InquirerPy.base.control import Choice

from crafting.io import is_item_clipboard_text, read_cell, safe_click
from crafting.materials import load_known_mats, scan_for_mats
from crafting.odds import estimate_aug_annul_5050_cost
from crafting.strategies import _run_fishing, strategy_aug_annul, strategy_aug_annul_5050, strategy_chaos
from crafting.targets import TargetConfigError, list_saves, load_save, load_target_mods
from item_parsing.identifier import identify
from item_parsing.parser import parse_item_text
from windows.inventory import cell_center


def _pick_save_to_load() -> dict | None:
    """Interactive fuzzy-select over all saved targets."""
    saves = list_saves()
    if not saves:
        return None

    choices = []
    for path in saves:
        try:
            data = load_save(path)
            save_name = data.get("save_name", path.stem) or path.stem
            slug = data.get("slug", "?").replace("_", " ").title()
            choices.append(Choice(value=data, name=f"{save_name:<28s}  {slug}"))
        except Exception:
            continue

    choices.append(Choice(value=None, name="<- Cancel - use current target_mods.json instead"))
    return inquirer.fuzzy(
        message="Load a saved target:",
        choices=choices,
        max_height="80%",
    ).execute()


def _build_identifier(mod_lookup: dict):
    return lambda stat_lines: identify(stat_lines, mod_lookup)


def _countdown(message: str, seconds: int) -> None:
    """Print a short countdown message."""
    click.echo(message)
    for second in range(seconds, 0, -1):
        click.echo(f"  Starting in {second}...")
        time.sleep(1)
    click.echo()


@click.command()
@click.option("--countdown", default=3, show_default=True, help="Seconds before scanning starts.")
@click.option("--verbose", is_flag=True, help="Print the status of every cell during the scan.")
def main(countdown: int, verbose: bool) -> None:
    """Read the target item at [0,0], locate crafting mats, and run the chosen strategy."""
    try:
        known_mats = load_known_mats()
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    strategy = inquirer.select(
        message="Select crafting strategy:",
        choices=[
            Choice("chaos", name="Chaos spam      - roll chaos orbs until a target mod hits"),
            Choice("augment_annul", name="Augment + Annul - augment -> check -> annul until target hits"),
            Choice("aug_annul_5050", name="Aug + Annul 50-50 - fish for target + good 2nd mod"),
            Choice(None, name="Scan only       - identify mats, no auto-clicking"),
        ],
    ).execute()

    target_entries: list[dict] = []
    fifty_fifty_entries: list[dict] = []
    db_groups: list[dict] = []
    identify_matches = None
    target_data = None
    saves = list_saves()
    if saves:
        action = inquirer.select(
            message="Which target to use?",
            choices=[
                Choice("current", name="Use current target_mods.json"),
                Choice("load", name=f"Load a saved target   ({len(saves)} available)"),
            ],
            default="current",
        ).execute()
        if action == "load":
            target_data = _pick_save_to_load()

    try:
        target_entries, fifty_fifty_entries, mod_lookup, slug, db_groups = load_target_mods(target_data)
    except TargetConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    identify_matches = _build_identifier(mod_lookup)
    source = "saved_targets/" if target_data else "target_mods.json"
    click.echo(f"Loaded {len(target_entries)} target mod(s) from {source} ({slug}):")
    for entry in target_entries:
        click.echo(f"  [{entry['type'][:3].upper()} T{entry['min_tier']}+] {entry['stat_template']}")
    if fifty_fifty_entries:
        click.echo(f"Loaded {len(fifty_fifty_entries)} 50-50 mod(s):")
        for entry in fifty_fifty_entries:
            click.echo(f"  [{entry['type'][:3].upper()} T{entry['min_tier']}+] {entry['stat_template']}")
    click.echo()

    _countdown("Switch to POE2 and OPEN YOUR INVENTORY.", countdown)

    hover_delay = 0.05
    copy_delay = 0.06

    target_text = read_cell(0, 0, hover_delay, copy_delay)
    if not is_item_clipboard_text(target_text):
        raise click.ClickException("No item found at cell [0,0]. Put the target item there first.")

    target_item = parse_item_text(target_text)
    target_name = target_item.get("name") or target_item.get("base") or "Unknown"
    target_base = target_item.get("base") or target_name
    click.echo(f"Target item : {target_name}  ({target_item['item_class']}, {target_item['rarity']})\n")

    if strategy == "aug_annul_5050":
        estimate = estimate_aug_annul_5050_cost(
            item=target_item,
            db_groups=db_groups,
            identify_matches=identify_matches,
            target_entries=target_entries,
            fifty_fifty_entries=fifty_fifty_entries,
        )
        if estimate is not None:
            expected = estimate["expected"]
            click.echo("Expected Average Cost To Stop (weighted estimate):")
            click.echo(f"  Start: {estimate['start_note']}")
            click.echo(
                f"  Avg cost: {expected.transmutes:.2f} transmutes"
                f" | {expected.augs:.2f} augs"
                f" | {expected.annuls:.2f} annuls\n"
            )
            click.echo(f"  Perfect augs: {expected.augs:.2f}\n")
            _countdown("Review the target and expected cost. Inventory scan starts next.", countdown)

    found_mats, found_bases, empty_slots = scan_for_mats(
        known_mats=known_mats,
        hover_delay=hover_delay,
        copy_delay=copy_delay,
        verbose=verbose,
        target_base=target_base,
    )

    if found_bases:
        click.echo(f"\nFound {len(found_bases)} matching base(s) in inventory:")
        for base in found_bases:
            click.echo(
                f"  [{base['col']:02d},{base['row']:02d}]  {base['name']} "
                f"({base['base']}, {base['rarity']}, ilvl {base['item_level']})"
            )

    click.echo(f"\nFound {len(found_mats)} crafting mat stack(s):\n")
    for mat in found_mats:
        click.echo(f"  [{mat['col']:02d},{mat['row']:02d}]  {mat['count']:>3}/{mat['max_stack']:<3}  {mat['name']}")

    plan = {
        "target": {
            "name": target_name,
            "base": target_base,
            "item_class": target_item["item_class"],
            "rarity": target_item["rarity"],
            "item_level": target_item["item_level"],
            "col": 0,
            "row": 0,
        },
        "mats": found_mats,
    }
    out = Path("_craft_plan.json")
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(f"\nSaved -> {out}")

    bases_to_craft = [{"col": 0, "row": 0, "name": target_name, "base": target_base}] + found_bases

    for index, base in enumerate(bases_to_craft):
        if index > 0:
            click.echo(f"\n-- Moving to next base at [{base['col']:02d},{base['row']:02d}] --")
            if not empty_slots:
                click.echo("ERROR: No empty slots in inventory to park the finished item.")
                break

            empty_col, empty_row = empty_slots.pop(0)
            target_x, target_y = cell_center(0, 0)
            empty_x, empty_y = cell_center(empty_col, empty_row)
            next_x, next_y = cell_center(base["col"], base["row"])

            safe_click(target_x, target_y)
            safe_click(empty_x, empty_y)
            safe_click(next_x, next_y)
            safe_click(target_x, target_y)
            time.sleep(0.5)

        success = False
        if strategy == "chaos":
            success = strategy_chaos(found_mats, hover_delay, copy_delay, target_entries, identify_matches)
        elif strategy == "augment_annul":
            success = strategy_aug_annul(found_mats, hover_delay, copy_delay, target_entries, identify_matches)
        elif strategy == "aug_annul_5050":
            success = strategy_aug_annul_5050(
                found_mats,
                hover_delay,
                copy_delay,
                target_entries,
                identify_matches,
                fifty_fifty_entries,
            )
        elif strategy is None:
            break

        if not success:
            break


if __name__ == "__main__":
    main()
