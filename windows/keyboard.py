"""
windows/keyboard.py
-------------------
Keyboard control via pyautogui.
"""

import pyautogui

pyautogui.PAUSE = 0.05


def type_text(text: str, interval: float = 0.05) -> None:
    """Type a string of text with an optional delay between keystrokes."""
    pyautogui.typewrite(text, interval=interval)


def press(key: str) -> None:
    """Press and release a single key (e.g. 'enter', 'esc', 'f1')."""
    pyautogui.press(key)


def press_multiple(keys: list[str]) -> None:
    """Press and release each key in sequence."""
    pyautogui.press(keys)


def hotkey(*keys: str) -> None:
    """Press a key combination simultaneously (e.g. hotkey('ctrl', 'c'))."""
    pyautogui.hotkey(*keys)


def key_down(key: str) -> None:
    """Hold a key down."""
    pyautogui.keyDown(key)


def key_up(key: str) -> None:
    """Release a held key."""
    pyautogui.keyUp(key)


def copy() -> None:
    """Ctrl+C."""
    hotkey("ctrl", "c")


def paste() -> None:
    """Ctrl+V."""
    hotkey("ctrl", "v")


def select_all() -> None:
    """Ctrl+A."""
    hotkey("ctrl", "a")


def undo() -> None:
    """Ctrl+Z."""
    hotkey("ctrl", "z")


def get_all_keys() -> list[str]:
    """Return the list of all valid key names supported by pyautogui."""
    return pyautogui.KEYBOARD_KEYS
