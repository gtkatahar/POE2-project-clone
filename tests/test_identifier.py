"""
Quick regression test for item_parsing.identifier against all target mod families.
Run: .venv\Scripts\python test_identifier.py
"""
import json
from item_parsing.identifier import build_lookup, identify

data = json.load(open("data/talismans_modifiers_tiered.json", encoding="utf-8"))
groups = [
    g for g in data["modifiers"]
    if g["type"] in ("Prefix", "Suffix") and g.get("section") == "Base Modifiers"
]
lookup = build_lookup(groups)

# (family, example rolled stat line, expected tier)
TESTS = [
    # ── Critical Hit Chance (Suffix) ──────────────────────────────────
    ("CriticalStrikeChanceIncrease", "+4.64% to Critical Hit Chance",     1),
    ("CriticalStrikeChanceIncrease", "+4.10% to Critical Hit Chance",     2),
    ("CriticalStrikeChanceIncrease", "+3.50% to Critical Hit Chance",     3),
    ("CriticalStrikeChanceIncrease", "+2.40% to Critical Hit Chance",     4),
    ("CriticalStrikeChanceIncrease", "+1.80% to Critical Hit Chance",     5),
    ("CriticalStrikeChanceIncrease", "+1.20% to Critical Hit Chance",     6),
    # ── Flat Physical Damage (Prefix) ─────────────────────────────────
    ("PhysicalDamage",               "Adds 40 to 75 Physical Damage",     1),
    ("PhysicalDamage",               "Adds 30 to 55 Physical Damage",     2),
    ("PhysicalDamage",               "Adds 25 to 45 Physical Damage",     3),
    ("PhysicalDamage",               "Adds 5 to 12 Physical Damage",      8),
    # ── % increased Physical Damage (Prefix) ──────────────────────────
    ("LocalPhysicalDamagePercent",   "170% increased Physical Damage",    1),
    ("LocalPhysicalDamagePercent",   "160% increased Physical Damage",    2),
    ("LocalPhysicalDamagePercent",   "140% increased Physical Damage",    3),
    ("LocalPhysicalDamagePercent",   "50% increased Physical Damage",     7),
    ("LocalPhysicalDamagePercent",   "40% increased Physical Damage",     8),
    # ── Flat Lightning Damage (Prefix) ────────────────────────────────
    ("LightningDamage",              "Adds 10 to 330 Lightning Damage",   1),
    ("LightningDamage",              "Adds 8 to 260 Lightning Damage",    2),
    ("LightningDamage",              "Adds 3 to 140 Lightning Damage",    4),
    ("LightningDamage",              "Adds 2 to 35 Lightning Damage",     8),
]

ok = True
for family, stat, expected_tier in TESTS:
    results = identify([stat], lookup)
    matched = results[0]["matched"]
    hit = next((m for m in matched if m["family"] == family), None)
    if hit is None:
        print(f"FAIL  no match         | {stat}")
        ok = False
    elif hit["matched_tier"]["tier"] != expected_tier:
        got = hit["matched_tier"]["tier"]
        print(f"FAIL  T{expected_tier} expected T{got} got  | {stat}")
        ok = False
    else:
        name = hit["matched_tier"]["name"]
        print(f"OK    T{hit['matched_tier']['tier']}  {name:22s}  | {stat}")

print()
print("All OK" if ok else "FAILURES ABOVE — check identifier.py")
