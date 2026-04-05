"""
craft_plan.py
-------------
1. Reads the target item at inventory cell [0,0].
2. Scans the rest of the inventory for known crafting mats.
3. Saves a craft_plan.json with target info and mat locations.
4. Executes the chosen crafting strategy.

Usage:
    py craft_plan.py
    py craft_plan.py --countdown 5   # more time to switch to game
    py craft_plan.py --verbose       # print each cell as it's scanned
"""

import json
import re
import time
from pathlib import Path

import click
import pyautogui as _pag
from InquirerPy import inquirer
from InquirerPy.base.control import Choice

from item_parsing.identifier import build_lookup, identify
from item_parsing.parser import parse_item_text
from windows.inventory import cell_center, scan_inventory
from windows.keyboard import hotkey
from windows.mouse import move_to, right_click
from windows.screen import clear_clipboard, read_clipboard


# ---------------------------------------------------------------------------
# File paths & static data
# ---------------------------------------------------------------------------

DATA_DIR     = Path(__file__).parent / "data"
SAVES_DIR    = Path(__file__).parent / "saved_targets"
_MATS_FILE   = Path(__file__).parent / "crafting_mats.json"
_TARGET_FILE = Path(__file__).parent / "target_mods.json"

if not _MATS_FILE.exists():
    raise FileNotFoundError(
        "crafting_mats.json not found. Run  py main_test.py --mats  first."
    )
KNOWN_MATS = json.loads(_MATS_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Orb name sets
# ---------------------------------------------------------------------------

CHAOS_NAMES = {"Chaos Orb", "Greater Chaos Orb", "Perfect Chaos Orb"}
AUG_NAMES   = {"Orb of Augmentation", "Greater Orb of Augmentation", "Perfect Orb of Augmentation"}
ANNUL_NAMES = {"Orb of Annulment"}


# ---------------------------------------------------------------------------
# OrbDispenser
# ---------------------------------------------------------------------------

class OrbDispenser:
    """Tracks remaining orbs across one or more inventory stacks and applies them one at a time."""

    def __init__(self, stacks: list[dict], target_x: int, target_y: int) -> None:
        self._stacks = stacks
        self._tx     = target_x
        self._ty     = target_y
        self.used    = 0

    @property
    def total(self) -> int:
        return sum(s["count"] for s in self._stacks)

    def apply(self) -> bool:
        """Apply one orb to the target cell. Returns False when out of stock."""
        for s in self._stacks:
            if s["count"] > 0:
                cx, cy = cell_center(s["col"], s["row"])
                _apply_orb(cx, cy, self._tx, self._ty)
                s["count"] -= 1
                self.used += 1
                return True
        return False


# ---------------------------------------------------------------------------
# Low-level I/O helpers
# ---------------------------------------------------------------------------

def _apply_orb(cx: int, cy: int, tx: int, ty: int) -> None:
    """Right-click orb stack at (cx, cy) then left-click target at (tx, ty)."""
    move_to(cx, cy, duration=0.1)
    time.sleep(0.05)
    right_click()
    time.sleep(0.05)
    move_to(tx, ty, duration=0.1)
    time.sleep(0.05)
    _pag.click(button="left")
    time.sleep(0.15)


def _read_cell(col: int, row: int, hover_delay: float, copy_delay: float) -> str:
    """Hover over a cell and return the raw Ctrl+C clipboard text."""
    x, y = cell_center(col, row)
    clear_clipboard()
    move_to(x, y, duration=0.0)
    time.sleep(hover_delay)
    hotkey("ctrl", "c")
    time.sleep(copy_delay)
    return read_clipboard().strip()


def _read_target(hover_delay: float, copy_delay: float) -> dict:
    """Parse and return the item sitting at the crafting target cell [0, 0]."""
    return parse_item_text(_read_cell(0, 0, hover_delay, copy_delay))


def _log_item(label: str, item: dict) -> None:
    name = item.get("name") or item.get("base") or "Unknown"
    click.echo(f"  {label:<22s}  →  {name}")
    for line in item["stat_lines"]:
        click.echo(f"                              {line}")


# ---------------------------------------------------------------------------
# Mod-matching helpers
# ---------------------------------------------------------------------------

def _first_match(
    stat_lines: list[str],
    mod_lookup: dict,
    entries:    list[dict],
) -> tuple[dict, dict] | tuple[None, None]:
    """Return (entry, tier) for the first entry whose family and tier match any stat line."""
    for result in identify(stat_lines, mod_lookup):
        for match in result["matched"]:
            for e in entries:
                if match["family"] == e["family"] and match["matched_tier"]["tier"] <= e["min_tier"]:
                    return e, match["matched_tier"]
    return None, None


def _any_match(stat_lines: list[str], mod_lookup: dict, entries: list[dict]) -> bool:
    return _first_match(stat_lines, mod_lookup, entries)[0] is not None


def _combo_win(
    stat_lines: list[str],
    mod_lookup: dict,
    targets:    list[dict],
    acceptable: list[dict],
) -> tuple[dict, dict] | tuple[None, None]:
    """Return (entry, tier) when item has ≥1 target mod AND ≥1 other acceptable mod."""
    target_hits:     list[tuple] = []
    acceptable_hits: list[tuple] = []

    for result in identify(stat_lines, mod_lookup):
        for match in result["matched"]:
            is_target = False
            for t in targets:
                if match["family"] == t["family"] and match["matched_tier"]["tier"] <= t["min_tier"]:
                    target_hits.append((t, match["matched_tier"]))
                    acceptable_hits.append((t, match["matched_tier"]))
                    is_target = True
                    break
            if not is_target:
                for e in acceptable:
                    if match["family"] == e["family"] and match["matched_tier"]["tier"] <= e["min_tier"]:
                        acceptable_hits.append((e, match["matched_tier"]))
                        break

    if len(target_hits) >= 1 and len(acceptable_hits) >= 2:
        return target_hits[0]
    return None, None


# ---------------------------------------------------------------------------
# Fishing engine  (pure — no mouse, no clipboard; all I/O is injected)
# ---------------------------------------------------------------------------

def _run_fishing(
    apply_aug:     "Callable[[], bool]",
    apply_annul:   "Callable[[], bool]",
    read_item:     "Callable[[], dict]",
    is_acceptable: "Callable[[dict], bool]",
    check_win:     "Callable[[dict], tuple]",
) -> bool:
    """
    Phase 1 — find a first acceptable mod:
        aug → acceptable? → phase 2
              bad?        → annul → restart

    Phase 2 — fish for a good 2nd mod:
        aug → win?             → STOP
              bad 2nd mod      → annul 1 → read survivor
                                   still good? → stay in phase 2
                                   gone?       → annul (clean) → back to phase 1
    """
    cycle        = 0
    lucky_streak = 0
    best_streak  = 0
    augs_used    = 0
    annuls_used  = 0

    while True:
        cycle += 1

        # Phase 1 ─────────────────────────────────────────────────────────────
        if not apply_aug():
            click.echo("\nOut of Augmentation Orbs.")
            return False
        augs_used += 1

        item = read_item()
        _log_item(f"Cycle #{cycle:>3}  AUG1", item)

        if not is_acceptable(item):
            click.echo("  ✗ Bad mod — annulling and restarting\n")
            if not apply_annul():
                click.echo("\nOut of Annulment Orbs.")
                return False
            annuls_used  += 1
            lucky_streak  = 0
            continue

        click.echo("  ~ Acceptable mod — fishing for 2nd mod...\n")

        # Phase 2 ─────────────────────────────────────────────────────────────
        while True:
            if not apply_aug():
                click.echo("\nOut of Augmentation Orbs.")
                return False
            augs_used += 1

            item = read_item()
            _log_item(f"Cycle #{cycle:>3}  AUG2", item)

            entry, tier = check_win(item)
            if entry:
                click.echo(
                    f"\n  ✓ WIN  [{entry['type'][:3].upper()} T{tier['tier']}]"
                    f" {entry['stat_template']}"
                )
                click.echo(
                    f"── {augs_used} augs · {annuls_used} annuls"
                    f" · best streak: {best_streak} ──"
                )
                return True

            click.echo("  ✗ Bad 2nd mod — annulling 1...\n")
            if not apply_annul():
                click.echo("\nOut of Annulment Orbs.")
                return False
            annuls_used += 1

            item = read_item()
            _log_item(f"Cycle #{cycle:>3}  POST", item)

            if is_acceptable(item):
                lucky_streak += 1
                best_streak   = max(best_streak, lucky_streak)
                click.echo(
                    f"  ~ Good mod survived"
                    f" (streak: {lucky_streak} / best: {best_streak})"
                    f" — fishing again...\n"
                )
            else:
                lucky_streak = 0
                click.echo("  ✗ Good mod annulled — clearing and restarting...\n")
                if not apply_annul():
                    click.echo("\nOut of Annulment Orbs during cleanup.")
                    return False
                annuls_used += 1
                break  # back to phase 1

    click.echo(
        f"── Done — {augs_used} augs · {annuls_used} annuls"
        f" · best streak: {best_streak} ──"
    )
    return False


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _strategy_chaos(
    found_mats:     list[dict],
    hover_delay:    float,
    copy_delay:     float,
    target_entries: list[dict],
    mod_lookup:     dict,
) -> bool:
    stacks = [m for m in found_mats if m["name"] in CHAOS_NAMES and m["count"] > 0]
    if not stacks:
        click.echo("\nNo Chaos Orbs found in inventory.")
        return False

    total  = sum(m["count"] for m in stacks)
    tx, ty = cell_center(0, 0)
    roll   = 0

    click.echo(f"\n── Chaos Spam  {total} orb(s) ──────────────────────────────────")

    for stack in stacks:
        cx, cy = cell_center(stack["col"], stack["row"])
        move_to(cx, cy, duration=0.1)
        time.sleep(0.05)
        right_click()
        time.sleep(0.05)
        move_to(tx, ty, duration=0.1)
        time.sleep(0.05)
        _pag.keyDown("shift")
        time.sleep(0.05)
        try:
            original_count = stack["count"]
            for _ in range(original_count):
                roll += 1
                stack["count"] -= 1
                _pag.click(button="left")
                time.sleep(0.05)
                item        = _read_target(hover_delay, copy_delay)
                _log_item(f"Roll #{roll:>3}", item)
                entry, tier = _first_match(item["stat_lines"], mod_lookup, target_entries)
                if entry:
                    click.echo(
                        f"\n  ✓ TARGET  [{entry['type'][:3].upper()} T{tier['tier']}]"
                        f" {entry['stat_template']}"
                    )
                    click.echo(f"── Stopped after {roll} rolls ──")
                    return True
                click.echo()
        finally:
            _pag.keyUp("shift")

    click.echo(f"── Done — {roll} rolls, target NOT found ──")
    return False


def _strategy_aug_annul(
    found_mats:     list[dict],
    hover_delay:    float,
    copy_delay:     float,
    target_entries: list[dict],
    mod_lookup:     dict,
) -> bool:
    tx, ty = cell_center(0, 0)
    augs   = OrbDispenser([m for m in found_mats if m["name"] in AUG_NAMES],   tx, ty)
    annuls = OrbDispenser([m for m in found_mats if m["name"] in ANNUL_NAMES], tx, ty)

    if not augs.total:
        click.echo("\nNo Augmentation Orbs found.")
        return False
    if not annuls.total:
        click.echo("\nNo Annulment Orbs found.")
        return False

    click.echo(f"\n── Augment + Annul  {augs.total} augs · {annuls.total} annuls ──────────────")
    cycle = 0

    while True:
        cycle += 1
        if not augs.apply():
            click.echo("\nOut of Augmentation Orbs.")
            return False

        item        = _read_target(hover_delay, copy_delay)
        _log_item(f"Cycle #{cycle:>3}  AUG", item)
        entry, tier = _first_match(item["stat_lines"], mod_lookup, target_entries)

        if entry:
            click.echo(
                f"\n  ✓ TARGET  [{entry['type'][:3].upper()} T{tier['tier']}]"
                f" {entry['stat_template']}"
            )
            click.echo(f"── Stopped after {cycle} cycles ──")
            return True

        click.echo()
        if not annuls.apply():
            click.echo("\nOut of Annulment Orbs.")
            return False
        click.echo(f"  Cycle #{cycle:>3}  ANNUL — restarting...\n")

    click.echo(f"── Done — {cycle} cycles, target NOT found ──")
    return False


def _strategy_aug_annul_5050(
    found_mats:          list[dict],
    hover_delay:         float,
    copy_delay:          float,
    target_entries:      list[dict],
    mod_lookup:          dict,
    fifty_fifty_entries: list[dict],
) -> bool:
    tx, ty     = cell_center(0, 0)
    augs       = OrbDispenser([m for m in found_mats if m["name"] in AUG_NAMES],   tx, ty)
    annuls     = OrbDispenser([m for m in found_mats if m["name"] in ANNUL_NAMES], tx, ty)
    acceptable = list(target_entries) + list(fifty_fifty_entries)

    if not augs.total:
        click.echo("\nNo Augmentation Orbs found.")
        return False
    if not annuls.total:
        click.echo("\nNo Annulment Orbs found.")
        return False
    
    if len(acceptable) < 2:
        click.echo("\nERROR: The 50-50 strategy requires at least 2 mods to 'fish' for.")
        click.echo("  (Either 2+ target mods, or 1 target mod + 50-50 mods).")
        click.echo("  If you only want ONE mod, use the 'Augment + Annul' strategy instead.")
        return False

    click.echo(
        f"\n── Aug + Annul 50-50  {augs.total} augs · {annuls.total} annuls ──────────────"
    )
    click.echo(
        f"  Acceptable: {len(target_entries)} target + {len(fifty_fifty_entries)} 50-50 mod(s)\n"
    )

    return _run_fishing(
        apply_aug     = augs.apply,
        apply_annul   = annuls.apply,
        read_item     = lambda: _read_target(hover_delay, copy_delay),
        is_acceptable = lambda item: _any_match(item["stat_lines"], mod_lookup, acceptable),
        check_win     = lambda item: _combo_win(
            item["stat_lines"], mod_lookup, target_entries, acceptable
        ),
    )


# ---------------------------------------------------------------------------
# Inventory scan
# ---------------------------------------------------------------------------

def _scan_for_mats(
    hover_delay: float,
    copy_delay:  float,
    verbose:     bool,
    target_name: str,
) -> tuple[list[dict], list[dict], list[tuple[int, int]]]:
    """Scan all inventory cells (skipping [0,0]) and return recognised crafting mat entries AND matching bases AND empty slots."""
    found_mats:  list[dict] = []
    found_bases: list[dict] = []

    def on_item(col: int, row: int, text: str) -> None:
        if col == 0 and row == 0:
            return
        item = parse_item_text(text)
        name = item.get("name") or item.get("base") or "Unknown"

        # Check for matching bases
        if name == target_name:
            found_bases.append({
                "col": col,
                "row": row,
                "rarity": item["rarity"],
                "item_level": item["item_level"],
            })
            if verbose:
                click.echo(f"  [{col:02d},{row:02d}] {name}  (extra base found)")
            return

        if name not in KNOWN_MATS:
            if verbose:
                click.echo(f"  [{col:02d},{row:02d}] {name}  (not a known mat)")
            return

        stack = 1
        for line in item["stat_lines"]:
            m = re.match(r"Stack Size:\s*(\d+)", line, re.IGNORECASE)
            if m:
                stack = int(m.group(1))
                break
        found_mats.append({
            "name":        name,
            "col":         col,
            "row":         row,
            "count":       stack,
            "max_stack":   KNOWN_MATS[name].get("max_stack", 1),
            "description": KNOWN_MATS[name].get("description", ""),
        })
        if verbose:
            click.echo(f"  [{col:02d},{row:02d}] {name}  x{stack}")

    res = scan_inventory(on_item=on_item, hover_delay=hover_delay, copy_delay=copy_delay, verbose=False)

    empty_slots: list[tuple[int, int]] = []
    if isinstance(res, dict) and "grid" in res:
        grid = res["grid"]
        for row in range(len(grid)):
            for col in range(len(grid[row])):
                if col == 0 and row == 0:
                    continue
                if grid[row][col] is None:
                    empty_slots.append((col, row))

    return found_mats, found_bases, empty_slots


# ---------------------------------------------------------------------------
# Target-mods loader
# ---------------------------------------------------------------------------

def _list_saves() -> list[Path]:
    """Return all .json files in SAVES_DIR, newest first."""
    if not SAVES_DIR.exists():
        return []
    return sorted(SAVES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _pick_save_to_load() -> dict | None:
    """Interactive fuzzy-select over all saves."""
    saves = _list_saves()
    if not saves:
        return None

    loaded: dict[str, dict] = {}
    choices = []
    for p in saves:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            save_name = data.get("save_name", p.stem) or p.stem
            slug = data.get("slug", "?").replace("_", " ").title()
            choices.append(Choice(value=data, name=f"{save_name:<28s}  {slug}"))
        except: pass

    choices.append(Choice(value=None, name="← Cancel — use current target_mods.json instead"))

    return inquirer.fuzzy(
        message="Load a saved target:",
        choices=choices,
        max_height="80%",
    ).execute()


def _load_target_mods(target_data: dict | None = None) -> tuple[list[dict], list[dict], dict, str]:
    """
    Read target_mods.json OR use provided data, then load the matching modifier DB.
    Returns (target_entries, fifty_fifty_entries, mod_lookup, slug).
    """
    if target_data is None:
        if not _TARGET_FILE.exists():
            click.echo("ERROR: target_mods.json not found. Run  py build_target.py  first.")
            raise SystemExit(1)
        target_data = json.loads(_TARGET_FILE.read_text(encoding="utf-8"))

    slug = target_data.get("slug", "")
    db_path = DATA_DIR / f"{slug.lower()}_modifiers_tiered.json"

    if not db_path.exists():
        click.echo(f"ERROR: modifier DB for '{slug}' not found at {db_path}")
        raise SystemExit(1)

    db_groups = [
        g for g in json.loads(db_path.read_text(encoding="utf-8"))["modifiers"]
        if g.get("section") == "Base Modifiers"
    ]
    mod_lookup = build_lookup(db_groups)

    if target_data.get("mode") == "search":
        target_entries = target_data.get("mods", [])
    else:
        target_entries = target_data.get("prefixes", []) + target_data.get("suffixes", [])

    fifty_fifty_entries = target_data.get("fifty_fifty", [])

    if not target_entries:
        click.echo("ERROR: target_mods.json has no mods defined.")
        raise SystemExit(1)

    return target_entries, fifty_fifty_entries, mod_lookup, slug


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--countdown", default=3, show_default=True,
              help="Seconds before scanning starts.")
@click.option("--verbose",   is_flag=True,
              help="Print the status of every cell during the scan.")
def main(countdown: int, verbose: bool) -> None:
    """Read the target item at [0,0], locate crafting mats, and run the chosen strategy."""

    strategy = inquirer.select(
        message="Select crafting strategy:",
        choices=[
            Choice("chaos",          name="Chaos spam      — roll chaos orbs until a target mod hits"),
            Choice("augment_annul",  name="Augment + Annul — augment → check → annul until target hits"),
            Choice("aug_annul_5050", name="Aug + Annul 50-50 — fish for target + good 2nd mod"),
            Choice(None,             name="Scan only       — identify mats, no auto-clicking"),
        ],
    ).execute()

    # ── Load Target ──────────────────────────────────────────────────────────
    target_data = None
    saves = _list_saves()
    if saves:
        action = inquirer.select(
            message="Which target to use?",
            choices=[
                Choice("current", name="Use current target_mods.json"),
                Choice("load",    name=f"Load a saved target   ({len(saves)} available)"),
            ],
            default="current"
        ).execute()
        if action == "load":
            target_data = _pick_save_to_load()

    target_entries, fifty_fifty_entries, mod_lookup, slug = _load_target_mods(target_data)

    source = "saved_targets/" if target_data else "target_mods.json"
    click.echo(f"Loaded {len(target_entries)} target mod(s) from {source} ({slug}):")
    for t in target_entries:
        click.echo(f"  [{t['type'][:3].upper()} T{t['min_tier']}+] {t['stat_template']}")
    
    if fifty_fifty_entries:
        click.echo(f"Loaded {len(fifty_fifty_entries)} 50-50 mod(s):")
        for t in fifty_fifty_entries:
            click.echo(f"  [{t['type'][:3].upper()} T{t['min_tier']}+] {t['stat_template']}")
    click.echo()

    click.echo("Switch to POE2 and OPEN YOUR INVENTORY.")
    for i in range(countdown, 0, -1):
        click.echo(f"  Starting in {i}…")
        time.sleep(1)
    click.echo()

    hover_delay = 0.05
    copy_delay  = 0.06

    # Step 1 — read the target item at [0, 0]
    target_text = _read_cell(0, 0, hover_delay, copy_delay)
    if not target_text or ("Item Class:" not in target_text and "Rarity:" not in target_text):
        click.echo("ERROR: No item found at cell [0,0]. Put the target item there first.")
        raise SystemExit(1)

    target_item = parse_item_text(target_text)
    target_name = target_item.get("name") or target_item.get("base") or "Unknown"
    click.echo(
        f"Target item : {target_name}"
        f"  ({target_item['item_class']}, {target_item['rarity']})\n"
    )

    # Step 2 — scan inventory for crafting mats, matching bases, and empty slots
    found_mats, found_bases, empty_slots = _scan_for_mats(hover_delay, copy_delay, verbose, target_name)

    if found_bases:
        click.echo(f"\nFound {len(found_bases)} matching base(s) in inventory:")
        for b in found_bases:
            click.echo(f"  [{b['col']:02d},{b['row']:02d}]  {target_name} ({b['rarity']}, ilvl {b['item_level']})")

    click.echo(f"\nFound {len(found_mats)} crafting mat stack(s):\n")
    for m in found_mats:
        click.echo(f"  [{m['col']:02d},{m['row']:02d}]  {m['count']:>3}/{m['max_stack']:<3}  {m['name']}")

    # Step 3 — save plan
    plan = {
        "target": {
            "name":       target_name,
            "item_class": target_item["item_class"],
            "rarity":     target_item["rarity"],
            "item_level": target_item["item_level"],
            "col": 0,
            "row": 0,
        },
        "mats": found_mats,
    }
    out = Path("_craft_plan.json")
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    click.echo(f"\nSaved → {out}")

    # Step 4 — execute strategy loop
    bases_to_craft = [{"col": 0, "row": 0}] + found_bases

    for i, base in enumerate(bases_to_craft):
        if i > 0:
            click.echo(f"\n── Swapping to next base at [{base['col']:02d},{base['row']:02d}] ──")
            if not empty_slots:
                click.echo("ERROR: No empty slots in inventory to park the finished item!")
                break
            ec, er = empty_slots.pop(0)

            tx, ty = cell_center(0, 0)
            ex, ey = cell_center(ec, er)
            nx, ny = cell_center(base["col"], base["row"])
            
            def safe_click(x, y):
                move_to(x, y, duration=0.2)
                time.sleep(0.15)
                _pag.mouseDown(button="left")
                time.sleep(0.05)
                _pag.mouseUp(button="left")
                time.sleep(0.2)

            # Move finished item [0,0] -> empty slot
            safe_click(tx, ty)  # Pick up finished item
            safe_click(ex, ey)  # Place into empty slot
            
            # Move next base -> [0,0]
            safe_click(nx, ny)  # Pick up next base
            safe_click(tx, ty)  # Place into [0,0]
            
            # Wait for UI to settle before next craft
            time.sleep(0.5) 

        success = False
        if strategy == "chaos":
            success = _strategy_chaos(found_mats, hover_delay, copy_delay, target_entries, mod_lookup)
        elif strategy == "augment_annul":
            success = _strategy_aug_annul(found_mats, hover_delay, copy_delay, target_entries, mod_lookup)
        elif strategy == "aug_annul_5050":
            success = _strategy_aug_annul_5050(
                found_mats, hover_delay, copy_delay, target_entries, mod_lookup, fifty_fifty_entries
            )
        elif strategy is None:
            break

        if not success:
            break


if __name__ == "__main__":
    main()
