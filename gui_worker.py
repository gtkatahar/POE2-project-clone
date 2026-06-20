"""Background QThread workers for scan and crafting operations."""

import json
import re
import sys
import time
import threading
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, QObject


ROOT_DIR = Path(__file__).resolve().parent


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


class StdoutRouter(QObject):
    """Redirect sys.stdout to a Qt signal so worker output appears in the UI."""
    line_written = pyqtSignal(str)

    def write(self, text: str) -> None:
        clean = _ANSI_RE.sub("", text)
        stripped = clean.rstrip("\n")
        if stripped:
            self.line_written.emit(stripped)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


class _StopCrafting(Exception):
    pass


class ScanWorker(QThread):
    """Scans the full inventory for crafting materials and saves crafting_mats.json."""

    log_line = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    minimize_window = pyqtSignal()
    restore_window = pyqtSignal()

    def __init__(self, countdown: int) -> None:
        super().__init__()
        self._countdown = countdown

    def run(self) -> None:
        # Import before replacing sys.stdout — click checks isatty() on first import
        from crafting.materials import extract_description, extract_stack_size
        from item_parsing.parser import parse_item_text
        from windows.inventory import scan_inventory

        router = StdoutRouter()
        router.line_written.connect(self.log_line)
        old_stdout = sys.stdout
        sys.stdout = router
        try:
            self.minimize_window.emit()
            self.log_line.emit("Switch to POE2 and OPEN YOUR INVENTORY.")
            for i in range(self._countdown, 0, -1):
                self.log_line.emit(f"  Starting in {i}...")
                time.sleep(1)
            self.log_line.emit("Scanning...\n")

            mat_counts: dict[str, dict] = {}

            def on_mat(col: int, row: int, text: str) -> None:
                item = parse_item_text(text)
                name = item.get("name") or item.get("base") or "Unknown"
                count, max_stack = extract_stack_size(item["stat_lines"])
                desc = extract_description(text)
                if name in mat_counts:
                    mat_counts[name]["count"] += count
                else:
                    mat_counts[name] = {
                        "count": count,
                        "max_stack": max_stack,
                        "description": desc,
                    }

            scan_inventory(on_item=on_mat)

            sorted_mats = dict(
                sorted(mat_counts.items(), key=lambda x: x[1]["count"], reverse=True)
            )

            out = ROOT_DIR / "crafting_mats.json"
            out.write_text(json.dumps(sorted_mats, indent=2, ensure_ascii=False), encoding="utf-8")

            self.log_line.emit(f"\nFound {len(sorted_mats)} material types.")
            self.log_line.emit(f"Saved -> crafting_mats.json")
            self.finished.emit(sorted_mats)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            sys.stdout = old_stdout
            self.restore_window.emit()


class CraftWorker(QThread):
    """Executes a crafting strategy in the background with stop support."""

    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool)
    error = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    mats_scanned = pyqtSignal(dict)
    minimize_window = pyqtSignal()
    restore_window = pyqtSignal()

    def __init__(self, strategy: str, target_data: dict, countdown: int) -> None:
        super().__init__()
        self._strategy = strategy
        self._target_data = target_data
        self._countdown = countdown
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        # Import before replacing sys.stdout — click checks isatty() on first import
        import crafting.strategies as _strats
        import crafting.io as _io
        from crafting.targets import load_target_mods
        from crafting.materials import combined_scan_for_mats
        from item_parsing.identifier import identify
        from crafting.strategies import strategy_chaos, strategy_aug_annul, strategy_aug_annul_5050

        router = StdoutRouter()
        router.line_written.connect(self.log_line)
        old_stdout = sys.stdout
        sys.stdout = router

        stop_event = self._stop_event
        original_orb_apply = _strats.OrbDispenser.apply
        original_read_target = _io.read_target

        def patched_orb_apply(self_disp: object) -> bool:
            if stop_event.is_set():
                return False
            return original_orb_apply(self_disp)

        def patched_read_target(hover_delay: float, copy_delay: float) -> dict:
            if stop_event.is_set():
                raise _StopCrafting("Stopped by user")
            return original_read_target(hover_delay, copy_delay)

        _strats.OrbDispenser.apply = patched_orb_apply
        _io.read_target = patched_read_target
        _strats.read_target = patched_read_target

        try:
            self.minimize_window.emit()
            self.log_line.emit("Switch to POE2 and put your base item at cell [0,0].")
            for i in range(self._countdown, 0, -1):
                self.log_line.emit(f"  Starting in {i}...")
                time.sleep(1)

            self.status_changed.emit("Scanning inventory...")
            self.log_line.emit("Scanning inventory for materials...\n")

            target_entries, fifty_fifty_entries, mod_lookup, slug, _ = \
                load_target_mods(self._target_data)

            def identify_matches(stat_lines: list) -> list:
                results = identify(stat_lines, mod_lookup)
                unknown = [
                    r["item_stat"]
                    for r in results
                    if not r["matched"] and not r["unmatched"]
                ]
                if unknown:
                    lines = "\n  • ".join(unknown)
                    raise RuntimeError(
                        f"Unrecognised mod(s) — cannot continue crafting:\n  • {lines}\n\n"
                        "Check that the correct item type / modifier DB is loaded, "
                        "or update the data file."
                    )
                return results

            verbose = self._strategy == "scan_only"
            found_mats, found_bases, empty_slots, catalog = combined_scan_for_mats(
                slug, 0.05, 0.06, verbose
            )

            sorted_catalog = dict(
                sorted(catalog.items(), key=lambda x: x[1]["count"], reverse=True)
            )
            out = ROOT_DIR / "crafting_mats.json"
            out.write_text(
                json.dumps(sorted_catalog, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.mats_scanned.emit(sorted_catalog)

            if self._strategy == "scan_only":
                self.log_line.emit(f"Target: {slug}  ({len(target_entries)} mod(s))")
                self.log_line.emit(f"\nFound {len(found_mats)} mat stacks, {len(found_bases)} base(s), {len(empty_slots)} empty slots.")
                self.finished.emit(True)
                return

            mat_summary = {}
            for m in found_mats:
                mat_summary[m["name"]] = mat_summary.get(m["name"], 0) + m["count"]
            for name, cnt in mat_summary.items():
                self.log_line.emit(f"  {name}: {cnt}")
            self.log_line.emit("")

            self.status_changed.emit("Running strategy...")

            success = False
            if self._strategy == "chaos":
                success = strategy_chaos(found_mats, 0.05, 0.06, target_entries, identify_matches)
            elif self._strategy == "augment_annul":
                success = strategy_aug_annul(found_mats, 0.05, 0.06, target_entries, identify_matches)
            elif self._strategy == "aug_annul_5050":
                success = strategy_aug_annul_5050(
                    found_mats, 0.05, 0.06, target_entries, identify_matches, fifty_fifty_entries
                )

            self.finished.emit(success)

        except _StopCrafting:
            self.log_line.emit("\nStopped by user.")
            self.finished.emit(False)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            sys.stdout = old_stdout
            _strats.OrbDispenser.apply = original_orb_apply
            _io.read_target = original_read_target
            _strats.read_target = original_read_target
            self.restore_window.emit()
