"""
test_fishing_engine.py
----------------------
Dry-run tests for _run_fishing — zero mouse / zero clipboard.

Each test scripts sequences of items and orb availability, then asserts
how many augs/annuls were consumed and whether the engine stopped correctly.

Run:
    .venv/Scripts/python -m pytest test_fishing_engine.py -v
"""

from collections import deque
import pytest

from crafting.strategies import _run_fishing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_ENTRY = {"type": "prefix", "stat_template": "fake target mod", "family": "FakeFamily"}
FAKE_TIER  = {"tier": 1}
WIN        = (FAKE_ENTRY, FAKE_TIER)
NO_WIN     = (None, None)


def _item(kind: str) -> dict:
    """Create a minimal item dict.  kind is just a label for debugging."""
    return {"name": kind, "stat_lines": [kind]}


def queue(*items):
    """Return a callable that pops from a scripted sequence."""
    q = deque(items)
    def _next():
        return q.popleft()
    return _next


def bool_queue(*bools):
    """Return a callable that pops bool values (for apply_aug / apply_annul)."""
    q = deque(bools)
    def _next():
        return q.popleft()
    return _next


def counting_bool(*, total: int):
    """Dispenser that returns True `total` times then False forever."""
    state = {"left": total}
    def _apply():
        if state["left"] > 0:
            state["left"] -= 1
            return True
        return False
    state["used"] = lambda: total - state["left"]
    return _apply


class Counter:
    """Wraps a callable and counts how many times it was called."""
    def __init__(self, fn):
        self._fn   = fn
        self.calls = 0
    def __call__(self, *a, **kw):
        self.calls += 1
        return self._fn(*a, **kw)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

class TestFishingEngine:

    def test_immediate_win_on_aug2(self, capsys):
        """
        AUG1 → acceptable
        AUG2 → win
        Expected: 2 augs, 0 annuls
        """
        apply_aug   = Counter(bool_queue(True, True))
        apply_annul = Counter(bool_queue())          # never called
        read_item   = queue(_item("GOOD"), _item("WIN"))

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: item["name"] in ("GOOD", "WIN"),
            check_win     = lambda item: WIN if item["name"] == "WIN" else NO_WIN,
        )

        assert apply_aug.calls   == 2
        assert apply_annul.calls == 0
        assert "WIN" in capsys.readouterr().out

    def test_bad_aug1_then_win(self, capsys):
        """
        AUG1 → bad  → annul
        AUG1 → good
        AUG2 → win
        Expected: 3 augs, 1 annul
        """
        apply_aug   = Counter(bool_queue(True, True, True))
        apply_annul = Counter(bool_queue(True))
        read_item   = queue(_item("BAD"), _item("GOOD"), _item("WIN"))

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: item["name"] in ("GOOD", "WIN"),
            check_win     = lambda item: WIN if item["name"] == "WIN" else NO_WIN,
        )

        assert apply_aug.calls   == 3
        assert apply_annul.calls == 1

    def test_good_mod_survives_annul_then_win(self, capsys):
        """
        AUG1 → good
        AUG2 → bad  → annul → POST: good survived  (lucky_streak=1)
        AUG2 → win
        Expected: 3 augs, 1 annul, "streak: 1" in output
        """
        apply_aug   = Counter(bool_queue(True, True, True))
        apply_annul = Counter(bool_queue(True))
        read_item   = queue(_item("GOOD"), _item("BAD"), _item("SURVIVED"), _item("WIN"))

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: item["name"] in ("GOOD", "SURVIVED", "WIN"),
            check_win     = lambda item: WIN if item["name"] == "WIN" else NO_WIN,
        )

        out = capsys.readouterr().out
        assert apply_aug.calls   == 3
        assert apply_annul.calls == 1
        assert "streak: 1" in out

    def test_good_mod_annulled_restart_then_win(self, capsys):
        """
        AUG1 → good
        AUG2 → bad  → annul → POST: gone (annul again for clean)
        AUG1 → good
        AUG2 → win
        Expected: 4 augs, 3 annuls
        """
        apply_aug   = Counter(bool_queue(True, True, True, True))
        apply_annul = Counter(bool_queue(True, True, True))
        read_item   = queue(
            _item("GOOD"),   # AUG1 first cycle
            _item("BAD"),    # AUG2 — not a win
            _item("GONE"),   # POST — mod gone
            _item("GOOD"),   # AUG1 second cycle
            _item("WIN"),    # AUG2 — win
        )

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: item["name"] in ("GOOD", "WIN"),
            check_win     = lambda item: WIN if item["name"] == "WIN" else NO_WIN,
        )

        assert apply_aug.calls   == 4
        assert apply_annul.calls == 2  # 1 for bad AUG2 + 1 for cleanup

    def test_out_of_augs_phase1(self, capsys):
        """No augs at all — should exit cleanly without crashing."""
        apply_aug   = Counter(bool_queue(False))
        apply_annul = Counter(bool_queue())
        read_item   = queue()

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: True,
            check_win     = lambda item: NO_WIN,
        )

        assert apply_aug.calls   == 1
        assert apply_annul.calls == 0
        assert "Out of Augmentation Orbs" in capsys.readouterr().out

    def test_out_of_augs_phase2(self, capsys):
        """Augs run out after first acceptable mod — should exit cleanly."""
        apply_aug   = Counter(bool_queue(True, False))  # 1 aug then gone
        apply_annul = Counter(bool_queue())
        read_item   = queue(_item("GOOD"))

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: True,
            check_win     = lambda item: NO_WIN,
        )

        assert apply_aug.calls   == 2
        assert apply_annul.calls == 0
        assert "Out of Augmentation Orbs" in capsys.readouterr().out

    def test_out_of_annuls_phase1(self, capsys):
        """Bad AUG1 but no annuls — should exit cleanly."""
        apply_aug   = Counter(bool_queue(True))
        apply_annul = Counter(bool_queue(False))
        read_item   = queue(_item("BAD"))

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: False,
            check_win     = lambda item: NO_WIN,
        )

        assert apply_aug.calls   == 1
        assert apply_annul.calls == 1
        assert "Out of Annulment Orbs" in capsys.readouterr().out

    def test_out_of_annuls_during_cleanup(self, capsys):
        """Good AUG1, bad AUG2, good mod annulled, cleanup annul fails."""
        apply_aug   = Counter(bool_queue(True, True))
        apply_annul = Counter(bool_queue(True, False))  # first ok, cleanup fails
        read_item   = queue(_item("GOOD"), _item("BAD"), _item("GONE"))

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: item["name"] == "GOOD",
            check_win     = lambda item: NO_WIN,
        )

        assert apply_aug.calls   == 2
        assert apply_annul.calls == 2
        assert "Out of Annulment Orbs" in capsys.readouterr().out

    def test_lucky_streak_tracking(self, capsys):
        """
        Mod survives 3 consecutive annuls before final win.
        best_streak should be 3.
        """
        apply_aug   = Counter(bool_queue(True, True, True, True, True))
        apply_annul = Counter(bool_queue(True, True, True))
        read_item   = queue(
            _item("GOOD"),      # AUG1
            _item("BAD"),       # AUG2 cycle 1
            _item("SURVIVED"),  # POST — streak 1
            _item("BAD"),       # AUG2 cycle 2
            _item("SURVIVED"),  # POST — streak 2
            _item("BAD"),       # AUG2 cycle 3
            _item("SURVIVED"),  # POST — streak 3
            _item("WIN"),       # AUG2 cycle 4 — win
        )

        _run_fishing(
            apply_aug     = apply_aug,
            apply_annul   = apply_annul,
            read_item     = read_item,
            is_acceptable = lambda item: item["name"] in ("GOOD", "SURVIVED", "WIN"),
            check_win     = lambda item: WIN if item["name"] == "WIN" else NO_WIN,
        )

        out = capsys.readouterr().out
        assert "best: 3" in out
        assert apply_aug.calls   == 5   # AUG1 + 4×AUG2
        assert apply_annul.calls == 3


    def test_transmute_seed_then_augment_win(self, capsys):
        """
        TRANS -> acceptable
        AUG   -> win
        Expected: 1 transmute, 1 aug, 0 annuls
        """
        apply_trans = Counter(bool_queue(True))
        apply_aug = Counter(bool_queue(True))
        apply_annul = Counter(bool_queue())
        read_item = queue(_item("GOOD"), _item("WIN"))

        _run_fishing(
            apply_seed=apply_trans,
            apply_aug=apply_aug,
            apply_annul=apply_annul,
            read_item=read_item,
            is_acceptable=lambda item: item["name"] in ("GOOD", "WIN"),
            check_win=lambda item: WIN if item["name"] == "WIN" else NO_WIN,
            seed_label="TRANS",
            seed_out_message="Out of Orbs of Transmutation.",
            aug_label="AUG",
            aug_out_message="Out of Augmentation Orbs.",
        )

        out = capsys.readouterr().out
        assert apply_trans.calls == 1
        assert apply_aug.calls == 1
        assert apply_annul.calls == 0
        assert "TRANS" in out

    def test_restart_from_surviving_magic_item_without_cleanup(self, capsys):
        """
        SEED -> good
        AUG  -> bad
        POST -> bad survivor
        restart directly from magic survivor, no cleanup annul
        """
        apply_aug = Counter(bool_queue(True))
        apply_annul = Counter(bool_queue(True, False))
        read_item = queue(
            _item("GOOD"),
            _item("BAD"),
            _item("BAD_SURVIVOR"),
            _item("BAD_SURVIVOR"),
        )

        _run_fishing(
            apply_seed=lambda: None,
            apply_aug=apply_aug,
            apply_annul=apply_annul,
            read_item=read_item,
            is_acceptable=lambda item: item["name"] == "GOOD",
            check_win=lambda item: NO_WIN,
            seed_label="SEED",
            aug_label="AUG",
            cleanup_on_miss=False,
        )

        out = capsys.readouterr().out
        assert apply_aug.calls == 1
        assert apply_annul.calls == 2
        assert "surviving magic item" in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
