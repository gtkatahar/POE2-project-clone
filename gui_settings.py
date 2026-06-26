"""Settings persistence and Settings tab for the POE2 Crafting Tool GUI."""

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QSpinBox, QRadioButton, QButtonGroup,
    QPushButton, QPlainTextEdit, QMessageBox, QDialog,
)

from gui_worker import ScrapeWorker
from gui_calibration import CalibrationOverlay
from windows.inventory import _load_config, calibrate_from_box

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
        self._scrape_worker: ScrapeWorker | None = None
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

        # --- Data Management ---
        data_group = QGroupBox("Data Management")
        data_layout = QVBoxLayout(data_group)

        data_desc = QLabel(
            "Re-download item modifier data from poe2db.tw, overwriting the\n"
            "cached files in data/. Makes ~50+ requests and takes a minute or two."
        )
        data_desc.setStyleSheet("color: #aaa; font-size: 11px;")
        data_layout.addWidget(data_desc)

        scrape_row = QHBoxLayout()
        self._btn_rescrape = QPushButton("Re-Scrape All Modifiers")
        self._btn_rescrape.setFixedHeight(34)
        self._btn_cancel_scrape = QPushButton("Cancel")
        self._btn_cancel_scrape.setFixedHeight(34)
        self._btn_cancel_scrape.setVisible(False)
        scrape_row.addWidget(self._btn_rescrape)
        scrape_row.addWidget(self._btn_cancel_scrape)
        scrape_row.addStretch()
        data_layout.addLayout(scrape_row)

        self._scrape_log = QPlainTextEdit()
        self._scrape_log.setReadOnly(True)
        self._scrape_log.setMaximumHeight(140)
        self._scrape_log.setPlaceholderText("Scrape output will appear here...")
        self._scrape_log.setVisible(False)
        data_layout.addWidget(self._scrape_log)

        self._btn_rescrape.clicked.connect(self._on_rescrape)
        self._btn_cancel_scrape.clicked.connect(self._on_cancel_scrape)

        layout.addWidget(data_group)

        # --- Inventory Calibration ---
        calib_group = QGroupBox("Inventory Calibration")
        calib_layout = QVBoxLayout(calib_group)

        self._calib_status = QLabel()
        self._calib_status.setStyleSheet("color: #aaa; font-size: 11px;")
        self._refresh_calib_status()
        calib_layout.addWidget(self._calib_status)

        calib_row = QHBoxLayout()
        self._btn_calibrate = QPushButton("Calibrate Inventory Grid")
        self._btn_calibrate.setFixedHeight(34)
        calib_row.addWidget(self._btn_calibrate)
        calib_row.addStretch()
        calib_layout.addLayout(calib_row)

        self._btn_calibrate.clicked.connect(self._on_calibrate)

        layout.addWidget(calib_group)
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

    def _on_rescrape(self) -> None:
        if self._scrape_worker and self._scrape_worker.isRunning():
            return

        reply = QMessageBox.question(
            self, "Re-Scrape All Modifiers",
            "This will fetch fresh data for every item category from poe2db.tw "
            "and overwrite the local JSON files in data/.\n\n"
            "This makes 50+ requests to poe2db.tw and may take a minute or two. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._scrape_log.clear()
        self._scrape_log.setVisible(True)
        self._btn_rescrape.setEnabled(False)
        self._btn_cancel_scrape.setVisible(True)

        self._scrape_worker = ScrapeWorker()
        self._scrape_worker.log_line.connect(self._scrape_log.appendPlainText)
        self._scrape_worker.finished.connect(self._on_rescrape_finished)
        self._scrape_worker.error.connect(self._on_rescrape_error)
        self._scrape_worker.start()

    def _on_cancel_scrape(self) -> None:
        if self._scrape_worker:
            self._scrape_worker.stop()
            self._scrape_log.appendPlainText("\nCancelling... (finishing current item)")

    def _on_rescrape_finished(self, result: dict) -> None:
        self._btn_rescrape.setEnabled(True)
        self._btn_cancel_scrape.setVisible(False)

    def _on_rescrape_error(self, msg: str) -> None:
        self._btn_rescrape.setEnabled(True)
        self._btn_cancel_scrape.setVisible(False)
        self._scrape_log.appendPlainText(f"\nERROR: {msg}")

    def _refresh_calib_status(self) -> None:
        cfg = _load_config()
        self._calib_status.setText(
            f"Current: {cfg['cell_w']}×{cfg['cell_h']}px cells, "
            f"origin ({cfg['origin_x']}, {cfg['origin_y']}) "
            f"@ {cfg['base_w']}×{cfg['base_h']}"
        )

    def _on_calibrate(self) -> None:
        self.window().showMinimized()
        dlg = CalibrationOverlay(self)
        result = dlg.exec()
        self.window().showNormal()

        if result == QDialog.DialogCode.Accepted and dlg.result_box():
            calibrate_from_box(*dlg.result_box())
            self._refresh_calib_status()
