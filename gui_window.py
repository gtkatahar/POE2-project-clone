"""Main window and tab widgets for the POE2 Crafting Tool GUI."""

import json
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QRadioButton, QButtonGroup, QPlainTextEdit,
    QSplitter, QFrame, QMessageBox, QScrollBar, QAbstractItemView,
    QSizePolicy, QLineEdit, QComboBox, QToolButton,
)

from gui_mod_builder import ModBuilderDialog
from gui_worker import ScanWorker, CraftWorker
from gui_settings import SettingsTab, load_settings
from crafting.targets import (
    load_all_db_groups,
    mods_from_data,
    target_to_active,
    ACTIVE_SOURCE_FILE,
    MATS_FILE,
    SAVES_DIR,
    TARGET_FILE,
)

STRATEGY_LABELS = [
    ("scan_only",      "Scan Only  (no automation)"),
    ("chaos",          "Chaos Spam"),
    ("augment_annul",  "Augment + Annul"),
    ("aug_annul_5050", "Aug + Annul  50-50"),
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _small_label(text: str, color: str = "#aaa") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
    return lbl


def _hr() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _read_active_source() -> str | None:
    """Return the filename of the saved target that was last used to set the
    active target, or None if unknown (e.g. never set since this feature shipped)."""
    if ACTIVE_SOURCE_FILE.exists():
        try:
            name = ACTIVE_SOURCE_FILE.read_text(encoding="utf-8").strip()
            return name or None
        except Exception:
            return None
    return None


def _mode_display(mode: str) -> str:
    if mode == "search":
        return "search (matches any of the listed mods)"
    if mode == "target":
        return "target (strict — exactly 3 prefixes + 3 suffixes)"
    return mode


ATTR_TOKENS = {"str", "dex", "int"}


def _split_slug(slug: str) -> tuple[str, tuple[str, ...]]:
    """Split a slug into (category_key, attr_tokens).

    Strips the longest trailing run of tokens drawn from {str, dex, int},
    e.g. "boots_int" -> ("boots", ("int",)); "wands" -> ("wands", ())."""
    tokens = slug.split("_")
    cut = len(tokens)
    while cut > 0 and tokens[cut - 1] in ATTR_TOKENS:
        cut -= 1
    if cut == 0:
        cut = len(tokens)
    return "_".join(tokens[:cut]), tuple(tokens[cut:])


def _category_display(category_key: str) -> str:
    return category_key.replace("_", " ").title()


def _subcategory_display(attr_tokens: tuple[str, ...]) -> str:
    return " ".join(t.title() for t in attr_tokens)


def _find_tier_options(slug: str, family: str, section_key: str | None = None) -> list[dict] | None:
    """Look up the real tier list for a mod family from its slug's DB file."""
    groups_by_section = load_all_db_groups(slug)
    sections = (
        [groups_by_section[section_key]]
        if section_key and section_key in groups_by_section
        else groups_by_section.values()
    )
    for groups in sections:
        for g in groups:
            if g.get("family") == family:
                tiers = g.get("tiers", [])
                return sorted(tiers, key=lambda t: t.get("tier", 0))
    return None


# ---------------------------------------------------------------------------
# Materials Tab
# ---------------------------------------------------------------------------

class MaterialsTab(QWidget):
    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self._main = main_window
        self._worker: ScanWorker | None = None

        layout = QVBoxLayout(self)

        # Controls row
        ctrl = QHBoxLayout()
        self._btn_scan = QPushButton("Scan Inventory")
        self._btn_scan.setToolTip("Open your POE2 inventory, then click Scan.")
        self._btn_scan.setFixedHeight(34)

        self._spin_countdown = QSpinBox()
        self._spin_countdown.setRange(1, 30)
        self._spin_countdown.setValue(3)
        self._spin_countdown.setSuffix("s")
        self._spin_countdown.setFixedWidth(55)

        self._btn_reload = QPushButton("Reload from File")
        self._btn_reload.setFixedHeight(34)

        ctrl.addWidget(self._btn_scan)
        ctrl.addWidget(_small_label("Countdown:"))
        ctrl.addWidget(self._spin_countdown)
        ctrl.addSpacing(12)
        ctrl.addWidget(self._btn_reload)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # Scan log (shown while scanning)
        self._scan_log = QPlainTextEdit()
        self._scan_log.setReadOnly(True)
        self._scan_log.setMaximumHeight(100)
        self._scan_log.setPlaceholderText("Scan output will appear here...")
        self._scan_log.setVisible(False)
        layout.addWidget(self._scan_log)

        # Materials table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Material", "Count", "Max Stack", "Description"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table)

        self._status = _small_label("No materials loaded.  Click 'Reload from File' or scan.")
        layout.addWidget(self._status)

        self._btn_scan.clicked.connect(self._on_scan)
        self._btn_reload.clicked.connect(self._on_reload)

        self._try_load_from_file()

    def _try_load_from_file(self) -> None:
        if MATS_FILE.exists():
            try:
                data = json.loads(MATS_FILE.read_text(encoding="utf-8"))
                self._load_mats_from_dict(data)
            except Exception:
                pass

    def _on_reload(self) -> None:
        if not MATS_FILE.exists():
            QMessageBox.warning(
                self, "File Not Found",
                "crafting_mats.json not found.\nRun 'Scan Inventory' first."
            )
            return
        try:
            data = json.loads(MATS_FILE.read_text(encoding="utf-8"))
            self._load_mats_from_dict(data)
            self._status.setText(f"Loaded {len(data)} materials from crafting_mats.json")
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _on_scan(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._scan_log.clear()
        self._scan_log.setVisible(True)
        self._btn_scan.setEnabled(False)
        self._btn_reload.setEnabled(False)
        self._status.setText("Scanning...")

        self._worker = ScanWorker(self._spin_countdown.value())
        self._worker.log_line.connect(self._scan_log.appendPlainText)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        self._worker.minimize_window.connect(
            self._main._maybe_minimize, Qt.ConnectionType.QueuedConnection
        )
        self._worker.restore_window.connect(
            self._main.showNormal, Qt.ConnectionType.QueuedConnection
        )
        self._worker.start()

    def _on_scan_finished(self, data: dict) -> None:
        self._btn_scan.setEnabled(True)
        self._btn_reload.setEnabled(True)
        self._load_mats_from_dict(data)
        self._status.setText(
            f"Scan complete — {len(data)} material types found.  "
            f"Saved to crafting_mats.json"
        )

    def _on_scan_error(self, msg: str) -> None:
        self._btn_scan.setEnabled(True)
        self._btn_reload.setEnabled(True)
        self._scan_log.appendPlainText(f"\nERROR: {msg}")
        self._status.setText(f"Scan failed: {msg}")

    def _load_mats_from_dict(self, data: dict) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for name, info in data.items():
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(name))

            count_item = QTableWidgetItem()
            count_item.setData(Qt.ItemDataRole.DisplayRole, info.get("count", 0))
            self._table.setItem(row, 1, count_item)

            max_item = QTableWidgetItem()
            max_item.setData(Qt.ItemDataRole.DisplayRole, info.get("max_stack", 1))
            self._table.setItem(row, 2, max_item)

            self._table.setItem(row, 3, QTableWidgetItem(info.get("description", "")))
        self._table.setSortingEnabled(True)
        self._table.sortItems(1, Qt.SortOrder.DescendingOrder)
        self._status.setText(
            f"{len(data)} materials loaded.  "
            f"Last file: {datetime.fromtimestamp(MATS_FILE.stat().st_mtime).strftime('%Y-%m-%d %H:%M') if MATS_FILE.exists() else 'N/A'}"
        )


# ---------------------------------------------------------------------------
# Targets Tab
# ---------------------------------------------------------------------------

class TargetsTab(QWidget):
    active_target_changed = pyqtSignal(dict)

    _ROLE_KIND = Qt.ItemDataRole.UserRole + 1  # "category" | "subcategory" | "leaf"
    _ROLE_KEY = Qt.ItemDataRole.UserRole + 2   # category key or full slug

    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self._main = main_window
        self._current_path: Path | None = None
        self._mod_row_refs: list[tuple[str, int]] = []
        self._fifty_row_refs: list[tuple[str, int]] = []

        layout = QHBoxLayout(self)

        # --- Left sidebar ---
        left = QVBoxLayout()

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Saved Targets:"))
        header_row.addStretch()
        self._btn_new = QPushButton("New")
        self._btn_new.setFixedHeight(24)
        header_row.addWidget(self._btn_new)
        left.addLayout(header_row)

        expand_row = QHBoxLayout()
        expand_row.addStretch()
        self._btn_expand_all = QPushButton("Expand All")
        self._btn_collapse_all = QPushButton("Collapse All")
        for btn in (self._btn_expand_all, self._btn_collapse_all):
            btn.setFixedHeight(20)
            expand_row.addWidget(btn)
        left.addLayout(expand_row)

        self._category_filter = QComboBox()
        self._category_filter.addItem("All Categories", userData=None)
        left.addWidget(self._category_filter)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter by name or item type...")
        left.addWidget(self._filter_edit)

        self._save_tree = QTreeWidget()
        self._save_tree.setHeaderHidden(True)
        self._save_tree.setColumnCount(1)
        self._save_tree.setAlternatingRowColors(True)
        self._tree_ever_populated = False
        left.addWidget(self._save_tree, 1)

        left_widget = QWidget()
        left_widget.setLayout(left)

        # --- Right detail panel ---
        right = QVBoxLayout()
        right.setSpacing(8)
        right.setContentsMargins(8, 4, 4, 4)

        active_row = QHBoxLayout()
        self._lbl_active = QLabel("No active target")
        self._lbl_active.setStyleSheet("font-size: 13px; font-weight: bold; color: #b8943f;")
        active_row.addWidget(self._lbl_active)
        active_row.addStretch()

        self._btn_set_active = QPushButton("Set Active")
        self._btn_set_active.setStyleSheet(
            "QPushButton { background: #4a7a1e; color: #ddd; font-weight: bold; }"
            "QPushButton:hover { background: #5a9a28; }"
            "QPushButton:disabled { background: #3a3a3a; color: #777; }"
        )
        self._btn_edit = QPushButton("Edit")
        self._btn_dup = QPushButton("Duplicate")
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setStyleSheet(
            "QPushButton { background: #7a1e1e; color: #ddd; }"
            "QPushButton:hover { background: #9a2828; }"
        )
        for btn in (self._btn_set_active, self._btn_edit, self._btn_dup, self._btn_delete):
            btn.setFixedHeight(26)
            active_row.addWidget(btn)
        right.addLayout(active_row)

        self._lbl_meta = _small_label("")
        right.addWidget(self._lbl_meta)

        self._lbl_edit_note = _small_label("", color="#d4a840")
        self._lbl_edit_note.setVisible(False)
        right.addWidget(self._lbl_edit_note)

        right.addWidget(_hr())

        self._mod_toggle = QToolButton()
        self._mod_toggle.setText("▼  Mods")
        self._mod_toggle.setCheckable(True)
        self._mod_toggle.setChecked(True)
        self._mod_toggle.setStyleSheet("QToolButton { text-align: left; font-weight: bold; border: none; }")
        self._mod_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        right.addWidget(self._mod_toggle)

        self._mod_table = QTableWidget(0, 5)
        self._mod_table.setHorizontalHeaderLabels(["Type", "Family", "Min Tier", "Tags", ""])
        self._mod_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._mod_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._mod_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._mod_table.setAlternatingRowColors(True)
        self._mod_table.setWordWrap(True)
        right.addWidget(self._mod_table, 3)

        self._fifty_toggle = QToolButton()
        self._fifty_toggle.setText("▼  50-50 Keeper Mods")
        self._fifty_toggle.setCheckable(True)
        self._fifty_toggle.setChecked(True)
        self._fifty_toggle.setStyleSheet("QToolButton { text-align: left; font-weight: bold; border: none; margin-top: 8px; }")
        self._fifty_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        right.addWidget(self._fifty_toggle)

        self._fifty_table = QTableWidget(0, 5)
        self._fifty_table.setHorizontalHeaderLabels(["Type", "Family", "Min Tier", "Tags", ""])
        self._fifty_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._fifty_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._fifty_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._fifty_table.setAlternatingRowColors(True)
        self._fifty_table.setWordWrap(True)
        right.addWidget(self._fifty_table, 1)
        right.addStretch(0)

        right_widget = QWidget()
        right_widget.setLayout(right)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 700])
        layout.addWidget(splitter)

        # Connections
        self._filter_edit.textChanged.connect(self._apply_filter)
        self._category_filter.currentIndexChanged.connect(self._apply_filter)
        self._save_tree.currentItemChanged.connect(self._on_selection_changed)
        self._save_tree.itemClicked.connect(self._on_item_clicked)
        self._btn_expand_all.clicked.connect(self._save_tree.expandAll)
        self._btn_collapse_all.clicked.connect(self._save_tree.collapseAll)
        self._btn_new.clicked.connect(self._on_new)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_dup.clicked.connect(self._on_duplicate)
        self._btn_set_active.clicked.connect(self._on_set_active)
        self._btn_delete.clicked.connect(self._on_delete)
        self._mod_toggle.toggled.connect(self._mod_table.setVisible)
        self._mod_toggle.toggled.connect(
            lambda checked: self._mod_toggle.setText(("▼" if checked else "▶") + "  Mods")
        )
        self._fifty_toggle.toggled.connect(self._fifty_table.setVisible)
        self._fifty_toggle.toggled.connect(
            lambda checked: self._fifty_toggle.setText(
                ("▼" if checked else "▶") + "  50-50 Keeper Mods"
            )
        )

        self._refresh_list()
        self._update_active_status(self._selected_path())

    def _refresh_list(self) -> None:
        expanded_state: dict[tuple[str, str], bool] = {}

        def snapshot(item: QTreeWidgetItem) -> None:
            kind = item.data(0, self._ROLE_KIND)
            if kind != "leaf":
                expanded_state[(kind, item.data(0, self._ROLE_KEY))] = item.isExpanded()
            for i in range(item.childCount()):
                snapshot(item.child(i))

        for i in range(self._save_tree.topLevelItemCount()):
            snapshot(self._save_tree.topLevelItem(i))

        selected_key: tuple[str, str] | None = None
        cur = self._save_tree.currentItem()
        if cur is not None:
            kind = cur.data(0, self._ROLE_KIND)
            if kind == "leaf":
                selected_key = ("leaf", cur.data(0, Qt.ItemDataRole.UserRole).name)
            else:
                selected_key = (kind, cur.data(0, self._ROLE_KEY))

        active_source = _read_active_source()

        self._save_tree.clear()
        SAVES_DIR.mkdir(exist_ok=True)
        paths = sorted(SAVES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

        groups: dict[str, dict[str | None, list[tuple[Path, dict]]]] = {}
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            slug = data.get("slug", "?")
            category_key, attr_tokens = _split_slug(slug)
            subcat_key = slug if attr_tokens else None
            groups.setdefault(category_key, {}).setdefault(subcat_key, []).append((path, data))

        selected_item: QTreeWidgetItem | None = None
        active_item: QTreeWidgetItem | None = None
        first_leaf: QTreeWidgetItem | None = None

        def add_leaf(parent: QTreeWidgetItem, path: Path, data: dict) -> QTreeWidgetItem:
            nonlocal first_leaf, selected_item, active_item
            mods = mods_from_data(data)
            label = f"{data.get('save_name', path.stem)}  ({len(mods)} mods)"
            leaf_item = QTreeWidgetItem([label])
            leaf_item.setData(0, Qt.ItemDataRole.UserRole, path)
            leaf_item.setData(0, self._ROLE_KIND, "leaf")
            if active_source is not None and path.name == active_source:
                font = leaf_item.font(0)
                font.setBold(True)
                leaf_item.setFont(0, font)
                leaf_item.setForeground(0, QColor("#b8943f"))
                active_item = leaf_item
            parent.addChild(leaf_item)
            if first_leaf is None:
                first_leaf = leaf_item
            if selected_key == ("leaf", path.name):
                selected_item = leaf_item
            return leaf_item

        for category_key in sorted(groups):
            subcats = groups[category_key]
            total = sum(len(leaves) for leaves in subcats.values())
            cat_item = QTreeWidgetItem([f"{_category_display(category_key)} ({total})"])
            cat_item.setData(0, self._ROLE_KIND, "category")
            cat_item.setData(0, self._ROLE_KEY, category_key)
            self._save_tree.addTopLevelItem(cat_item)
            cat_item.setExpanded(expanded_state.get(("category", category_key), True))
            if selected_key == ("category", category_key):
                selected_item = cat_item

            for path, data in subcats.get(None, []):
                add_leaf(cat_item, path, data)

            subcat_keys = [k for k in subcats if k is not None]
            subcat_keys.sort(key=lambda k: _subcategory_display(_split_slug(k)[1]))
            for subcat_key in subcat_keys:
                leaves = subcats[subcat_key]
                _, attr_tokens = _split_slug(subcat_key)
                sub_item = QTreeWidgetItem([f"{_subcategory_display(attr_tokens)} ({len(leaves)})"])
                sub_item.setData(0, self._ROLE_KIND, "subcategory")
                sub_item.setData(0, self._ROLE_KEY, subcat_key)
                cat_item.addChild(sub_item)
                sub_item.setExpanded(expanded_state.get(("subcategory", subcat_key), True))
                if selected_key == ("subcategory", subcat_key):
                    selected_item = sub_item
                for path, data in leaves:
                    add_leaf(sub_item, path, data)

        if active_item is not None:
            parent = active_item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()

        if not self._tree_ever_populated:
            self._save_tree.expandAll()
            self._tree_ever_populated = True

        if selected_item is None:
            selected_item = first_leaf
        if selected_item is not None:
            self._save_tree.setCurrentItem(selected_item)

        self._refresh_category_filter(sorted(groups))
        self._apply_filter()

    def _refresh_category_filter(self, category_keys: list[str]) -> None:
        current = self._category_filter.currentData()
        self._category_filter.blockSignals(True)
        self._category_filter.clear()
        self._category_filter.addItem("All Categories", userData=None)
        select_index = 0
        for i, key in enumerate(category_keys, start=1):
            self._category_filter.addItem(_category_display(key), userData=key)
            if key == current:
                select_index = i
        self._category_filter.setCurrentIndex(select_index)
        self._category_filter.blockSignals(False)

    def _apply_filter(self, _value=None) -> None:
        text = self._filter_edit.text().strip().lower()
        cat_key = self._category_filter.currentData()
        for i in range(self._save_tree.topLevelItemCount()):
            self._apply_filter_recursive(self._save_tree.topLevelItem(i), text, cat_key)

    def _apply_filter_recursive(self, item: QTreeWidgetItem, text: str, cat_key: str | None) -> bool:
        kind = item.data(0, self._ROLE_KIND)
        if kind == "category" and cat_key is not None and item.data(0, self._ROLE_KEY) != cat_key:
            item.setHidden(True)
            return False
        if kind == "leaf":
            visible = (
                not text
                or text in item.text(0).lower()
                or self._ancestor_text_matches(item, text)
            )
        else:
            visible = any(
                self._apply_filter_recursive(item.child(i), text, cat_key)
                for i in range(item.childCount())
            )
        item.setHidden(not visible)
        return visible

    def _ancestor_text_matches(self, item: QTreeWidgetItem, text: str) -> bool:
        parent = item.parent()
        while parent is not None:
            if text in parent.text(0).lower():
                return True
            parent = parent.parent()
        return False

    def _update_active_status(self, path: Path | None) -> None:
        """Reflect whether the selected target is the active one, and toggle Set Active."""
        if path is None:
            self._lbl_active.setText("No target selected")
            self._lbl_active.setStyleSheet("font-size: 13px; font-weight: bold; color: #999;")
            self._btn_set_active.setEnabled(False)
            return

        active_source = _read_active_source()
        if active_source is not None and path.name == active_source:
            self._lbl_active.setText("● Active")
            self._lbl_active.setStyleSheet("font-size: 13px; font-weight: bold; color: #6fc22e;")
            self._btn_set_active.setEnabled(False)
        else:
            self._lbl_active.setText("○ Not Active")
            self._lbl_active.setStyleSheet("font-size: 13px; font-weight: bold; color: #999;")
            self._btn_set_active.setEnabled(True)

    def _on_selection_changed(
        self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None = None
    ) -> None:
        if current is None or current.data(0, self._ROLE_KIND) != "leaf":
            self._current_path = None
            self._clear_detail_panel()
            self._update_active_status(None)
            return
        path: Path = current.data(0, Qt.ItemDataRole.UserRole)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._populate_detail(data, path)
            self._note_if_active(data)
            self._update_active_status(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", str(exc))

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if item.data(0, self._ROLE_KIND) != "leaf":
            item.setExpanded(not item.isExpanded())

    def _clear_detail_panel(self) -> None:
        self._lbl_meta.setText("")
        self._lbl_edit_note.setVisible(False)
        self._mod_table.setRowCount(0)
        self._mod_row_refs = []
        self._fifty_table.setRowCount(0)
        self._fifty_row_refs = []

    def _populate_detail(self, data: dict, path: Path) -> None:
        slug = data.get("slug", "?")
        mode = data.get("mode", "?")
        created = data.get("created_at", "?")
        fifty = data.get("fifty_fifty", [])

        self._current_path = path
        self._lbl_meta.setText(f"Slug: {slug}   Mode: {_mode_display(mode)}   Created: {created}")
        self._lbl_edit_note.setVisible(False)

        self._mod_table.setRowCount(0)
        self._mod_row_refs = []
        if mode == "search":
            for idx, entry in enumerate(data.get("mods", [])):
                self._add_mod_row(self._mod_table, entry, slug, "mods", idx, self._mod_row_refs)
        else:
            for idx, entry in enumerate(data.get("prefixes", [])):
                self._add_mod_row(self._mod_table, entry, slug, "prefixes", idx, self._mod_row_refs)
            for idx, entry in enumerate(data.get("suffixes", [])):
                self._add_mod_row(self._mod_table, entry, slug, "suffixes", idx, self._mod_row_refs)
        self._mod_table.resizeRowsToContents()

        self._fifty_table.setRowCount(0)
        self._fifty_row_refs = []
        for idx, entry in enumerate(fifty):
            self._add_mod_row(self._fifty_table, entry, slug, "fifty_fifty", idx, self._fifty_row_refs)
        self._fifty_table.resizeRowsToContents()

    def _add_mod_row(
        self, table: QTableWidget, entry: dict, slug: str,
        list_key: str, index: int, row_refs: list[tuple[str, int]],
    ) -> None:
        row = table.rowCount()
        table.insertRow(row)
        row_refs.append((list_key, index))

        t = entry.get("type", "?")
        prefix = "PRE" if t.lower() == "prefix" else "SUF"
        table.setItem(row, 0, QTableWidgetItem(prefix))

        family = entry.get("family", "")
        family_item = QTableWidgetItem(family)
        family_item.setToolTip(family)
        table.setItem(row, 1, family_item)

        tier_options = _find_tier_options(slug, family, entry.get("section_key"))
        if tier_options:
            combo = QComboBox()
            current_tier = entry.get("min_tier")
            select_index = 0
            for i, tier_info in enumerate(tier_options):
                combo.addItem(f"T{tier_info['tier']}+", tier_info["tier"])
                if tier_info["tier"] == current_tier:
                    select_index = i
            combo.setCurrentIndex(select_index)
            combo.currentIndexChanged.connect(
                lambda _idx, le=list_key, ix=index, c=combo: self._on_tier_changed(le, ix, c)
            )
            table.setCellWidget(row, 2, combo)
        else:
            tier_item = QTableWidgetItem(f"T{entry.get('min_tier', '?')}+")
            tier_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 2, tier_item)

        tags = ", ".join(entry.get("tags", []))
        tags_item = QTableWidgetItem(tags)
        tags_item.setToolTip(tags)
        table.setItem(row, 3, tags_item)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setToolTip("Remove this mod from the target")
        remove_btn.setStyleSheet(
            "QPushButton { background: #7a1e1e; color: #ddd; font-weight: bold; border-radius: 3px; }"
            "QPushButton:hover { background: #9a2828; }"
        )
        remove_btn.clicked.connect(
            lambda _checked, le=list_key, ix=index: self._on_remove_mod(le, ix)
        )
        table.setCellWidget(row, 4, remove_btn)

    def _note_if_active(self, data: dict) -> None:
        active_source = _read_active_source()
        if self._current_path is not None and active_source == self._current_path.name:
            if target_to_active(data) != self._main.active_target_data:
                self._lbl_edit_note.setText("Edited — click Set Active to apply this change")
                self._lbl_edit_note.setVisible(True)
                return
        self._lbl_edit_note.setVisible(False)

    def _on_tier_changed(self, list_key: str, index: int, combo: QComboBox) -> None:
        if self._current_path is None:
            return
        new_tier = combo.currentData()
        try:
            data = json.loads(self._current_path.read_text(encoding="utf-8"))
            data[list_key][index]["min_tier"] = new_tier
            self._current_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Update Error", str(exc))
            return
        self._populate_detail(data, self._current_path)
        self._note_if_active(data)
        self._refresh_list()

    def _on_remove_mod(self, list_key: str, index: int) -> None:
        if self._current_path is None:
            return
        ans = QMessageBox.question(
            self, "Remove Mod",
            "Remove this mod from the target?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            data = json.loads(self._current_path.read_text(encoding="utf-8"))
            del data[list_key][index]
            self._current_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Update Error", str(exc))
            return
        self._populate_detail(data, self._current_path)
        self._note_if_active(data)
        self._refresh_list()

    def _selected_path(self) -> Path | None:
        item = self._save_tree.currentItem()
        if item is None or item.data(0, self._ROLE_KIND) != "leaf":
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    def _selected_data(self) -> dict | None:
        path = self._selected_path()
        if path is None:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _on_new(self) -> None:
        dlg = ModBuilderDialog(parent=self)
        if dlg.exec() == ModBuilderDialog.DialogCode.Accepted:
            self._refresh_list()
            result = dlg.get_result()
            if result:
                self._apply_active(result)

    def _on_edit(self) -> None:
        data = self._selected_data()
        if data is None:
            QMessageBox.information(self, "No Selection", "Select a target to edit.")
            return
        dlg = ModBuilderDialog(existing_data=data, parent=self)
        if dlg.exec() == ModBuilderDialog.DialogCode.Accepted:
            self._refresh_list()
            result = dlg.get_result()
            if result:
                self._apply_active(result)

    def _on_duplicate(self) -> None:
        data = self._selected_data()
        if data is None:
            QMessageBox.information(self, "No Selection", "Select a target to duplicate.")
            return
        dup = dict(data)
        dup.pop("save_name", None)
        dup.pop("created_at", None)
        dlg = ModBuilderDialog(existing_data=dup, parent=self)
        if dlg.exec() == ModBuilderDialog.DialogCode.Accepted:
            self._refresh_list()
            result = dlg.get_result()
            if result:
                self._apply_active(result)

    def _apply_active(self, data: dict, source_path: Path | None = None) -> None:
        """Write data as the active target and update all UI state."""
        active = target_to_active(data)
        TARGET_FILE.write_text(json.dumps(active, indent=2, ensure_ascii=False), encoding="utf-8")
        self._main.active_target_data = active

        if source_path is None and data.get("save_name"):
            source_path = SAVES_DIR / f"{data['save_name']}.json"
        if source_path is not None and source_path.exists():
            ACTIVE_SOURCE_FILE.write_text(source_path.name, encoding="utf-8")
        else:
            ACTIVE_SOURCE_FILE.unlink(missing_ok=True)

        self.active_target_changed.emit(active)
        self._refresh_list()
        self._update_active_status(self._selected_path())
        self._lbl_edit_note.setVisible(False)

    def _on_set_active(self) -> None:
        path = self._selected_path()
        data = self._selected_data()
        if data is None:
            QMessageBox.information(self, "No Selection", "Select a target first.")
            return
        self._apply_active(data, source_path=path)
        slug = data.get("slug", "?")
        QMessageBox.information(
            self, "Active Target Set",
            f"'{data.get('save_name', slug)}' is now the active target."
        )

    def _on_delete(self) -> None:
        path = self._selected_path()
        if path is None:
            QMessageBox.information(self, "No Selection", "Select a target to delete.")
            return
        ans = QMessageBox.question(
            self, "Delete Target",
            f"Delete '{path.stem}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            path.unlink(missing_ok=True)
            if _read_active_source() == path.name:
                ACTIVE_SOURCE_FILE.unlink(missing_ok=True)
            self._refresh_list()


# ---------------------------------------------------------------------------
# Craft Tab
# ---------------------------------------------------------------------------

class CraftTab(QWidget):
    def __init__(self, main_window: "MainWindow") -> None:
        super().__init__()
        self._main = main_window
        self._worker: CraftWorker | None = None
        self._active_data: dict | None = None

        layout = QVBoxLayout(self)

        # --- Active target group ---
        target_group = QGroupBox("Active Target")
        tg_layout = QHBoxLayout(target_group)
        self._lbl_target = QLabel("No active target set.")
        self._lbl_target.setWordWrap(True)
        self._btn_change = QPushButton("Change...")
        self._btn_change.setFixedWidth(90)
        tg_layout.addWidget(self._lbl_target, stretch=1)
        tg_layout.addWidget(self._btn_change)
        layout.addWidget(target_group)

        # --- Strategy selector ---
        strat_group = QGroupBox("Strategy")
        strat_layout = QHBoxLayout(strat_group)
        self._strategy_group = QButtonGroup(self)
        self._strategy_btns: dict[str, QRadioButton] = {}
        for key, label in STRATEGY_LABELS:
            btn = QRadioButton(label)
            self._strategy_btns[key] = btn
            self._strategy_group.addButton(btn)
            strat_layout.addWidget(btn)
        layout.addWidget(strat_group)

        # --- Settings row ---
        settings = QHBoxLayout()
        self._spin_countdown = QSpinBox()
        self._spin_countdown.setRange(1, 60)
        self._spin_countdown.setValue(4)
        self._spin_countdown.setSuffix("s")
        self._spin_countdown.setFixedWidth(60)
        settings.addWidget(QLabel("Countdown:"))
        settings.addWidget(self._spin_countdown)
        settings.addStretch()
        layout.addLayout(settings)

        # --- Run/Stop buttons ---
        btn_row = QHBoxLayout()
        self._btn_run = QPushButton("Run")
        self._btn_run.setFixedHeight(38)
        self._btn_run.setStyleSheet(
            "QPushButton { background: #2d6e1a; color: #ddd; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background: #3a8a22; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setFixedHeight(38)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(
            "QPushButton { background: #6e1a1a; color: #ddd; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background: #8a2222; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        btn_row.addWidget(self._btn_run, stretch=2)
        btn_row.addWidget(self._btn_stop, stretch=1)
        layout.addLayout(btn_row)

        # --- Status + log ---
        self._lbl_status = QLabel("Ready")
        self._lbl_status.setStyleSheet("font-style: italic; color: #aaa;")
        layout.addWidget(self._lbl_status)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        font = QFont("Consolas", 9)
        self._log.setFont(font)
        self._log.setPlaceholderText("Craft output will appear here...")
        layout.addWidget(self._log, stretch=1)

        # Connections
        self._btn_change.clicked.connect(lambda: self._main.tabs.setCurrentIndex(1))
        self._btn_run.clicked.connect(self._on_run)
        self._btn_stop.clicked.connect(self._on_stop)

        self._try_load_active()

    def _try_load_active(self) -> None:
        if TARGET_FILE.exists():
            try:
                data = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
                self.on_active_target_changed(data)
            except Exception:
                pass

    def on_active_target_changed(self, data: dict) -> None:
        self._active_data = data
        slug = data.get("slug", "?")
        mode = data.get("mode", "?")
        mods = mods_from_data(data)
        fifty = data.get("fifty_fifty", [])
        mod_lines = [f"  [{e['type'][:3].upper()}] {e['family']}  (T{e['min_tier']}+)" for e in mods]
        summary = f"<b>{slug}</b>  ({mode}, {len(mods)} mod(s))"
        if fifty:
            summary += f"  +{len(fifty)} 50-50"
        summary += "<br>" + "<br>".join(mod_lines)
        self._lbl_target.setText(summary)
        self._btn_run.setEnabled(True)

    def _selected_strategy(self) -> str | None:
        for key, btn in self._strategy_btns.items():
            if btn.isChecked():
                return key
        return None

    def _on_run(self) -> None:
        if self._active_data is None:
            QMessageBox.warning(
                self, "No Target",
                "Set an active target in the Targets tab first."
            )
            return

        strategy = self._selected_strategy()
        if strategy is None:
            QMessageBox.warning(self, "No Strategy", "Please select a crafting strategy first.")
            return
        countdown = self._spin_countdown.value()

        self._log.clear()
        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._lbl_status.setText("Running...")

        self._worker = CraftWorker(strategy, self._active_data, countdown)
        self._worker.log_line.connect(self._append_log)
        self._worker.status_changed.connect(self._lbl_status.setText)
        self._worker.finished.connect(self._on_craft_finished)
        self._worker.error.connect(self._on_craft_error)
        self._worker.mats_scanned.connect(self._main._materials_tab._on_scan_finished)
        self._worker.minimize_window.connect(
            self._main._maybe_minimize, Qt.ConnectionType.QueuedConnection
        )
        self._worker.restore_window.connect(
            self._main.showNormal, Qt.ConnectionType.QueuedConnection
        )
        self._worker.start()

    def _on_stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self._lbl_status.setText("Stopping...")
            self._btn_stop.setEnabled(False)

    def _on_craft_finished(self, success: bool) -> None:
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        if success:
            self._lbl_status.setText("Target found!")
            self._append_log("\n[DONE] Target condition met.")
        else:
            self._lbl_status.setText("Finished (no target found or stopped).")

    def _on_craft_error(self, msg: str) -> None:
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._lbl_status.setText(f"Error: {msg}")
        self._append_log(f"\nERROR: {msg}")

    def apply_default_strategy(self, key: str | None) -> None:
        if key and key in self._strategy_btns:
            self._strategy_btns[key].setChecked(True)
        else:
            for btn in self._strategy_btns.values():
                btn.setAutoExclusive(False)
                btn.setChecked(False)
                btn.setAutoExclusive(True)

    def _append_log(self, text: str) -> None:
        doc = self._log.document()
        if doc.blockCount() > 2000:
            cursor = self._log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()
        self._log.appendPlainText(text)
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.active_target_data: dict | None = None
        self._settings = load_settings()

        self.tabs = QTabWidget()
        self._materials_tab = MaterialsTab(self)
        self._targets_tab = TargetsTab(self)
        self._craft_tab = CraftTab(self)
        self._settings_tab = SettingsTab(self._settings)

        self.tabs.addTab(self._materials_tab, "Materials")
        self.tabs.addTab(self._targets_tab, "Targets")
        self.tabs.addTab(self._craft_tab, "Craft")
        self.tabs.addTab(self._settings_tab, "Settings")

        self.setCentralWidget(self.tabs)

        self._targets_tab.active_target_changed.connect(
            self._craft_tab.on_active_target_changed
        )
        self._settings_tab.auto_minimize_changed.connect(self._on_auto_minimize_changed)
        self._settings_tab.font_size_changed.connect(self._on_font_size_changed)
        self._settings_tab.default_strategy_changed.connect(
            self._craft_tab.apply_default_strategy
        )

        # Apply saved default strategy on startup
        default = self._settings.get("default_strategy")
        if default:
            self._craft_tab.apply_default_strategy(default)

        # Load active target into craft tab on startup
        if TARGET_FILE.exists():
            try:
                data = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
                self.active_target_data = data
            except Exception:
                pass

    def _maybe_minimize(self) -> None:
        if self._settings.get("auto_minimize", True):
            self.showMinimized()

    def _on_auto_minimize_changed(self, enabled: bool) -> None:
        self._settings["auto_minimize"] = enabled

    def _on_font_size_changed(self, size: int) -> None:
        app = QApplication.instance()
        base = app.font()
        base.setPointSize(size)
        app.setFont(base)
        for widget in app.allWidgets():
            f = widget.font()
            f.setPointSize(size)
            widget.setFont(f)
