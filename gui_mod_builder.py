"""ModBuilderDialog — GUI replacement for build_target.py's InquirerPy interface."""

import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QRadioButton,
    QButtonGroup, QListWidget, QListWidgetItem, QSplitter,
    QWidget, QSpinBox, QFrame, QMessageBox, QToolButton,
    QDialogButtonBox, QScrollArea, QGroupBox,
)


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
SAVES_DIR = ROOT_DIR / "saved_targets"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_slugs() -> list[tuple[str, str]]:
    """Return [(slug, display_name)] sorted alphabetically from data/*.json."""
    results = []
    for path in sorted(DATA_DIR.glob("*_modifiers_tiered.json")):
        slug = path.name.replace("_modifiers_tiered.json", "")
        display = slug.replace("_", " ").title()
        results.append((slug, display))
    return results


def _load_db_groups(slug: str) -> list[dict]:
    """Return Base Modifier groups from the slug's tiered DB file."""
    db_path = DATA_DIR / f"{slug.lower()}_modifiers_tiered.json"
    if not db_path.exists():
        return []
    db = json.loads(db_path.read_text(encoding="utf-8"))
    return [
        g for g in db["modifiers"]
        if g.get("section") == "Base Modifiers"
        and g.get("type", "").lower() in ("prefix", "suffix")
    ]


def _format_values(values: list) -> str:
    parts = []
    for v in values:
        if isinstance(v, list) and len(v) == 2:
            if v[0] == v[1]:
                parts.append(str(v[0]))
            else:
                parts.append(f"{v[0]}-{v[1]}")
        else:
            parts.append(str(v))
    return ", ".join(parts)


def _mod_display(group: dict) -> str:
    t = "PRE" if group["type"].lower() == "prefix" else "SUF"
    return f"[{t}] {group['family']}"


def _selected_display(entry: dict, show_tier: bool = True) -> str:
    t = "PRE" if entry["type"].lower() == "prefix" else "SUF"
    tier_str = f"  (T{entry['min_tier']}+)" if show_tier else ""
    return f"[{t}] {entry['family']}{tier_str}"


# ---------------------------------------------------------------------------
# Tier picker dialog
# ---------------------------------------------------------------------------

class TierPickerDialog(QDialog):
    """Small dialog to pick the minimum acceptable tier for a mod."""

    def __init__(self, group: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Minimum Tier")
        self.setMinimumWidth(360)
        self._group = group
        self._selected_tier: int | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{group['family']}</b>"))
        layout.addWidget(QLabel("Accept this tier or better (lower = better):"))

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        tiers = group.get("tiers", [])
        for tier_info in tiers:
            val_str = _format_values(tier_info.get("values", []))
            ilvl = tier_info.get("min_ilvl", 0)
            name = tier_info.get("name", "")
            label = f"T{tier_info['tier']}  {name:<20}  ilvl≥{ilvl:<3}  [{val_str}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, tier_info["tier"])
            self._list.addItem(item)

        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self._list)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept_selection)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept_selection(self) -> None:
        item = self._list.currentItem()
        if item:
            self._selected_tier = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def selected_tier(self) -> int | None:
        return self._selected_tier


# ---------------------------------------------------------------------------
# Mod list panel (reusable for main mods + 50-50)
# ---------------------------------------------------------------------------

class ModListPanel(QWidget):
    """Left: filterable available mods. Right: selected mods with tier."""

    def __init__(self, max_prefixes: int = 0, max_suffixes: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._max_prefixes = max_prefixes
        self._max_suffixes = max_suffixes
        self._db_groups: list[dict] = []
        self._selected: list[dict] = []
        self._type_filter = "all"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Left: available ---
        left = QVBoxLayout()
        filter_row = QHBoxLayout()
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter mods...")
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "Prefix", "Suffix"])
        self._filter_combo.setFixedWidth(80)
        filter_row.addWidget(self._filter_edit)
        filter_row.addWidget(self._filter_combo)
        left.addLayout(filter_row)

        self._avail_list = QListWidget()
        self._avail_list.setAlternatingRowColors(True)
        self._avail_list.setToolTip("Double-click to add")
        left.addWidget(QLabel("Available mods:"))
        left.addWidget(self._avail_list)

        left_widget = QWidget()
        left_widget.setLayout(left)

        # --- Right: selected ---
        right = QVBoxLayout()
        right.addWidget(QLabel("Selected mods:"))
        self._sel_list = QListWidget()
        self._sel_list.setAlternatingRowColors(True)
        right.addWidget(self._sel_list)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("Add →")
        self._btn_remove = QPushButton("Remove")
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        right.addLayout(btn_row)

        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 250])
        layout.addWidget(splitter)

        self._filter_edit.textChanged.connect(self._apply_filter)
        self._filter_combo.currentTextChanged.connect(self._on_type_filter)
        self._avail_list.itemDoubleClicked.connect(self._add_selected)
        self._btn_add.clicked.connect(self._add_selected)
        self._btn_remove.clicked.connect(self._remove_selected)

    def set_db_groups(self, groups: list[dict]) -> None:
        self._db_groups = groups
        self._populate_available()

    def _populate_available(self) -> None:
        self._avail_list.clear()
        filt = self._filter_edit.text().lower()
        type_filt = self._filter_combo.currentText().lower()

        for group in self._db_groups:
            t = group["type"].lower()
            if type_filt != "all" and t != type_filt:
                continue
            display = _mod_display(group)
            if filt and filt not in display.lower():
                continue
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, group)
            self._avail_list.addItem(item)

    def _apply_filter(self, _text: str) -> None:
        self._populate_available()

    def _on_type_filter(self, _text: str) -> None:
        self._populate_available()

    def _add_selected(self) -> None:
        item = self._avail_list.currentItem()
        if not item:
            return
        group = item.data(Qt.ItemDataRole.UserRole)
        family = group["family"]

        if any(e["family"] == family for e in self._selected):
            QMessageBox.information(self, "Already Added", f"'{family}' is already in the list.")
            return

        if self._max_prefixes or self._max_suffixes:
            t = group["type"].lower()
            count = sum(1 for e in self._selected if e["type"].lower() == t)
            limit = self._max_prefixes if t == "prefix" else self._max_suffixes
            if limit and count >= limit:
                QMessageBox.warning(
                    self, "Limit Reached",
                    f"Maximum {limit} {t}(es) already selected."
                )
                return

        dlg = TierPickerDialog(group, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        tier = dlg.selected_tier()
        if tier is None:
            return

        entry = {
            "type": group["type"],
            "family": family,
            "stat_template": group.get("stat_template", family),
            "min_tier": tier,
            "tags": group.get("tags", []),
        }
        self._selected.append(entry)
        self._refresh_selected_list()

    def _remove_selected(self) -> None:
        row = self._sel_list.currentRow()
        if row < 0:
            return
        del self._selected[row]
        self._refresh_selected_list()

    def _refresh_selected_list(self) -> None:
        self._sel_list.clear()
        for entry in self._selected:
            self._sel_list.addItem(_selected_display(entry))

    def get_selected(self) -> list[dict]:
        return list(self._selected)

    def set_selected(self, entries: list[dict]) -> None:
        self._selected = list(entries)
        self._refresh_selected_list()


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class ModBuilderDialog(QDialog):
    """Full target builder: slug, mode, mods, 50-50, save name."""

    def __init__(self, existing_data: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Build Target")
        self.setMinimumSize(820, 620)
        self._result: dict | None = None

        layout = QVBoxLayout(self)

        # --- Top: slug + mode ---
        top = QHBoxLayout()

        slug_form = QFormLayout()
        self._slug_combo = QComboBox()
        self._slug_combo.setEditable(True)
        self._slug_combo.setMinimumWidth(200)
        slugs = _list_slugs()
        for slug, display in slugs:
            self._slug_combo.addItem(display, userData=slug)
        slug_form.addRow("Item Type:", self._slug_combo)
        top.addLayout(slug_form)

        top.addSpacing(20)

        mode_group = QGroupBox("Mode")
        mode_layout = QHBoxLayout(mode_group)
        self._mode_search = QRadioButton("Search (any mods)")
        self._mode_target = QRadioButton("Target (3+3 strict)")
        self._mode_search.setChecked(True)
        mode_layout.addWidget(self._mode_search)
        mode_layout.addWidget(self._mode_target)
        top.addWidget(mode_group)
        top.addStretch()

        layout.addLayout(top)

        # --- Main mods panel ---
        self._main_panel = ModListPanel(parent=self)
        main_group = QGroupBox("Target Mods")
        main_group_layout = QVBoxLayout(main_group)
        main_group_layout.addWidget(self._main_panel)
        layout.addWidget(main_group, stretch=3)

        # --- 50-50 section (collapsible) ---
        self._fifty_toggle = QToolButton()
        self._fifty_toggle.setText("▶  50-50 Keeper Mods (optional)")
        self._fifty_toggle.setCheckable(True)
        self._fifty_toggle.setStyleSheet("QToolButton { text-align: left; font-weight: bold; }")
        self._fifty_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        layout.addWidget(self._fifty_toggle)

        self._fifty_widget = QWidget()
        fifty_inner = QVBoxLayout(self._fifty_widget)
        fifty_inner.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel("These mods are acceptable to keep during Aug+Annul 50-50 strategy.")
        lbl.setStyleSheet("color: #aaa; font-style: italic;")
        fifty_inner.addWidget(lbl)
        self._fifty_panel = ModListPanel(parent=self)
        fifty_inner.addWidget(self._fifty_panel)
        self._fifty_widget.setVisible(False)
        layout.addWidget(self._fifty_widget, stretch=2)

        # --- Save name + buttons ---
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Save as:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. my_amulet_target")
        self._name_edit.setMaximumWidth(250)
        bottom.addWidget(self._name_edit)
        bottom.addStretch()

        self._btn_cancel = QPushButton("Cancel")
        self._btn_save = QPushButton("Save Target")
        self._btn_save.setDefault(True)
        bottom.addWidget(self._btn_cancel)
        bottom.addWidget(self._btn_save)
        layout.addLayout(bottom)

        # Connections
        self._slug_combo.currentIndexChanged.connect(self._on_slug_changed)
        self._mode_search.toggled.connect(self._on_mode_changed)
        self._fifty_toggle.toggled.connect(self._fifty_widget.setVisible)
        self._fifty_toggle.toggled.connect(
            lambda checked: self._fifty_toggle.setText(
                ("▼" if checked else "▶") + "  50-50 Keeper Mods (optional)"
            )
        )
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_save.clicked.connect(self._on_save)

        # Pre-fill if editing
        if existing_data:
            self._prefill(existing_data)
        else:
            self._on_slug_changed(0)

    def _on_slug_changed(self, _idx: int) -> None:
        slug = self._slug_combo.currentData()
        if not slug:
            return
        groups = _load_db_groups(slug)
        self._main_panel.set_db_groups(groups)
        self._fifty_panel.set_db_groups(groups)

    def _on_mode_changed(self, search_checked: bool) -> None:
        if search_checked:
            self._main_panel._max_prefixes = 0
            self._main_panel._max_suffixes = 0
        else:
            self._main_panel._max_prefixes = 3
            self._main_panel._max_suffixes = 3

    def _prefill(self, data: dict) -> None:
        slug = data.get("slug", "")
        idx = self._slug_combo.findData(slug)
        if idx >= 0:
            self._slug_combo.setCurrentIndex(idx)
        else:
            self._on_slug_changed(0)

        mode = data.get("mode", "search")
        if mode == "target":
            self._mode_target.setChecked(True)
        else:
            self._mode_search.setChecked(True)

        if mode == "search":
            mods = data.get("mods", [])
        else:
            mods = data.get("prefixes", []) + data.get("suffixes", [])
        self._main_panel.set_selected(mods)

        fifty = data.get("fifty_fifty", [])
        if fifty:
            self._fifty_panel.set_selected(fifty)
            self._fifty_toggle.setChecked(True)

        save_name = data.get("save_name", "")
        if save_name:
            self._name_edit.setText(save_name)

    def _on_save(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "Please enter a save name.")
            return

        slug = self._slug_combo.currentData() or ""
        if not slug:
            QMessageBox.warning(self, "Slug Required", "Please select an item type.")
            return

        mode = "search" if self._mode_search.isChecked() else "target"
        selected = self._main_panel.get_selected()

        if not selected:
            QMessageBox.warning(self, "No Mods", "Please add at least one mod.")
            return

        fifty = self._fifty_panel.get_selected()

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

        if mode == "search":
            result = {
                "save_name": safe_name,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "slug": slug,
                "mode": "search",
                "mods": selected,
                "fifty_fifty": fifty,
            }
        else:
            prefixes = [e for e in selected if e["type"].lower() == "prefix"]
            suffixes = [e for e in selected if e["type"].lower() == "suffix"]
            result = {
                "save_name": safe_name,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "slug": slug,
                "mode": "target",
                "prefixes": prefixes,
                "suffixes": suffixes,
                "fifty_fifty": fifty,
            }

        SAVES_DIR.mkdir(exist_ok=True)
        out_path = SAVES_DIR / f"{safe_name}.json"
        if out_path.exists():
            ans = QMessageBox.question(
                self, "Overwrite?",
                f"'{safe_name}.json' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        self._result = result
        self.accept()

    def get_result(self) -> dict | None:
        return self._result
