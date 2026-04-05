"""
windows/screen.py
-----------------
Screen utilities: clipboard read/write and screenshots.
Uses pyperclip for clipboard access — no window creation, no focus stealing.
"""

import pyperclip
import pyautogui


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def read_clipboard() -> str:
    """Return the current clipboard text (empty string on failure)."""
    try:
        return pyperclip.paste()
    except Exception:
        return ""


def clear_clipboard() -> None:
    """Clear the clipboard so stale data is not mistaken for a new item."""
    pyperclip.copy("")


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------

def screenshot(region: tuple[int, int, int, int] | None = None):
    """
    Take a screenshot and return a PIL Image.

    region  (left, top, width, height) in pixels; None = full screen.
    """
    return pyautogui.screenshot(region=region)
