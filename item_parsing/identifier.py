"""
item_parsing/identifier.py
--------------------------
Match a parsed item's stat lines against a tiered modifier database
(produced by scraping.poe2db.fetch_tiered_modifiers) and identify
each modifier's family, section, and exact tier rolled.
"""

import re


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """
    Reduce a stat string to a template that matches stat_template in the DB.
    All numeric values and ranges are replaced with #.
    """
    text = re.sub(
        r"\s*\((fractured|implicit|crafted|corrupted|enchant|veiled)\)",
        "", text, flags=re.IGNORECASE,
    )
    # Collapse numeric (min—max) ranges to a single #
    text = re.sub(r"[+\-]?\(\d+[\u2014\u2013\-]\d+\.?\d*\)", "#", text)
    # Collapse template-style (#—#) ranges (DB stat_template already uses #)
    text = re.sub(r"[+\-]?\(#[\u2014\u2013\-]#\)", "#", text)
    text = re.sub(r"[+\-]?\d+\.?\d*", "#", text)
    text = re.sub(r"#\s+%", "#%", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_values(text: str) -> list:
    """Pull all numeric tokens from a stat line in order."""
    text = re.sub(
        r"\s*\((fractured|implicit|crafted|corrupted|enchant|veiled)\)",
        "", text, flags=re.IGNORECASE,
    )
    values: list = []
    for m in re.finditer(r"[+\-]?\d+\.?\d*", text):
        raw = m.group()
        values.append(float(raw) if "." in raw else int(raw))
    return values


# ---------------------------------------------------------------------------
# DB lookup
# ---------------------------------------------------------------------------

def build_lookup(tiered_groups: list[dict]) -> dict[str, list[dict]]:
    """Build a normalised-template → list[group] lookup map from tiered DB."""
    lookup: dict[str, list[dict]] = {}
    for group in tiered_groups:
        key = normalize(group["stat_template"])
        lookup.setdefault(key, []).append(group)
    return lookup


# ---------------------------------------------------------------------------
# Tier matching
# ---------------------------------------------------------------------------

def _value_in_tier(item_values: list, tier: dict) -> bool:
    tier_vals = tier["values"]
    # Flat [min, max] range in DB but single rolled value on item
    # e.g. crit chance: tier_vals=[4.41, 5], item_values=[4.64]
    if (
        len(item_values) == 1
        and len(tier_vals) == 2
        and not isinstance(tier_vals[0], list)
        and not isinstance(tier_vals[1], list)
    ):
        return tier_vals[0] <= item_values[0] <= tier_vals[1]
    if len(item_values) != len(tier_vals):
        return False
    for iv, tv in zip(item_values, tier_vals):
        if isinstance(tv, list):
            if not (tv[0] <= iv <= tv[1]):
                return False
        else:
            if iv != tv:
                return False
    return True


def _match_tier(item_values: list, tiers: list[dict]) -> dict | None:
    for tier in tiers:
        if _value_in_tier(item_values, tier):
            return tier
    return None


# ---------------------------------------------------------------------------
# Identify
# ---------------------------------------------------------------------------

def identify(stat_lines: list[str], lookup: dict) -> list[dict]:
    """
    For each stat line, find all matching modifier groups and determine the
    exact tier rolled.

    Returns a list of result dicts, one per stat line:
        item_stat    – original stat line
        is_fractured – bool
        item_values  – extracted numeric values
        template     – normalised template
        matched      – list of groups where a tier was confirmed
        unmatched    – list of groups where template matched but no tier fits
    """
    results: list[dict] = []
    for line in stat_lines:
        key = normalize(line)
        groups = lookup.get(key, [])
        is_fractured = bool(re.search(r"\(fractured\)", line, re.IGNORECASE))
        item_values = extract_values(line)

        matched: list[dict] = []
        unmatched: list[dict] = []

        for group in groups:
            tier = _match_tier(item_values, group["tiers"])
            entry = {
                "section":       group["section"],
                "type":          group["type"],
                "family":        group["family"],
                "tags":          group["tags"],
                "stat_template": group["stat_template"],
                "num_tiers":     group["num_tiers"],
                "matched_tier":  tier,
                "all_tiers":     group["tiers"],
            }
            (matched if tier else unmatched).append(entry)

        results.append({
            "item_stat":    line,
            "is_fractured": is_fractured,
            "item_values":  item_values,
            "template":     key,
            "matched":      matched,
            "unmatched":    unmatched,
        })
    return results
