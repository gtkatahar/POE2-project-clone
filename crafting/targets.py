"""Target configuration loading and shared target-building helpers."""

import json
import re
from datetime import datetime
from pathlib import Path

from item_parsing.identifier import build_lookup
from paths import ACTIVE_SOURCE, DATA, MATS, ROOT, SAVES, TARGET, db_path


# Backward-compatible aliases used across the codebase.
ROOT_DIR = ROOT
DATA_DIR = DATA
SAVES_DIR = SAVES
TARGET_FILE = TARGET
MATS_FILE = MATS
ACTIVE_SOURCE_FILE = ACTIVE_SOURCE


class TargetConfigError(RuntimeError):
    """Raised when target configuration cannot be loaded."""


def normalize_mod_entry(entry: dict) -> dict:
    """Ensure legacy target entries have a section_key (defaults to base mods)."""
    entry.setdefault("section_key", "normal")
    return entry


def mod_entry_matches(match: dict, entry: dict) -> bool:
    """True when an identified mod matches a target or keeper entry."""
    tier = match.get("matched_tier")
    if not tier:
        return False
    return (
        match["family"] == entry["family"]
        and match["section_key"] == entry.get("section_key", "normal")
        and tier["tier"] <= entry["min_tier"]
    )


def mods_from_data(data: dict) -> list[dict]:
    """Return the primary mod list from a target dict (search or strict mode)."""
    if data.get("mode") == "search":
        return data.get("mods", [])
    return data.get("prefixes", []) + data.get("suffixes", [])


def target_to_active(data: dict) -> dict:
    """Strip save metadata to produce a target_mods.json-compatible dict."""
    keys = ("slug", "mode", "mods", "prefixes", "suffixes", "fifty_fifty")
    return {k: data[k] for k in keys if k in data}


def build_mod_entry(group: dict, min_tier: int) -> dict:
    """Build a target mod entry dict from a DB group and chosen minimum tier."""
    return {
        "type": group["type"],
        "family": group["family"],
        "stat_template": group.get("stat_template", group["family"]),
        "min_tier": min_tier,
        "section_key": group.get("section_key", "normal"),
        "tags": group.get("tags", []),
    }


def sanitize_save_name(name: str) -> str:
    """Turn a user string into a safe filename stem."""
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", "_", name)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return (safe or "save")[:80]


def load_or_fetch_db(slug: str) -> dict:
    """Load a tiered modifier DB from disk, scraping first if missing."""
    from scraping.poe2db import fetch_tiered_modifiers, save_json

    path = db_path(slug)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    DATA.mkdir(exist_ok=True)
    data = fetch_tiered_modifiers(slug)
    save_json(data, path)
    return data


def load_db_groups(slug: str, *, base_only: bool = False) -> list[dict]:
    """Return modifier groups for a slug, optionally filtered to base prefix/suffix."""
    db = load_or_fetch_db(slug)
    groups = db["modifiers"]
    if not base_only:
        return groups
    return [
        g for g in groups
        if g.get("section") == "Base Modifiers"
        and g.get("type", "").lower() in ("prefix", "suffix")
    ]


def load_all_db_groups(slug: str) -> dict[str, list[dict]]:
    """Return {section_key: [groups]} for all sections in the slug's DB file."""
    groups: dict[str, list[dict]] = {}
    for g in load_or_fetch_db(slug)["modifiers"]:
        key = g.get("section_key", "normal")
        groups.setdefault(key, []).append(g)
    return groups


def list_saves(saves_dir: Path = SAVES) -> list[Path]:
    """Return all saved target JSON files, newest first."""
    if not saves_dir.exists():
        return []
    return sorted(saves_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def load_save(path: Path) -> dict:
    """Read a saved target JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def save_named_target(result: dict, name: str) -> Path:
    """Persist a target to saved_targets/{name}.json. Returns the path written."""
    SAVES.mkdir(exist_ok=True)
    safe = sanitize_save_name(name)
    dest = SAVES / f"{safe}.json"
    payload = {
        "save_name": name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        **result,
    }
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def load_target_mods(target_data: dict | None = None) -> tuple[list[dict], list[dict], dict, str, list[dict]]:
    """
    Read target_mods.json or use provided data, then load the matching modifier DB.
    Returns (target_entries, fifty_fifty_entries, mod_lookup, slug, db_groups).
    """
    if target_data is None:
        if not TARGET.exists():
            raise TargetConfigError("target_mods.json not found. Run  py build_target.py  first.")
        target_data = json.loads(TARGET.read_text(encoding="utf-8"))

    slug = target_data.get("slug", "")
    path = db_path(slug)
    if not path.exists():
        raise TargetConfigError(f"modifier DB for '{slug}' not found at {path}")

    all_groups = json.loads(path.read_text(encoding="utf-8"))["modifiers"]
    # All sections go into the lookup so item scans can identify runes, bonded,
    # essence, corrupted, etc. mods when they appear on a scanned item.
    mod_lookup = build_lookup(all_groups)
    # Odds / crafting calculations only apply to the normal prefix/suffix pool.
    db_groups = [g for g in all_groups if g.get("section") == "Base Modifiers"]

    target_entries = mods_from_data(target_data)
    fifty_fifty_entries = target_data.get("fifty_fifty", [])

    for entry in target_entries + fifty_fifty_entries:
        normalize_mod_entry(entry)

    if not target_entries:
        raise TargetConfigError("target_mods.json has no mods defined.")

    return target_entries, fifty_fifty_entries, mod_lookup, slug, db_groups
