"""
windows/mouse.py
----------------
Mouse control via pyautogui.

SAFETY: pyautogui.FAILSAFE is enabled — move the mouse to the BOTTOM-RIGHT
corner of the screen at any time to immediately abort execution.
"""

import time

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# Move failsafe trigger to bottom-right corner instead of top-left
_w, _h = pyautogui.size()
pyautogui.FAILSAFE_POINTS = [(_w - 1, _h - 1)]


def get_position() -> tuple[int, int]:
    """Return the current mouse (x, y) position."""
    return pyautogui.position()


def get_screen_size() -> tuple[int, int]:
    """Return the screen resolution as (width, height)."""
    return pyautogui.size()


def move_to(x: int, y: int, duration: float = 0.3) -> None:
    """Move the mouse to an absolute position."""
    pyautogui.moveTo(x, y, duration=duration)


def move_relative(dx: int, dy: int, duration: float = 0.3) -> None:
    """Move the mouse relative to its current position."""
    pyautogui.moveRel(dx, dy, duration=duration)


def click(x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> None:
    """Click at the given position (or current position if None)."""
    pyautogui.click(x=x, y=y, button=button, clicks=clicks)


def double_click(x: int = None, y: int = None) -> None:
    """Double-click at the given position."""
    pyautogui.doubleClick(x=x, y=y)


def right_click(x: int = None, y: int = None) -> None:
    """Right-click at the given position."""
    pyautogui.rightClick(x=x, y=y)


def shift_click(x: int = None, y: int = None) -> None:
    """Single Shift+left-click (press and release shift around one click)."""
    pyautogui.keyDown("shift")
    try:
        time.sleep(0.05)
        pyautogui.click(x=x, y=y, button="left")
        time.sleep(0.05)
    finally:
        for key in ("shift", "shiftleft", "shiftright"):
            try:
                pyautogui.keyUp(key)
            except Exception:
                pass


def scroll(clicks: int, x: int = None, y: int = None) -> None:
    """Scroll up (positive) or down (negative) by the given number of clicks."""
    pyautogui.scroll(clicks, x=x, y=y)


def drag_to(x: int, y: int, duration: float = 0.5, button: str = "left") -> None:
    """Drag the mouse to an absolute position while holding a button."""
    pyautogui.dragTo(x, y, duration=duration, button=button)


def drag_relative(dx: int, dy: int, duration: float = 0.5, button: str = "left") -> None:
    """Drag the mouse relative to its current position."""
    pyautogui.dragRel(dx, dy, duration=duration, button=button)


def mouse_down(x: int = None, y: int = None, button: str = "left") -> None:
    """Press and hold a mouse button."""
    pyautogui.mouseDown(x=x, y=y, button=button)


def mouse_up(x: int = None, y: int = None, button: str = "left") -> None:
    """Release a mouse button."""
    pyautogui.mouseUp(x=x, y=y, button=button)
