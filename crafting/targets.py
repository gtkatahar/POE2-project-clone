"""Target configuration loading utilities."""

import json
from pathlib import Path

from item_parsing.identifier import build_lookup


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SAVES_DIR = ROOT_DIR / "saved_targets"
TARGET_FILE = ROOT_DIR / "target_mods.json"


class TargetConfigError(RuntimeError):
    """Raised when target configuration cannot be loaded."""


def list_saves(saves_dir: Path = SAVES_DIR) -> list[Path]:
    """Return all saved target JSON files, newest first."""
    if not saves_dir.exists():
        return []
    return sorted(saves_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def load_save(path: Path) -> dict:
    """Read a saved target JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_target_mods(target_data: dict | None = None) -> tuple[list[dict], list[dict], dict, str, list[dict]]:
    """
    Read target_mods.json or use provided data, then load the matching modifier DB.
    Returns (target_entries, fifty_fifty_entries, mod_lookup, slug, db_groups).
    """
    if target_data is None:
        if not TARGET_FILE.exists():
            raise TargetConfigError("target_mods.json not found. Run  py build_target.py  first.")
        target_data = json.loads(TARGET_FILE.read_text(encoding="utf-8"))

    slug = target_data.get("slug", "")
    db_path = DATA_DIR / f"{slug.lower()}_modifiers_tiered.json"
    if not db_path.exists():
        raise TargetConfigError(f"modifier DB for '{slug}' not found at {db_path}")

    db_groups = [
        group
        for group in json.loads(db_path.read_text(encoding="utf-8"))["modifiers"]
        if group.get("section") == "Base Modifiers"
    ]
    mod_lookup = build_lookup(db_groups)

    if target_data.get("mode") == "search":
        target_entries = target_data.get("mods", [])
    else:
        target_entries = target_data.get("prefixes", []) + target_data.get("suffixes", [])

    fifty_fifty_entries = target_data.get("fifty_fifty", [])

    if not target_entries:
        raise TargetConfigError("target_mods.json has no mods defined.")

    return target_entries, fifty_fifty_entries, mod_lookup, slug, db_groups
