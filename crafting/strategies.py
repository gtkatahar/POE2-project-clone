"""Crafting strategies and matching logic."""

import time
from typing import Callable

import click

from crafting.io import apply_orb_to_target, pick_up_orb_stack, read_target
from crafting.targets import mod_entry_matches
from windows.inventory import cell_center


CHAOS_NAMES = {"Chaos Orb", "Greater Chaos Orb", "Perfect Chaos Orb"}
TRANSMUTE_NAMES = {
    "Orb of Transmutation",
    "Greater Orb of Transmutation",
    "Perfect Orb of Transmutation",
}
AUG_NAMES = {"Orb of Augmentation", "Greater Orb of Augmentation", "Perfect Orb of Augmentation"}
ANNUL_NAMES = {"Orb of Annulment"}


def _release_modifiers() -> None:
    """Best-effort release of common modifiers to avoid sticky keys."""
    import pyautogui as _pag

    for key in (
        "shift",
        "shiftleft",
        "shiftright",
        "ctrl",
        "ctrlleft",
        "ctrlright",
        "alt",
        "altleft",
        "altright",
    ):
        try:
            _pag.keyUp(key)
        except Exception:
            pass


class OrbDispenser:
    """Tracks remaining orbs across one or more inventory stacks and applies them one at a time."""

    def __init__(self, stacks: list[dict], target_x: int, target_y: int) -> None:
        self._stacks = stacks
        self._tx = target_x
        self._ty = target_y
        self.used = 0

    @property
    def total(self) -> int:
        return sum(stack["count"] for stack in self._stacks)

    def apply(self) -> bool:
        """Apply one orb to the target cell. Returns False when out of stock."""
        for stack in self._stacks:
            if stack["count"] > 0:
                cx, cy = cell_center(stack["col"], stack["row"])
                apply_orb_to_target(cx, cy, self._tx, self._ty)
                stack["count"] -= 1
                self.used += 1
                return True
        return False


def _log_item(label: str, item: dict) -> None:
    name = item.get("name") or item.get("base") or "Unknown"
    rarity = item.get("rarity") or "Unknown"
    click.echo(f"  {label:<22s}  ->  [{rarity}] {name}")
    for line in item.get("implicit_stat_lines", []):
        click.echo(f"                              (implicit) {line}")
    for line in item["stat_lines"]:
        click.echo(f"                              {line}")


def _first_match(
    stat_lines: list[str],
    identify_matches,
    entries: list[dict],
) -> tuple[dict, dict] | tuple[None, None]:
    """Return (entry, tier) for the first entry whose family and tier match any stat line."""
    for result in identify_matches(stat_lines):
        for match in result["matched"]:
            for entry in entries:
                if mod_entry_matches(match, entry):
                    return entry, match["matched_tier"]
    return None, None


def _any_match(stat_lines: list[str], identify_matches, entries: list[dict]) -> bool:
    return _first_match(stat_lines, identify_matches, entries)[0] is not None


def _combo_win(
    stat_lines: list[str],
    identify_matches,
    targets: list[dict],
    acceptable: list[dict],
) -> tuple[dict, dict] | tuple[None, None]:
    """Return (entry, tier) when item has >=1 target mod and >=1 other acceptable mod."""
    target_hits: list[tuple] = []
    acceptable_hits: list[tuple] = []

    for result in identify_matches(stat_lines):
        for match in result["matched"]:
            is_target = False
            for target in targets:
                if mod_entry_matches(match, target):
                    target_hits.append((target, match["matched_tier"]))
                    acceptable_hits.append((target, match["matched_tier"]))
                    is_target = True
                    break
            if not is_target:
                for entry in acceptable:
                    if mod_entry_matches(match, entry):
                        acceptable_hits.append((entry, match["matched_tier"]))
                        break

    if len(target_hits) >= 1 and len(acceptable_hits) >= 2:
        return target_hits[0]
    return None, None


def _run_fishing(
    apply_aug: "Callable[[], bool]",
    apply_annul: "Callable[[], bool]",
    read_item: "Callable[[], dict]",
    is_acceptable: "Callable[[dict], bool]",
    check_win: "Callable[[dict], tuple]",
    apply_seed: "Callable[[], bool | None] | None" = None,
    seed_label: str = "AUG1",
    seed_out_message: str = "Out of Augmentation Orbs.",
    aug_label: str = "AUG2",
    aug_out_message: str = "Out of Augmentation Orbs.",
    needs_seed_roll: "Callable[[dict], bool] | None" = None,
    seed_roll_label: str = "AUG1",
    cleanup_on_miss: bool = True,
) -> bool:
    """Pure two-phase augment/annul fishing loop."""
    uses_distinct_seed = apply_seed is not None
    if apply_seed is None:
        def _default_seed():
            return apply_aug()
        apply_seed = _default_seed
    if needs_seed_roll is None:
        def _default_needs_seed_roll(_item: dict) -> bool:
            return False
        needs_seed_roll = _default_needs_seed_roll

    cycle = 0
    lucky_streak = 0
    best_streak = 0
    seeds_used = 0
    augs_used = 0
    annuls_used = 0

    while True:
        cycle += 1

        seed_result = apply_seed()
        if seed_result is False:
            click.echo(f"\n{seed_out_message}")
            return False
        if seed_result is True:
            seeds_used += 1

        item = read_item()
        _log_item(f"Cycle #{cycle:>3}  {seed_label}", item)
        print(needs_seed_roll(item))
        if needs_seed_roll(item):
            click.echo("  ~ No seed mod present -> rolling first mod...\n")
            if not apply_aug():
                click.echo(f"\n{aug_out_message}")
                return False
            augs_used += 1
            item = read_item()
            _log_item(f"Cycle #{cycle:>3}  {seed_roll_label}", item)

        if not is_acceptable(item):
            click.echo("  x Bad mod -> annulling and restarting\n")
            if not apply_annul():
                click.echo("\nOut of Annulment Orbs.")
                return False
            annuls_used += 1
            lucky_streak = 0
            continue

        click.echo("  ~ Acceptable mod -> fishing for 2nd mod...\n")

        while True:
            if not apply_aug():
                click.echo(f"\n{aug_out_message}")
                return False
            augs_used += 1

            item = read_item()
            _log_item(f"Cycle #{cycle:>3}  {aug_label}", item)

            entry, tier = check_win(item)
            if entry:
                orb_summary = (
                    f"-- {seeds_used} {seed_label.lower()} | {augs_used} {aug_label.lower()} "
                    f"| {annuls_used} annuls | best streak: {best_streak} --"
                    if uses_distinct_seed
                    else f"-- {augs_used} augs | {annuls_used} annuls | best streak: {best_streak} --"
                )
                click.echo(
                    f"\n  OK WIN  [{entry['type'][:3].upper()} T{tier['tier']}]"
                    f" {entry['stat_template']}"
                )
                click.echo(orb_summary)
                return True

            click.echo("  x Bad 2nd mod -> annulling 1...\n")
            if not apply_annul():
                click.echo("\nOut of Annulment Orbs.")
                return False
            annuls_used += 1

            item = read_item()
            _log_item(f"Cycle #{cycle:>3}  POST", item)

            if is_acceptable(item):
                lucky_streak += 1
                best_streak = max(best_streak, lucky_streak)
                click.echo(
                    f"  ~ Good mod survived"
                    f" (streak: {lucky_streak} / best: {best_streak})"
                    f" -> fishing again...\n"
                )
            else:
                lucky_streak = 0
                if not cleanup_on_miss:
                    click.echo("  x Good mod annulled -> restarting from surviving magic item...\n")
                    break
                click.echo("  x Good mod annulled -> clearing and restarting...\n")
                if not apply_annul():
                    click.echo("\nOut of Annulment Orbs during cleanup.")
                    return False
                annuls_used += 1
                break


def _require_magic_item(
    found_mats: list[dict],
    hover_delay: float,
    copy_delay: float,
    target_entries: list[dict],
    identify_matches,
) -> tuple[bool, dict | None, str]:
    """
    Ensure the target item is magic when starting an augment-based strategy.

    Returns (ready, item, prep_state). When ready is False, the strategy should stop.
    """
    item = read_target(hover_delay, copy_delay)
    rarity = (item.get("rarity") or "").lower()

    if rarity == "magic":
        _log_item("Prep      START-MAGIC", item)
        return True, item, "magic"

    if rarity != "normal":
        click.echo(f"\nUnsupported target rarity for this strategy: {item.get('rarity') or 'Unknown'}.")
        click.echo("Put a Normal or Magic item in [0,0].")
        return False, None, "unsupported"

    tx, ty = cell_center(0, 0)
    transmutes = OrbDispenser([mat for mat in found_mats if mat["name"] in TRANSMUTE_NAMES], tx, ty)
    if not transmutes.total:
        click.echo("\nNo Orb of Transmutation found for the Normal base item.")
        return False, None, "no_transmute"

    if not transmutes.apply():
        click.echo("\nOut of Orb of Transmutation.")
        return False, None, "out_of_transmute"

    item = read_target(hover_delay, copy_delay)
    _log_item("Prep      TRANSMUTE", item)
    return True, item, "transmuted"


def strategy_chaos(
    found_mats: list[dict],
    hover_delay: float,
    copy_delay: float,
    target_entries: list[dict],
    identify_matches,
) -> bool:
    stacks = [mat for mat in found_mats if mat["name"] in CHAOS_NAMES and mat["count"] > 0]
    if not stacks:
        click.echo("\nNo Chaos Orbs found in inventory.")
        return False

    total = sum(mat["count"] for mat in stacks)
    tx, ty = cell_center(0, 0)
    roll = 0

    click.echo(f"\n-- Chaos Spam  {total} orb(s) ----------------------------------")

    import pyautogui as _pag

    try:
        for stack in stacks:
            cx, cy = cell_center(stack["col"], stack["row"])
            # Load the whole stack onto the cursor (right-click), then move
            # mouse over the target.  Shift is held BEFORE the first click so
            # every click draws one orb from the cursor stack.
            pick_up_orb_stack(cx, cy, tx, ty)

            _pag.keyDown("shift")
            time.sleep(0.05)
            try:
                original_count = stack["count"]
                stack["count"] = 0
                for _ in range(original_count):
                    roll += 1
                    _pag.click(button="left")
                    time.sleep(0.05)
                    item = read_target(hover_delay, copy_delay)
                    _log_item(f"Roll #{roll:>3}", item)
                    entry, tier = _first_match(item["stat_lines"], identify_matches, target_entries)
                    if entry:
                        click.echo(
                            f"\n  OK TARGET  [{entry['type'][:3].upper()} T{tier['tier']}]"
                            f" {entry['stat_template']}"
                        )
                        click.echo(f"-- Stopped after {roll} rolls --")
                        return True
                    click.echo()
            finally:
                _release_modifiers()
    finally:
        _release_modifiers()

    click.echo(f"-- Done | {roll} rolls | target NOT found --")
    return False


def strategy_aug_annul(
    found_mats: list[dict],
    hover_delay: float,
    copy_delay: float,
    target_entries: list[dict],
    identify_matches,
) -> bool:
    tx, ty = cell_center(0, 0)
    augs = OrbDispenser([mat for mat in found_mats if mat["name"] in AUG_NAMES], tx, ty)
    annuls = OrbDispenser([mat for mat in found_mats if mat["name"] in ANNUL_NAMES], tx, ty)

    if not annuls.total:
        click.echo("\nNo Annulment Orbs found.")
        return False
    click.echo(
        f"\n-- Augment + Annul  {augs.total} augs"
        f" | {sum(mat['count'] for mat in found_mats if mat['name'] in TRANSMUTE_NAMES)} transmutes"
        f" | {annuls.total} annuls --------------"
    )
    click.echo("  Flow: ensure magic -> check seed mod -> augment -> annul -> repeat\n")
    cycle = 0

    while True:
        cycle += 1
        ready, item, prep_state = _require_magic_item(
            found_mats, hover_delay, copy_delay, target_entries, identify_matches
        )
        if not ready:
            return False

        entry, tier = _first_match(item["stat_lines"], identify_matches, target_entries)
        if entry:
            click.echo(
                f"\n  OK TARGET  [{entry['type'][:3].upper()} T{tier['tier']}]"
                f" {entry['stat_template']}"
            )
            click.echo(f"-- Stopped after {cycle} cycles (target hit on {'transmute' if prep_state == 'transmuted' else 'starting'} seed) --")
            return True

        if not augs.total:
            click.echo("\nNo Augmentation Orbs found.")
            return False
        if not augs.apply():
            click.echo("\nOut of Augmentation Orbs.")
            return False

        item = read_target(hover_delay, copy_delay)
        _log_item(f"Cycle #{cycle:>3}  AUG", item)
        entry, tier = _first_match(item["stat_lines"], identify_matches, target_entries)
        if entry:
            click.echo(
                f"\n  OK TARGET  [{entry['type'][:3].upper()} T{tier['tier']}]"
                f" {entry['stat_template']}"
            )
            click.echo(f"-- Stopped after {cycle} cycles --")
            return True

        click.echo()
        if not annuls.apply():
            click.echo("\nOut of Annulment Orbs.")
            return False
        click.echo(f"  Cycle #{cycle:>3}  ANNUL1                  -> checking survivor\n")

        item = read_target(hover_delay, copy_delay)
        _log_item(f"Cycle #{cycle:>3}  POST", item)
        entry, tier = _first_match(item["stat_lines"], identify_matches, target_entries)
        if entry:
            click.echo(
                f"\n  OK TARGET  [{entry['type'][:3].upper()} T{tier['tier']}]"
                f" {entry['stat_template']}"
            )
            click.echo(f"-- Stopped after {cycle} cycles (target survived annul) --")
            return True

        # if (item.get("rarity") or "").lower() == "magic":
        #     if not annuls.apply():
        #         click.echo("\nOut of Annulment Orbs during cleanup.")
        #         return False
        #     click.echo(f"  Cycle #{cycle:>3}  ANNUL2                  -> cleanup to normal, restarting\n")
        # else:
        #     click.echo(f"  Cycle #{cycle:>3}  CLEAN                   -> already normal, restarting\n")


def strategy_aug_annul_5050(
    found_mats: list[dict],
    hover_delay: float,
    copy_delay: float,
    target_entries: list[dict],
    identify_matches,
    fifty_fifty_entries: list[dict],
) -> bool:
    tx, ty = cell_center(0, 0)
    transmutes = OrbDispenser([mat for mat in found_mats if mat["name"] in TRANSMUTE_NAMES], tx, ty)
    augs = OrbDispenser([mat for mat in found_mats if mat["name"] in AUG_NAMES], tx, ty)
    annuls = OrbDispenser([mat for mat in found_mats if mat["name"] in ANNUL_NAMES], tx, ty)
    acceptable = list(target_entries) + list(fifty_fifty_entries)

    if not annuls.total:
        click.echo("\nNo Annulment Orbs found.")
        return False
    if len(acceptable) < 2:
        click.echo("\nERROR: The 50-50 strategy requires at least 2 mods to fish for.")
        click.echo("  (Either 2+ target mods, or 1 target mod + 50-50 mods).")
        click.echo("  If you only want one mod, use 'Augment + Annul' instead.")
        return False

    current_item = read_target(hover_delay, copy_delay)
    current_rarity = (current_item.get("rarity") or "").lower()

    if current_rarity not in {"normal", "magic"}:
        click.echo(f"\nUnsupported target rarity for this strategy: {current_item.get('rarity') or 'Unknown'}.")
        click.echo("Put a Normal or Magic item in [0,0].")
        return False
    if current_rarity == "normal" and not transmutes.total:
        click.echo("\nNo Orb of Transmutation found for the Normal base item.")
        return False
    if not augs.total:
        click.echo("\nNo Augmentation Orbs found.")
        return False

    prepared, _, prep_state = _require_magic_item(
        found_mats, hover_delay, copy_delay, target_entries, identify_matches
    )
    if not prepared:
        return False

    click.echo(
        f"\n-- Aug + Annul 50-50  {transmutes.total} transmutes | {augs.total} augs | {annuls.total} annuls ----------"
    )
    click.echo(
        f"  Acceptable: {len(target_entries)} target + {len(fifty_fifty_entries)} 50-50 mod(s)"
    )
    click.echo(
        f"  Start: {'transmuted white base to magic' if prep_state == 'transmuted' else 'already magic'}"
    )
    click.echo("  Flow: keep one acceptable mod, augment for a second, annul bad pairs, repeat\n")

    return _run_fishing(
        apply_seed=lambda: None,
        apply_aug=augs.apply,
        apply_annul=annuls.apply,
        read_item=lambda: read_target(hover_delay, copy_delay),
        is_acceptable=lambda item: _any_match(item["stat_lines"], identify_matches, acceptable),
        check_win=lambda item: _combo_win(
            item["stat_lines"], identify_matches, target_entries, acceptable
        ),
        seed_label="SEED",
        aug_label="AUG",
        needs_seed_roll=lambda item: not item["stat_lines"],
        seed_roll_label="AUG-SEED",
        cleanup_on_miss=False,
    )
