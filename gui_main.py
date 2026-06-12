"""Entry point for the POE2 Crafting Tool GUI."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor, QIcon

from gui_window import MainWindow
from gui_settings import load_settings


def _apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()

    dark   = QColor(28, 28, 30)
    mid    = QColor(44, 44, 46)
    light  = QColor(58, 58, 62)
    text   = QColor(220, 220, 220)
    dim    = QColor(110, 110, 115)
    gold   = QColor(180, 140, 55)    # POE gold accent
    hl_bg  = QColor(60, 47, 15)      # highlight background

    p.setColor(QPalette.ColorRole.Window,          dark)
    p.setColor(QPalette.ColorRole.WindowText,      text)
    p.setColor(QPalette.ColorRole.Base,            mid)
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(38, 38, 40))
    p.setColor(QPalette.ColorRole.ToolTipBase,     mid)
    p.setColor(QPalette.ColorRole.ToolTipText,     text)
    p.setColor(QPalette.ColorRole.Text,            text)
    p.setColor(QPalette.ColorRole.Button,          light)
    p.setColor(QPalette.ColorRole.ButtonText,      text)
    p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 100, 100))
    p.setColor(QPalette.ColorRole.Link,            gold)
    p.setColor(QPalette.ColorRole.Highlight,       gold)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(20, 20, 20))

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, dim)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, dim)

    app.setPalette(p)

    # Additional stylesheet tweaks
    app.setStyleSheet("""
        QTabWidget::pane { border: 1px solid #444; }
        QTabBar::tab {
            background: #3a3a3c;
            color: #bbb;
            padding: 6px 18px;
            border: 1px solid #555;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #1c1c1e;
            color: #b8943f;
            font-weight: bold;
        }
        QTabBar::tab:hover { background: #4a4a4e; }
        QGroupBox {
            border: 1px solid #555;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 4px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            color: #b8943f;
        }
        QHeaderView::section {
            background: #3a3a3c;
            color: #ccc;
            border: 1px solid #555;
            padding: 3px;
        }
        QScrollBar:vertical {
            background: #2c2c2e;
            width: 10px;
        }
        QScrollBar::handle:vertical {
            background: #555;
            border-radius: 5px;
            min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QSplitter::handle { background: #444; }
        QToolButton {
            background: transparent;
            border: none;
            color: #b8943f;
            padding: 2px 4px;
        }
        QToolButton:hover { color: #d4a840; }
    """)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("POE2 Crafting Tool")
    _apply_dark_palette(app)

    settings = load_settings()
    font = app.font()
    font.setPointSize(settings["font_size"])
    app.setFont(font)

    window = MainWindow()
    window.setWindowTitle("POE2 Crafting Tool")
    window.resize(1150, 720)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
