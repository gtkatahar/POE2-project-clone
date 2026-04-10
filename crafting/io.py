"""Low-level in-game input/output helpers."""

import time

import pyautogui as _pag

from item_parsing.parser import parse_item_text
from windows.inventory import cell_center
from windows.keyboard import hotkey
from windows.mouse import move_to, right_click
from windows.screen import clear_clipboard, read_clipboard


def is_item_clipboard_text(text: str) -> bool:
    """Return True when clipboard text looks like a POE item block."""
    return bool(text) and ("Item Class:" in text or "Rarity:" in text)


def apply_orb_to_target(cx: int, cy: int, tx: int, ty: int) -> None:
    """Right-click orb stack at (cx, cy) then left-click target at (tx, ty)."""
    move_to(cx, cy, duration=0.1)
    time.sleep(0.05)
    right_click()
    time.sleep(0.05)
    move_to(tx, ty, duration=0.1)
    time.sleep(0.05)
    _pag.click(button="left")
    time.sleep(0.15)


def read_cell(col: int, row: int, hover_delay: float, copy_delay: float) -> str:
    """Hover over a cell and return the raw Ctrl+C clipboard text."""
    x, y = cell_center(col, row)
    clear_clipboard()
    move_to(x, y, duration=0.0)
    time.sleep(hover_delay)
    hotkey("ctrl", "c")
    time.sleep(copy_delay)
    return read_clipboard().strip()


def read_target(hover_delay: float, copy_delay: float) -> dict:
    """Parse and return the item sitting at inventory cell [0, 0]."""
    return parse_item_text(read_cell(0, 0, hover_delay, copy_delay))


def safe_click(x: int, y: int) -> None:
    """Click with short delays to reduce dropped in-game input."""
    move_to(x, y, duration=0.2)
    time.sleep(0.2)
    _pag.click(button="left")
    time.sleep(0.3)
