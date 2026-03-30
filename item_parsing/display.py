"""
item_parsing/display.py
-----------------------
Console output for identified item modifier results.
"""


RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"


def _fmt_vals(vals: list) -> str:
    parts = []
    for v in vals:
        parts.append(f"{v[0]}\u2013{v[1]}" if isinstance(v, list) else str(v))
    return ", ".join(parts)


def _print_tier_list(tiers: list[dict], highlight_tier: int | None) -> None:
    for t in tiers:
        is_match = highlight_tier is not None and t["tier"] == highlight_tier
        marker = f"{GREEN}\u25ba{RESET}" if is_match else " "
        color  = GREEN if is_match else DIM
        print(f"      {marker} {color}T{t['tier']}  ilvl\u2265{t['min_ilvl']:>3}  "
              f"wt:{t['weight']:>5}  \"{t['name']}\"  [{_fmt_vals(t['values'])}]{RESET}")


def print_results(item: dict, results: list[dict]) -> None:
    """Print a formatted identification report to stdout."""
    print("=" * 65)
    print(f"  {BOLD}{item['name']}{RESET}  \u2014  {item['base']}")
    print(f"  Class: {item['item_class']}   iLvl: {item['item_level']}")
    print("=" * 65)

    for r in results:
        frac = f"  {YELLOW}[FRACTURED]{RESET}" if r["is_fractured"] else ""
        print(f"\n{BOLD}{r['item_stat']}{RESET}{frac}")

        if not r["matched"] and not r["unmatched"]:
            print(f"  {RED}\u2717 No match found in database{RESET}")
            continue

        # Confirmed tier matches
        for f in r["matched"]:
            t = f["matched_tier"]
            print(f"  {GREEN}\u2714 [{f['section']}] {f['type']}  \u2014  {f['family']}{RESET}")
            print(f"    template : {f['stat_template']}")
            print(f"    tags     : {', '.join(f['tags']) or '\u2014'}")
            print(f"    {GREEN}rolled   : T{t['tier']} \"{t['name']}\"  "
                  f"ilvl\u2265{t['min_ilvl']}  wt:{t['weight']}{RESET}")
            print(f"    {DIM}all tiers:{RESET}")
            _print_tier_list(f["all_tiers"], t["tier"])

        # Template matched but value falls outside all known tiers
        if not r["matched"] and r["unmatched"]:
            print(f"  {YELLOW}~ Template matched but value fits no tier:{RESET}")
            for f in r["unmatched"]:
                print(f"  {DIM}  [{f['section']}] {f['type']}  \u2014  {f['family']}{RESET}")
                print(f"      template : {f['stat_template']}")
                _print_tier_list(f["all_tiers"], None)
        elif r["unmatched"]:
            pools = list(dict.fromkeys(f["section"] for f in r["unmatched"]))
            print(f"  {DIM}  also in: {', '.join(pools)}{RESET}")

    print()


# ---------------------------------------------------------------------------
# Simplified view
# ---------------------------------------------------------------------------

def build_simple_result(item: dict, results: list[dict]) -> dict:
    """Return only matched mods as a compact dict (no tier lists, no unmatched)."""
    mods = []
    for r in results:
        for f in r["matched"]:
            t = f["matched_tier"]
            mods.append({
                "stat":         r["item_stat"],
                "is_fractured": r["is_fractured"],
                "section":      f["section"],
                "type":         f["type"],
                "family":       f["family"],
                "tags":         f["tags"],
                "tier":         t["tier"],
                "tier_name":    t["name"],
                "min_ilvl":     t["min_ilvl"],
                "weight":       t["weight"],
                "values":       t["values"],
            })
    return {"item": item, "total_matched": len(mods), "mods": mods}


def print_simple(item: dict, results: list[dict]) -> None:
    """Print a compact one-line-per-mod summary."""
    print("=" * 65)
    print(f"  {BOLD}{item['name']}{RESET}  \u2014  {item['base']}")
    print(f"  Class: {item['item_class']}   iLvl: {item['item_level']}")
    print("=" * 65)

    any_matched = False
    for r in results:
        for f in r["matched"]:
            any_matched = True
            t = f["matched_tier"]
            frac = f"  {YELLOW}[FRACTURED]{RESET}" if r["is_fractured"] else ""
            tier_info = f"{GREEN}T{t['tier']} \"{t['name']}\"{RESET}  ilvl\u2265{t['min_ilvl']}  [{_fmt_vals(t['values'])}]"
            print(f"  {GREEN}\u2714{RESET}  {BOLD}{r['item_stat']}{RESET}{frac}")
            print(f"       {tier_info}   {DIM}{f['section']} / {f['type']}{RESET}")

    if not any_matched:
        print(f"  {RED}No matched modifiers found.{RESET}")
    print()
