"""Shared filesystem paths for the POE2 crafting tool."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SAVES = ROOT / "saved_targets"
TARGET = ROOT / "target_mods.json"
MATS = ROOT / "crafting_mats.json"
SETTINGS = ROOT / "settings.json"
ACTIVE_SOURCE = ROOT / "active_target_source.txt"


def db_path(slug: str) -> Path:
    return DATA / f"{slug.lower()}_modifiers_tiered.json"
