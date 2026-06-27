"""Expected-cost estimators for weighted crafting strategies."""

from __future__ import annotations

from dataclasses import dataclass

from crafting.targets import mod_entry_matches


@dataclass(frozen=True)
class CostVector:
    transmutes: float = 0.0
    augs: float = 0.0
    annuls: float = 0.0

    def __add__(self, other: "CostVector") -> "CostVector":
        return CostVector(
            transmutes=self.transmutes + other.transmutes,
            augs=self.augs + other.augs,
            annuls=self.annuls + other.annuls,
        )

    def __sub__(self, other: "CostVector") -> "CostVector":
        return CostVector(
            transmutes=self.transmutes - other.transmutes,
            augs=self.augs - other.augs,
            annuls=self.annuls - other.annuls,
        )

    def scale(self, factor: float) -> "CostVector":
        return CostVector(
            transmutes=self.transmutes * factor,
            augs=self.augs * factor,
            annuls=self.annuls * factor,
        )


def _zero() -> CostVector:
    return CostVector()


def _transmute_cost() -> CostVector:
    return CostVector(transmutes=1.0)


def _aug_cost() -> CostVector:
    return CostVector(augs=1.0)


def _annul_cost() -> CostVector:
    return CostVector(annuls=1.0)


def _matches_entry(group: dict, tier: dict, entry: dict) -> bool:
    return (
        group["type"].lower() == entry["type"].lower()
        and mod_entry_matches(
            {
                "family": group["family"],
                "section_key": group.get("section_key", "normal"),
                "matched_tier": tier,
            },
            entry,
        )
    )


def _pool_weights(db_groups: list[dict], item_level: int, target_entries: list[dict], keeper_entries: list[dict]) -> dict:
    pools = {
        "prefix": {"target": 0.0, "keeper": 0.0, "bad": 0.0, "total": 0.0},
        "suffix": {"target": 0.0, "keeper": 0.0, "bad": 0.0, "total": 0.0},
    }

    for group in db_groups:
        group_type = group["type"].lower()
        if group_type not in pools:
            continue
        for tier in group["tiers"]:
            if tier["min_ilvl"] > item_level:
                continue
            weight = float(tier["weight"])
            pools[group_type]["total"] += weight
            if any(_matches_entry(group, tier, entry) for entry in target_entries):
                pools[group_type]["target"] += weight
            elif any(_matches_entry(group, tier, entry) for entry in keeper_entries):
                pools[group_type]["keeper"] += weight
            else:
                pools[group_type]["bad"] += weight

    return pools


def _probabilities(pool: dict) -> dict:
    total = pool["total"]
    if total <= 0:
        return {"target": 0.0, "keeper": 0.0, "bad": 0.0}
    return {
        "target": pool["target"] / total,
        "keeper": pool["keeper"] / total,
        "bad": pool["bad"] / total,
    }


def _combined_probabilities(prefix: dict, suffix: dict) -> dict:
    total = prefix["total"] + suffix["total"]
    if total <= 0:
        return {"tp": 0.0, "ts": 0.0, "kp": 0.0, "ks": 0.0, "bad": 1.0}
    return {
        "tp": prefix["target"] / total,
        "ts": suffix["target"] / total,
        "kp": prefix["keeper"] / total,
        "ks": suffix["keeper"] / total,
        "bad": (prefix["bad"] + suffix["bad"]) / total,
    }


def _solve_linear_system(matrix: list[list[float]], rhs: list[CostVector]) -> list[CostVector]:
    size = len(matrix)
    cols = []
    for attr in ("transmutes", "augs", "annuls"):
        augmented = [
            [float(matrix[row][col]) for col in range(size)] + [getattr(rhs[row], attr)]
            for row in range(size)
        ]

        for pivot in range(size):
            best = max(range(pivot, size), key=lambda row: abs(augmented[row][pivot]))
            augmented[pivot], augmented[best] = augmented[best], augmented[pivot]
            pivot_val = augmented[pivot][pivot]
            if abs(pivot_val) < 1e-12:
                raise ValueError("Singular expected-cost system.")
            for col in range(pivot, size + 1):
                augmented[pivot][col] /= pivot_val
            for row in range(size):
                if row == pivot:
                    continue
                factor = augmented[row][pivot]
                if factor == 0:
                    continue
                for col in range(pivot, size + 1):
                    augmented[row][col] -= factor * augmented[pivot][col]

        cols.append([augmented[row][size] for row in range(size)])

    return [
        CostVector(
            transmutes=cols[0][idx],
            augs=cols[1][idx],
            annuls=cols[2][idx],
        )
        for idx in range(size)
    ]


def _classify_current_magic_item(
    item: dict,
    identify_matches,
    target_entries: list[dict],
    keeper_entries: list[dict],
) -> str | None:
    stat_lines = item.get("stat_lines", [])
    if not stat_lines:
        return "M0"
    if len(stat_lines) != 1:
        return None

    for result in identify_matches(stat_lines):
        # A stat line may match multiple groups (e.g. normal T3 and
        # breach_caster T1 share the same rolled value).  Check every
        # candidate so that target/keeper entries from any section are found.
        candidates = result["matched"] or result["unmatched"]
        if not candidates:
            return None

        for candidate in candidates:
            lt = candidate["type"].lower()
            lf = candidate["family"]
            for entry in target_entries:
                if (
                    entry["type"].lower() == lt
                    and entry["family"] == lf
                    and candidate["section_key"] == entry.get("section_key", "normal")
                ):
                    return "TP" if lt == "prefix" else "TS"
            for entry in keeper_entries:
                if (
                    entry["type"].lower() == lt
                    and entry["family"] == lf
                    and candidate["section_key"] == entry.get("section_key", "normal")
                ):
                    return "KP" if lt == "prefix" else "KS"

        # None of the interpretations matched a target or keeper entry.
        lt = candidates[0]["type"].lower()
        return "BP" if lt == "prefix" else "BS"

    return None


def estimate_aug_annul_5050_cost(
    item: dict,
    db_groups: list[dict],
    identify_matches,
    target_entries: list[dict],
    fifty_fifty_entries: list[dict],
) -> dict | None:
    """
    Estimate expected average orb usage to stop for the Aug + Annul 50-50 strategy.

    The current version supports the normal start states used by the workflow:
    white base, magic base with 0 mods, or magic base with 1 mod.
    """
    item_level = item.get("item_level")
    rarity = (item.get("rarity") or "").lower()
    if item_level is None or rarity not in {"normal", "magic"}:
        return None

    pools = _pool_weights(db_groups, item_level, target_entries, fifty_fifty_entries)
    prefix_probs = _probabilities(pools["prefix"])
    suffix_probs = _probabilities(pools["suffix"])
    all_probs = _combined_probabilities(pools["prefix"], pools["suffix"])

    state_names = ["M0", "TP", "TS", "KP", "KS"]
    index = {name: idx for idx, name in enumerate(state_names)}
    matrix = [[0.0 for _ in state_names] for _ in state_names]
    rhs = [_zero() for _ in state_names]

    # M0: augment a seed mod from an empty magic item.
    matrix[index["M0"]][index["M0"]] = 1.0 - all_probs["bad"]
    matrix[index["M0"]][index["TP"]] = -all_probs["tp"]
    matrix[index["M0"]][index["TS"]] = -all_probs["ts"]
    matrix[index["M0"]][index["KP"]] = -all_probs["kp"]
    matrix[index["M0"]][index["KS"]] = -all_probs["ks"]
    rhs[index["M0"]] = _aug_cost() + _annul_cost().scale(all_probs["bad"])

    # TP / TS: already have a target seed; any acceptable second mod wins.
    for state_name, opposite in (("TP", suffix_probs), ("TS", prefix_probs)):
        bad = opposite["bad"]
        row = index[state_name]
        matrix[row][row] = 1.0 - 0.5 * bad
        matrix[row][index["M0"]] = -0.5 * bad
        rhs[row] = _aug_cost() + _annul_cost().scale(1.5 * bad)

    # KP / KS: need a target on the second mod or survive/reset into a new keeper state.
    for state_name, same_state, other_state, opposite in (
        ("KP", "KP", "KS", suffix_probs),
        ("KS", "KS", "KP", prefix_probs),
    ):
        keep = opposite["keeper"]
        bad = opposite["bad"]
        row = index[state_name]
        matrix[row][row] = 1.0 - 0.5 * (keep + bad)
        matrix[row][index[other_state]] = -0.5 * keep
        matrix[row][index["M0"]] = -0.5 * bad
        rhs[row] = _aug_cost() + _annul_cost().scale(keep + 1.5 * bad)

    solved = {
        name: value
        for name, value in zip(state_names, _solve_linear_system(matrix, rhs), strict=True)
    }

    current_state: str | None
    start_note: str
    if rarity == "normal":
        current_state = "WHITE"
        start_note = "white base -> transmute once, then magic flow"
        expected = (
            _transmute_cost()
            + solved["TP"].scale(all_probs["tp"])
            + solved["TS"].scale(all_probs["ts"])
            + solved["KP"].scale(all_probs["kp"])
            + solved["KS"].scale(all_probs["ks"])
            + (_annul_cost() + solved["M0"]).scale(all_probs["bad"])
        )
    else:
        current_state = _classify_current_magic_item(
            item=item,
            identify_matches=identify_matches,
            target_entries=target_entries,
            keeper_entries=fifty_fifty_entries,
        )
        if current_state is None:
            return None
        if current_state == "M0":
            start_note = "magic base with 0 mods"
            expected = solved["M0"]
        elif current_state == "TP":
            start_note = "magic base with target seed mod"
            expected = solved["TP"]
        elif current_state == "TS":
            start_note = "magic base with target seed mod"
            expected = solved["TS"]
        elif current_state == "KP":
            start_note = "magic base with 50-50 seed mod"
            expected = solved["KP"]
        elif current_state == "KS":
            start_note = "magic base with 50-50 seed mod"
            expected = solved["KS"]
        elif current_state in {"BP", "BS"}:
            start_note = "magic base with bad seed mod"
            expected = _annul_cost() + solved["M0"]
        else:
            return None

    return {
        "start_state": current_state,
        "start_note": start_note,
        "expected": expected,
        "probabilities": {
            "empty_magic_seed": all_probs,
            "prefix_pool": prefix_probs,
            "suffix_pool": suffix_probs,
        },
    }
