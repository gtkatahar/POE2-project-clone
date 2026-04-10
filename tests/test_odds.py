import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from crafting.odds import estimate_aug_annul_5050_cost


TARGET_PREFIX = {
    "type": "Prefix",
    "family": "target_prefix",
    "stat_template": "target_prefix",
    "min_tier": 1,
}
TARGET_SUFFIX = {
    "type": "Suffix",
    "family": "target_suffix",
    "stat_template": "target_suffix",
    "min_tier": 1,
}


DB_GROUPS = [
    {
        "section": "Base Modifiers",
        "type": "Prefix",
        "family": "target_prefix",
        "tiers": [{"tier": 1, "min_ilvl": 1, "weight": 100}],
    },
    {
        "section": "Base Modifiers",
        "type": "Suffix",
        "family": "target_suffix",
        "tiers": [{"tier": 1, "min_ilvl": 1, "weight": 100}],
    },
]


def identify_matches(stat_lines: list[str]) -> list[dict]:
    mapping = {
        "target_prefix": {"type": "Prefix", "family": "target_prefix"},
        "target_suffix": {"type": "Suffix", "family": "target_suffix"},
    }
    results = []
    for line in stat_lines:
        matched = []
        if line in mapping:
            matched.append(
                {
                    "type": mapping[line]["type"],
                    "family": mapping[line]["family"],
                    "matched_tier": {"tier": 1},
                }
            )
        results.append({"matched": matched, "unmatched": []})
    return results


def test_estimate_5050_from_white_with_only_target_pools():
    estimate = estimate_aug_annul_5050_cost(
        item={"rarity": "Normal", "item_level": 1, "stat_lines": []},
        db_groups=DB_GROUPS,
        identify_matches=identify_matches,
        target_entries=[TARGET_PREFIX, TARGET_SUFFIX],
        fifty_fifty_entries=[],
    )

    expected = estimate["expected"]
    assert round(expected.transmutes, 6) == 1.0
    assert round(expected.augs, 6) == 1.0
    assert round(expected.annuls, 6) == 0.0


def test_estimate_5050_from_empty_magic_with_only_target_pools():
    estimate = estimate_aug_annul_5050_cost(
        item={"rarity": "Magic", "item_level": 1, "stat_lines": []},
        db_groups=DB_GROUPS,
        identify_matches=identify_matches,
        target_entries=[TARGET_PREFIX, TARGET_SUFFIX],
        fifty_fifty_entries=[],
    )

    expected = estimate["expected"]
    assert round(expected.transmutes, 6) == 0.0
    assert round(expected.augs, 6) == 2.0
    assert round(expected.annuls, 6) == 0.0
