"""Settings persistence and Settings tab for the POE2 Crafting Tool GUI."""

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QSpinBox, QRadioButton, QButtonGroup,
)

ROOT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT_DIR / "settings.json"

DEFAULTS: dict = {
    "auto_minimize": True,
    "font_size": 10,
    "default_strategy": None,
}

STRATEGY_LABELS = [
    ("scan_only",      "Scan Only  (no automation)"),
    ("chaos",          "Chaos Spam"),
    ("augment_annul",  "Augment + Annul"),
    ("aug_annul_5050", "Aug + Annul  50-50"),
]


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


class SettingsTab(QWidget):
    auto_minimize_changed = pyqtSignal(bool)
    font_size_changed = pyqtSignal(int)
    default_strategy_changed = pyqtSignal(object)  # str key or None

    def __init__(self, settings: dict, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(12)

        # --- Window Behavior ---
        win_group = QGroupBox("Window Behavior")
        win_layout = QVBoxLayout(win_group)
        self._auto_minimize_cb = QCheckBox("Auto-minimize window during operations")
        self._auto_minimize_cb.setChecked(self._settings.get("auto_minimize", True))
        self._auto_minimize_cb.toggled.connect(self._on_auto_minimize)
        win_layout.addWidget(self._auto_minimize_cb)
        layout.addWidget(win_group)

        # --- Appearance ---
        app_group = QGroupBox("Appearance")
        app_layout = QHBoxLayout(app_group)
        app_layout.addWidget(QLabel("Font Size:"))
        self._font_spin = QSpinBox()
        self._font_spin.setRange(8, 18)
        self._font_spin.setValue(self._settings.get("font_size", 10))
        self._font_spin.setSuffix(" pt")
        self._font_spin.setFixedWidth(80)
        self._font_spin.valueChanged.connect(self._on_font_size)
        app_layout.addWidget(self._font_spin)
        app_layout.addStretch()
        layout.addWidget(app_group)

        # --- Crafting Defaults ---
        craft_group = QGroupBox("Crafting Defaults")
        craft_layout = QVBoxLayout(craft_group)
        craft_layout.addWidget(QLabel("Default Crafting Method:"))

        self._strategy_bg = QButtonGroup(self)
        none_rb = QRadioButton("None  (no default)")
        self._strategy_bg.addButton(none_rb, -1)
        craft_layout.addWidget(none_rb)

        for i, (key, label) in enumerate(STRATEGY_LABELS):
            rb = QRadioButton(label)
            self._strategy_bg.addButton(rb, i)
            craft_layout.addWidget(rb)

        default = self._settings.get("default_strategy")
        if default is None:
            none_rb.setChecked(True)
        else:
            matched = False
            for i, (key, _) in enumerate(STRATEGY_LABELS):
                if key == default:
                    self._strategy_bg.button(i).setChecked(True)
                    matched = True
                    break
            if not matched:
                none_rb.setChecked(True)

        self._strategy_bg.idToggled.connect(self._on_strategy_toggled)
        layout.addWidget(craft_group)
        layout.addStretch()

    def _on_auto_minimize(self, checked: bool) -> None:
        self._settings["auto_minimize"] = checked
        save_settings(self._settings)
        self.auto_minimize_changed.emit(checked)

    def _on_font_size(self, value: int) -> None:
        self._settings["font_size"] = value
        save_settings(self._settings)
        self.font_size_changed.emit(value)

    def _on_strategy_toggled(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        if btn_id == -1:
            self._settings["default_strategy"] = None
            save_settings(self._settings)
            self.default_strategy_changed.emit(None)
        else:
            key = STRATEGY_LABELS[btn_id][0]
            self._settings["default_strategy"] = key
            save_settings(self._settings)
            self.default_strategy_changed.emit(key)
