"""
test_tier_overlaps.py
---------------------
Detect any overlapping value ranges between tiers in the same modifier group.
Run: .venv\Scripts\python test_tier_overlaps.py
"""
import json


def ranges_overlap(a, b) -> bool:
    """Return True if two tier value-lists have any dimensional overlap."""
    if len(a) != len(b):
        return False
    for av, bv in zip(a, b):
        alo, ahi = (av[0], av[1]) if isinstance(av, list) else (av, av)
        blo, bhi = (bv[0], bv[1]) if isinstance(bv, list) else (bv, bv)
        if ahi < blo or bhi < alo:
            return False
    return True


data = json.load(open("data/talismans_modifiers_tiered.json", encoding="utf-8"))
groups = [
    g for g in data["modifiers"]
    if g["type"] in ("Prefix", "Suffix") and g.get("section") == "Base Modifiers"
]

found = False
for g in groups:
    tiers = g["tiers"]
    for i in range(len(tiers)):
        for j in range(i + 1, len(tiers)):
            ta, tb = tiers[i], tiers[j]
            if ranges_overlap(ta["values"], tb["values"]):
                print(
                    f"OVERLAP  [{g['type']}] {g['family']}\n"
                    f"         T{ta['tier']} '{ta['name']}' {ta['values']}\n"
                    f"         T{tb['tier']} '{tb['name']}' {tb['values']}\n"
                )
                found = True

if not found:
    print("No overlapping tier ranges found.")
