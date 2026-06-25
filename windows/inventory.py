"""
windows/inventory.py
--------------------
Scan every cell in the player inventory by hovering and copying item text.

HOW IT WORKS
------------
1.  The player opens their inventory in-game (default key: 'I').
2.  `scan_inventory()` moves the mouse to each of the 12×5 cells one by one.
3.  For every cell it does Ctrl+C → reads clipboard → parses the pasted text.
4.  Items that span multiple cells (e.g. 2×2 flasks) will copy the same text
    more than once; duplicates are silently dropped via a dedup set.

CALIBRATION
-----------
Grid layout is stored in  data/inventory_config.json  and loaded at runtime.
Run  py calibrate.py  to re-measure and overwrite the file automatically.
Auto-scaling is applied to any resolution at runtime.
"""

import json
import time
from pathlib import Path

from .mouse import move_to, get_screen_size
from .keyboard import hotkey
from .screen import read_clipboard, clear_clipboard

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "inventory_config.json"

_DEFAULTS = {
    "base_w": 2560, "base_h": 1440,
    "origin_x": 1694, "origin_y": 787,
    "cell_w": 73, "cell_h": 69,
    "grid_cols": 12, "grid_rows": 5,
}


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        return {**_DEFAULTS, **json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))}
    return _DEFAULTS.copy()


# Seconds to wait after moving before copying (tooltip load time)
HOVER_DELAY = 0.05

# Seconds to wait after Ctrl+C before reading clipboard
COPY_DELAY = 0.06


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _scale_coords() -> tuple[int, int, int, int]:
    """Scale the configured grid constants to the actual screen resolution."""
    cfg = _load_config()
    sw, sh = get_screen_size()
    sx, sy = sw / cfg["base_w"], sh / cfg["base_h"]
    origin_x = round(cfg["origin_x"] * sx)
    origin_y = round(cfg["origin_y"] * sy)
    cell_w   = round(cfg["cell_w"]   * sx)
    cell_h   = round(cfg["cell_h"]   * sy)
    return origin_x, origin_y, cell_w, cell_h


def cell_center(col: int, row: int) -> tuple[int, int]:
    """Return the screen (x, y) centre for the given inventory cell.
    origin is the centre of cell (0,0); cell_w/h is the centre-to-centre step.
    """
    ox, oy, cw, ch = _scale_coords()
    return ox + col * cw, oy + row * ch


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

def _is_duplicate_cell(grid: list[list[str | None]], row: int, col: int, text: str) -> bool:
    """Treat adjacent identical non-stackable text as the same multi-cell item."""
    if "stack size:" in text.lower():
        return False
    return (
        (col > 0 and grid[row][col - 1] == text)
        or (row > 0 and grid[row - 1][col] == text)
    )


def scan_inventory(
    on_item=None,
    hover_delay: float = HOVER_DELAY,
    copy_delay: float   = COPY_DELAY,
    verbose: bool       = False,
    debug: bool         = False,
) -> dict:
    """
    Hover over every inventory cell, copy item text with Ctrl+C, and return
    a stats dict with the full breakdown of what was found.

    Parameters
    ----------
    on_item : callable(col, row, text) | None
        Optional callback invoked for each unique item text found.
    hover_delay : float
        Seconds to wait after moving the mouse before pressing Ctrl+C.
    copy_delay : float
        Seconds to wait after Ctrl+C before reading the clipboard.
    verbose : bool
        Print the status of every cell while scanning.

    Returns
    -------
    dict with keys:
        items    list of unique raw clipboard strings
        empty    number of empty cells
        dupes    number of duplicate cells (multi-cell items)
        found    number of unique items
        total    total cells scanned
    """
    items: list[dict] = []
    empty = 0
    dupes = 0
    cfg = _load_config()
    rows, cols = cfg["grid_rows"], cfg["grid_cols"]
    grid: list[list[str | None]] = [[None] * cols for _ in range(rows)]

    for row in range(rows):
        for col in range(cols):
            x, y = cell_center(col, row)

            clear_clipboard()
            move_to(x, y, duration=0.0)
            time.sleep(hover_delay)

            hotkey("ctrl", "c")
            time.sleep(copy_delay)

            text = read_clipboard().strip()

            if not text or ("Item Class:" not in text and "Rarity:" not in text):
                empty += 1
                if verbose:
                    print(f"  [{col:02d},{row:02d}] px=({x},{y}) empty")
                if debug and text:
                    print(f"  [{col:02d},{row:02d}] FILTERED OUT — raw clipboard:")
                    print("    " + text[:200].replace("\n", "\n    "))
                continue

            grid[row][col] = text
            if _is_duplicate_cell(grid, row, col, text):
                dupes += 1
                if verbose:
                    print(f"  [{col:02d},{row:02d}] px=({x},{y}) duplicate")
                continue

            items.append({"col": col, "row": row, "text": text})

            if verbose:
                # Extract a short name for display
                name = next(
                    (l.strip() for l in text.splitlines()
                     if l.strip() and not l.lower().startswith(("item class:", "rarity:"))),
                    "item"
                )
                print(f"  [{col:02d},{row:02d}] px=({x},{y}) {name}")

            if on_item is not None:
                on_item(col, row, text)

    total = cols * rows
    return {"items": items, "empty": empty, "dupes": dupes, "found": len(items), "total": total, "grid": grid}



# ---------------------------------------------------------------------------
# Calibration helper
# ---------------------------------------------------------------------------

def calibrate() -> None:
    """
    Calibrate by hovering over cell CENTRES (easier and more accurate than corners).
    Click centre of (0,0), centre of (cols-1, 0), centre of (0, rows-1).
    Span is divided by (n-1) to get centre-to-centre step — no drift.
    Saves the result to data/inventory_config.json automatically.

    Run with:  py calibrate.py
    """
    import pyautogui

    cfg = _load_config()
    cols = cfg["grid_cols"]
    rows = cfg["grid_rows"]

    print("=" * 60)
    print(" POE2 Inventory Grid Calibration")
    print("=" * 60)
    print("Hover over the CENTRE of each indicated cell, then press Enter.")
    print()

    print(f"[1/3] CENTRE of the FIRST cell  (col 0, row 0)")
    input("      Press Enter when ready… ")
    x0, y0 = pyautogui.position()
    print(f"      → ({x0}, {y0})\n")

    print(f"[2/3] CENTRE of the LAST cell in row 0  (col {cols-1}, row 0)")
    input("      Press Enter when ready… ")
    x_last, _ = pyautogui.position()
    cell_w = round((x_last - x0) / (cols - 1))
    print(f"      → ({x_last}, {_})  span={x_last-x0}px  cell_w={cell_w}px\n")

    print(f"[3/3] CENTRE of the LAST cell in col 0  (col 0, row {rows-1})")
    input("      Press Enter when ready… ")
    _, y_last = pyautogui.position()
    cell_h = round((y_last - y0) / (rows - 1))
    print(f"      → ({_}, {y_last})  span={y_last-y0}px  cell_h={cell_h}px\n")

    sw, sh = pyautogui.size()

    config = {
        "base_w":    sw,
        "base_h":    sh,
        "origin_x":  x0,
        "origin_y":  y0,
        "cell_w":    cell_w,
        "cell_h":    cell_h,
        "grid_cols": cols,
        "grid_rows": rows,
    }

    _CONFIG_PATH.parent.mkdir(exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )

    print("=" * 60)
    print(f" Saved to {_CONFIG_PATH}")
    print("=" * 60)
    print(f"  resolution : {sw}×{sh}")
    print(f"  origin     : ({x0}, {y0})")
    print(f"  cell size  : {cell_w}×{cell_h}")


def calibrate_from_box(x1: int, y1: int, x2: int, y2: int) -> dict:
    """
    Calibrate from a single drag-box enclosing the OUTER edges of the whole
    grid (top-left corner of cell (0,0) to bottom-right corner of the last
    cell). Used by the GUI's drag-to-select calibration overlay.
    Saves the result to data/inventory_config.json automatically.
    """
    cfg = _load_config()
    cols = cfg["grid_cols"]
    rows = cfg["grid_rows"]

    left, top = min(x1, x2), min(y1, y2)
    width, height = abs(x2 - x1), abs(y2 - y1)
    cell_w = round(width / cols)
    cell_h = round(height / rows)

    sw, sh = get_screen_size()

    config = {
        "base_w":    sw,
        "base_h":    sh,
        "origin_x":  left + cell_w // 2,
        "origin_y":  top + cell_h // 2,
        "cell_w":    cell_w,
        "cell_h":    cell_h,
        "grid_cols": cols,
        "grid_rows": rows,
    }

    _CONFIG_PATH.parent.mkdir(exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    return config


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json
    from pathlib import Path

    # Ensure the project root is on sys.path when run via `py -m windows.inventory`
    _project_root = Path(__file__).parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

    from item_parsing.parser import parse_item_text
    from item_parsing.identifier import build_lookup, identify
    from item_parsing.display import build_simple_result

    args = sys.argv[1:]

    # --- calibrate mode ---
    if "--calibrate" in args:
        calibrate()
        sys.exit(0)

    # --- scan mode ---
    slug = "Talismans"
    for i, a in enumerate(args):
        if a == "--slug" and i + 1 < len(args):
            slug = args[i + 1]

    data_dir = Path(__file__).parent.parent / "data"
    db_path  = data_dir / f"{slug.lower()}_modifiers_tiered.json"
    if not db_path.exists():
        print(f"ERROR: modifier database not found at {db_path}")
        print(f"Run:  python identify.py --slug {slug}  to generate it first.")
        sys.exit(1)

    db     = json.loads(db_path.read_text(encoding="utf-8"))
    lookup = build_lookup(db["modifiers"])
    print(f"Loaded {db['total_groups']} modifier groups.\n")

    # Countdown so you have time to switch to the game
    print("Switch to POE2 and OPEN YOUR INVENTORY.")
    for i in range(3, 0, -1):
        print(f"  Starting in {i}…")
        time.sleep(1)
    print("Scanning…\n")

    results = []

    def _on_item(col, row, text):
        item    = parse_item_text(text)
        matches = identify(item["stat_lines"], lookup)
        entry   = build_simple_result(item, matches)
        results.append(entry)
        name = item.get("name") or item.get("base") or "Unknown"
        n_matched = sum(1 for r in matches if r["matched"])
        print(f"  [{col:02d},{row:02d}] {name}  ({n_matched}/{len(matches)} mods matched)")

    scan_inventory(on_item=_on_item)

    print(f"\nDone — {len(results)} unique items found.")

    # Save results
    out_path = Path("inventory_scan.json")
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results saved to {out_path}")
