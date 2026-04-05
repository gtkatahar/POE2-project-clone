"""
build_target.py
---------------
Interactive CLI for two modes:

  Search for mods  — fuzzy-search and collect any number of mods
  Target mods      — build a strict prefix/suffix target (max 3+3) with min tier

Usage:
    py build_target.py
    py build_target.py --slug Swords
"""

import json
import re
from datetime import datetime
from pathlib import Path

import click
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator

from scraping.poe2db import fetch_tiered_modifiers, save_json

DATA_DIR   = Path(__file__).parent / "data"
SAVES_DIR  = Path(__file__).parent / "saved_targets"

MAX_PREFIXES = 3
MAX_SUFFIXES = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_or_fetch_db(slug: str) -> dict:
    db_path = DATA_DIR / f"{slug.lower()}_modifiers_tiered.json"
    if db_path.exists():
        return json.loads(db_path.read_text(encoding="utf-8"))
    print(f"Database for '{slug}' not found — scraping now…")
    DATA_DIR.mkdir(exist_ok=True)
    data = fetch_tiered_modifiers(slug)
    save_json(data, db_path)
    return data


def _fmt_values(values: list) -> str:
    parts = []
    for v in values:
        parts.append(f"{v[0]}{v[1]}" if isinstance(v, list) else str(v))
    return ", ".join(parts)


def _fmt_mod_label(group: dict) -> str:
    return f"[{group['type'][:3].upper()}] {group['family']:28s}  {group['stat_template']}"


def _fmt_tier_label(tier: dict) -> str:
    vals = _fmt_values(tier["values"])
    return f"T{tier['tier']}  {tier['name']:20s}  ilvl≥{tier['min_ilvl']}  [{vals}]"


def _pick_min_tier(group: dict) -> int:
    """Prompt the user to pick a minimum tier for a mod group."""
    tier_choices = [
        Choice(value=t["tier"], name=_fmt_tier_label(t))
        for t in group["tiers"]
    ]
    tier_choices.append(Choice(
        value=group["num_tiers"],
        name=f"Any tier  (T{group['num_tiers']} minimum — most lenient)",
    ))
    return inquirer.select(
        message=f"Minimum tier for  [{group['stat_template']}]:",
        choices=tier_choices,
        default=tier_choices[0].value,
    ).execute()


def _fuzzy_pick_mod(pool: list[dict], already: set[str], label: str):
    """Fuzzy-search a mod from pool, excluding already-chosen ones."""
    choices = [
        Choice(value=g, name=_fmt_mod_label(g))
        for g in pool
        if g["stat_template"] not in already
    ]
    if not choices:
        print("  No more mods available.")
        return None
    return inquirer.fuzzy(
        message=label,
        choices=choices,
        max_height="80%",
        match_exact=False,
    ).execute()


# ---------------------------------------------------------------------------
# Mode A — Search for mods (no limit)
# ---------------------------------------------------------------------------

def _mode_search(groups: list[dict]) -> list[dict]:
    """Add any number of mods from the full pool, with min-tier selection."""
    chosen: list[dict] = []

    print("\n  Search for mods — add as many as you like.")
    print("  Choose 'Done' when finished.\n")

    while True:
        # Summary
        if chosen:
            print("  ┌─ Selected mods ─────────────────────────────────────────┐")
            for m in chosen:
                print(f"  │  [T{m['min_tier']}+] [{m['type'][:3].upper()}] {m['stat_template']}")
            print("  └─────────────────────────────────────────────────────────┘\n")

        choices = [Choice("add", name="Add a mod")]
        if chosen:
            choices.append(Choice("remove", name="Remove a mod"))
        choices.append(Separator())
        choices.append(Choice("done", name="Done — save and quit"))

        action = inquirer.select(
            message="What would you like to do?",
            choices=choices,
        ).execute()

        if action == "done":
            break

        if action == "add":
            already = {m["stat_template"] for m in chosen}
            group = _fuzzy_pick_mod(groups, already, "Search mods:")
            if group is None:
                continue
            min_tier = _pick_min_tier(group)
            chosen.append({
                "type":          group["type"],
                "family":        group["family"],
                "stat_template": group["stat_template"],
                "min_tier":      min_tier,
                "tags":          group["tags"],
            })

        elif action == "remove":
            to_remove = inquirer.select(
                message="Which mod to remove?",
                choices=[
                    Choice(value=i, name=f"[T{m['min_tier']}+] [{m['type'][:3].upper()}] {m['stat_template']}")
                    for i, m in enumerate(chosen)
                ],
            ).execute()
            chosen.pop(to_remove)

    return chosen


# ---------------------------------------------------------------------------
# Mode B — Target mods (max 3 prefix + 3 suffix)
# ---------------------------------------------------------------------------

def _print_target_summary(prefixes: list, suffixes: list) -> None:
    print()
    print("  ┌─ Current target ─────────────────────────────────────────┐")
    print(f"  │  Prefixes ({len(prefixes)}/{MAX_PREFIXES})")
    for p in prefixes:
        print(f"  │    [T{p['min_tier']}+] {p['stat_template']}")
    print(f"  │  Suffixes ({len(suffixes)}/{MAX_SUFFIXES})")
    for s in suffixes:
        print(f"  │    [T{s['min_tier']}+] {s['stat_template']}")
    print("  └──────────────────────────────────────────────────────────┘")
    print()


def _mode_target(groups: list[dict]) -> tuple[list, list]:
    """Build a strict prefix/suffix target with min-tier selection."""
    prefixes_db = [g for g in groups if g["type"].lower() == "prefix"]
    suffixes_db = [g for g in groups if g["type"].lower() == "suffix"]
    chosen_prefixes: list[dict] = []
    chosen_suffixes: list[dict] = []

    print("\n  Target mods — max 3 prefixes and 3 suffixes.\n")

    while True:
        _print_target_summary(chosen_prefixes, chosen_suffixes)
        n_pre, n_suf = len(chosen_prefixes), len(chosen_suffixes)

        choices = []
        if n_pre < MAX_PREFIXES:
            choices.append(Choice("prefix", name=f"Add Prefix  ({n_pre}/{MAX_PREFIXES})"))
        else:
            choices.append(Choice("prefix", name=f"Prefixes FULL ({MAX_PREFIXES}/{MAX_PREFIXES})", enabled=False))
        if n_suf < MAX_SUFFIXES:
            choices.append(Choice("suffix", name=f"Add Suffix  ({n_suf}/{MAX_SUFFIXES})"))
        else:
            choices.append(Choice("suffix", name=f"Suffixes FULL ({MAX_SUFFIXES}/{MAX_SUFFIXES})", enabled=False))
        if chosen_prefixes or chosen_suffixes:
            choices.append(Choice("remove", name="Remove a mod"))
        choices.append(Separator())
        choices.append(Choice("done", name="Done — save and quit"))

        action = inquirer.select(
            message="What would you like to do?",
            choices=choices,
            default="done" if (n_pre + n_suf) > 0 else "prefix",
        ).execute()

        if action == "done":
            break

        if action in ("prefix", "suffix"):
            pool    = prefixes_db if action == "prefix" else suffixes_db
            existing = chosen_prefixes if action == "prefix" else chosen_suffixes
            already = {m["stat_template"] for m in existing}
            group = _fuzzy_pick_mod(pool, already, f"Search {action} mods:")
            if group is None:
                continue
            min_tier = _pick_min_tier(group)
            entry = {
                "type":          action,
                "family":        group["family"],
                "stat_template": group["stat_template"],
                "min_tier":      min_tier,
                "tags":          group["tags"],
            }
            (chosen_prefixes if action == "prefix" else chosen_suffixes).append(entry)

        elif action == "remove":
            all_mods = [
                Choice(value=("prefix", i), name=f"[PREFIX T{m['min_tier']}+] {m['stat_template']}")
                for i, m in enumerate(chosen_prefixes)
            ] + [
                Choice(value=("suffix", i), name=f"[SUFFIX T{m['min_tier']}+] {m['stat_template']}")
                for i, m in enumerate(chosen_suffixes)
            ]
            kind, idx = inquirer.select(
                message="Which mod to remove?",
                choices=all_mods,
            ).execute()
            (chosen_prefixes if kind == "prefix" else chosen_suffixes).pop(idx)

    return chosen_prefixes, chosen_suffixes


def _pick_fifty_fifty_mods(groups: list[dict], already_chosen: set[str]) -> list[dict]:
    """Interactively pick 50-50 (keeper) mods for the aug+annul strategy."""
    chosen: list[dict] = []

    print("\n  50-50 mods — mods you are OK keeping to augment again.")
    print("  Leave empty to skip.\n")

    while True:
        if chosen:
            print("  ┌─ 50-50 mods ───────────────────────────────────────────────┐")
            for m in chosen:
                print(f"  │  [T{m['min_tier']}+] [{m['type'][:3].upper()}] {m['stat_template']}")
            print("  └────────────────────────────────────────────────────────────┘\n")

        choices = [Choice("add", name="Add a 50-50 mod")]
        if chosen:
            choices.append(Choice("remove", name="Remove a 50-50 mod"))
        choices.append(Separator())
        choices.append(Choice("done", name="Done"))

        action = inquirer.select(
            message="50-50 mods:",
            choices=choices,
        ).execute()

        if action == "done":
            break

        if action == "add":
            excluded = already_chosen | {m["stat_template"] for m in chosen}
            group = _fuzzy_pick_mod(groups, excluded, "Search 50-50 mods:")
            if group is None:
                continue
            min_tier = _pick_min_tier(group)
            chosen.append({
                "type":          group["type"],
                "family":        group["family"],
                "stat_template": group["stat_template"],
                "min_tier":      min_tier,
                "tags":          group["tags"],
            })

        elif action == "remove":
            to_remove = inquirer.select(
                message="Which 50-50 mod to remove?",
                choices=[
                    Choice(value=i, name=f"[T{m['min_tier']}+] [{m['type'][:3].upper()}] {m['stat_template']}")
                    for i, m in enumerate(chosen)
                ],
            ).execute()
            chosen.pop(to_remove)

    return chosen


def _pick_slug(default: str) -> str:
    """Prompt the user to pick an item category from available DB files."""
    from scraping.poe2db import fetch_modifier_slugs

    # Build name→slug map from already-downloaded files
    available: dict[str, str] = {}
    for p in sorted(DATA_DIR.glob("*_modifiers_tiered.json")):
        slug = p.name.replace("_modifiers_tiered.json", "")
        available[slug] = slug

    if not available:
        print("  No modifier databases found in data/. Run scrape_all.py first.")
        return default

    # Try to enrich with human-readable names from the index
    try:
        index = fetch_modifier_slugs()
        name_map = {s["slug"].lower(): s["name"] for s in index}
    except Exception:
        name_map = {}

    choices = []
    for slug_key, slug_val in available.items():
        display_name = name_map.get(slug_key.lower(), slug_key.replace("_", " ").title())
        choices.append(Choice(value=slug_val, name=f"{display_name:35s}  ({slug_key})"))

    return inquirer.fuzzy(
        message="Item category:",
        choices=choices,
        max_height="80%",
        match_exact=False,
    ).execute()


# ---------------------------------------------------------------------------
# Save / Load helpers
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    """Turn any user string into a safe filename (no special chars)."""
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)   # strip illegal chars
    name = re.sub(r"\s+", "_", name)             # spaces → underscores
    return name[:80] or "save"


def _list_saves() -> list[Path]:
    """Return all .json files in SAVES_DIR, newest first."""
    if not SAVES_DIR.exists():
        return []
    return sorted(SAVES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _save_result(result: dict, name: str) -> Path:
    """Persist result to SAVES_DIR/{safe_name}.json. Returns the path written."""
    SAVES_DIR.mkdir(exist_ok=True)
    safe = _sanitize_filename(name)
    dest = SAVES_DIR / f"{safe}.json"
    payload = {
        "save_name":  name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **result,
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def _preview_save(data: dict, indent: str = "  ") -> str:
    """Return a multi-line human-readable preview of a saved target."""
    lines: list[str] = []
    slug        = data.get("slug", "unknown")
    mode        = data.get("mode", "?").title()
    created_at  = data.get("created_at", "")
    created_str = f"  (saved {created_at})" if created_at else ""

    lines.append(f"{indent}Item  : {slug.replace('_', ' ').title()}{created_str}")
    lines.append(f"{indent}Mode  : {mode}")

    # Search mode — flat mod list
    mods = data.get("mods", [])
    if mods:
        lines.append(f"{indent}Mods  :")
        for m in mods:
            lines.append(f"{indent}  [{m['type'][:3].upper()} T{m['min_tier']}+] {m['stat_template']}")

    # Target mode — prefixes + suffixes
    prefixes = data.get("prefixes", [])
    suffixes = data.get("suffixes", [])
    if prefixes:
        lines.append(f"{indent}Prefix:")
        for m in prefixes:
            lines.append(f"{indent}  [T{m['min_tier']}+] {m['stat_template']}")
    if suffixes:
        lines.append(f"{indent}Suffix:")
        for m in suffixes:
            lines.append(f"{indent}  [T{m['min_tier']}+] {m['stat_template']}")

    # 50-50 mods
    fifty = data.get("fifty_fifty", [])
    if fifty:
        lines.append(f"{indent}50-50 :")
        for m in fifty:
            lines.append(f"{indent}  [{m['type'][:3].upper()} T{m['min_tier']}+] {m['stat_template']}")

    return "\n".join(lines)


def _pick_save_to_load() -> dict | None:
    """
    Interactive fuzzy-select over all saves.
    Shows a full preview of the highlighted save, then returns the loaded dict
    (or None if the user cancels).
    """
    saves = _list_saves()
    if not saves:
        print("  No saved targets found.")
        return None

    # Load all saves to build the preview map
    loaded: dict[str, dict] = {}
    for p in saves:
        try:
            loaded[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass

    choices = []
    for p in saves:
        data        = loaded.get(p.stem, {})
        save_name   = data.get("save_name", p.stem)
        slug        = data.get("slug", "?").replace("_", " ").title()
        created_at  = data.get("created_at", "")
        all_mods    = (
            data.get("mods", [])
            + data.get("prefixes", [])
            + data.get("suffixes", [])
        )
        n_mods = len(all_mods)
        n_5050 = len(data.get("fifty_fifty", []))
        tag    = f"  +{n_5050} 50-50" if n_5050 else ""
        date_str = f"  [{created_at}]" if created_at else ""
        label  = f"{save_name:<28s}  {slug:<22s}  {n_mods} mod(s){tag}{date_str}"
        choices.append(Choice(value=p.stem, name=label))

    choices.append(Choice(value=None, name="← Cancel — build a new target instead"))

    stem = inquirer.fuzzy(
        message="Load a saved target  (type to filter):",
        choices=choices,
        max_height="80%",
        match_exact=False,
    ).execute()

    if stem is None:
        return None

    data = loaded[stem]
    print()
    print("  ┌─ Save preview ───────────────────────────────────────────┐")
    for line in _preview_save(data).splitlines():
        print(f"  │{line}")
    print("  └──────────────────────────────────────────────────────────┘")
    print()

    confirm = inquirer.confirm(
        message=f"Load  '{data.get('save_name', stem)}'  as the active target?",
        default=True,
    ).execute()

    return data if confirm else None


def _prompt_save(result: dict) -> None:
    """Offer to save a freshly-built target under a user-chosen name."""
    want = inquirer.confirm(
        message="Save this target for later?",
        default=True,
    ).execute()
    if not want:
        return

    existing_names = {json.loads(p.read_text(encoding="utf-8")).get("save_name", p.stem)
                      for p in _list_saves()}

    while True:
        name = inquirer.text(
            message="Save name:",
            validate=lambda x: bool(x.strip()) or "Name cannot be empty.",
        ).execute().strip()

        if name in existing_names:
            overwrite = inquirer.confirm(
                message=f"  '{name}' already exists — overwrite?",
                default=False,
            ).execute()
            if not overwrite:
                continue

        dest = _save_result(result, name)
        print(f"\n  Saved  '{name}'  →  {dest}\n")
        break


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

@click.command()
@click.option("--slug",   default=None,
              help="Item category slug (e.g. Talismans). Prompts if omitted.")
@click.option("--output", default="target_mods.json", show_default=True,
              help="Output file path.")
def main(slug: str | None, output: str):
    """Build a mod target — search freely or build a strict prefix/suffix list."""

    print()

    # ── Load an existing save? ──────────────────────────────────────────────
    saves = _list_saves()
    start_action = "new"
    if saves:
        start_action = inquirer.select(
            message="What would you like to do?",
            choices=[
                Choice("load", name=f"Load a saved target   ({len(saves)} save(s) available)"),
                Choice("new",  name="Build a new target"),
            ],
        ).execute()

    if start_action == "load":
        loaded = _pick_save_to_load()
        if loaded is not None:
            # Strip save metadata before writing to output
            result = {k: v for k, v in loaded.items()
                      if k not in ("save_name", "created_at")}
            out = Path(output)
            out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  Active target set  →  {out}\n")
            return
        # User cancelled — fall through to build a new one
        print()

    # ── Build a new target ──────────────────────────────────────────────────
    if not slug:
        slug = _pick_slug("Talismans")

    db     = _load_or_fetch_db(slug)
    groups = [
        g for g in db["modifiers"]
        if g["type"].lower() in ("prefix", "suffix")
        and g.get("section") == "Base Modifiers"
    ]
    print(f"\n  Loaded {len(groups)} modifier groups for {slug} (prefix/suffix only).\n")

    mode = inquirer.select(
        message="Select mode:",
        choices=[
            Choice("search", name="Search for mods  — add any number of mods freely"),
            Choice("target", name="Target mods      — strict 3 prefix / 3 suffix with min tier"),
        ],
    ).execute()

    result: dict = {"slug": slug, "mode": mode}

    if mode == "search":
        chosen = _mode_search(groups)
        if not chosen:
            print("\n  No mods selected — nothing saved.")
            return
        result["mods"] = chosen

    else:
        prefixes, suffixes = _mode_target(groups)
        if not prefixes and not suffixes:
            print("\n  No mods selected — nothing saved.")
            return
        result["prefixes"] = prefixes
        result["suffixes"] = suffixes

    # Optional 50-50 mods
    want_5050 = inquirer.confirm(
        message="Add 50-50 mods? (keeper mods for the aug+annul strategy)",
        default=False,
    ).execute()
    if want_5050:
        all_target_templates = {
            m["stat_template"]
            for m in result.get("mods", []) + result.get("prefixes", []) + result.get("suffixes", [])
        }
        fifty_fifty = _pick_fifty_fifty_mods(groups, all_target_templates)
        if fifty_fifty:
            result["fifty_fifty"] = fifty_fifty

    # ── Write active target_mods.json ───────────────────────────────────────
    out = Path(output)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Active target set  →  {out}")

    # ── Offer to save for later ─────────────────────────────────────────────
    _prompt_save(result)


if __name__ == "__main__":
    main()
