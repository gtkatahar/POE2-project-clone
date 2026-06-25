"""CalibrationOverlay — drag-to-select screen overlay for inventory grid calibration."""

import pyautogui
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout

# Ignore drags smaller than this (accidental clicks, not a real grid box)
_MIN_DRAG_PX = 10


class CalibrationOverlay(QDialog):
    """Fullscreen translucent overlay: drag a box around the inventory grid.

    Coordinates are read via pyautogui.position() (not Qt mouse events) so
    they stay in the same coordinate space windows/inventory.py already uses
    for cell_center()/_scale_coords(). Qt's own mouse-event coordinates are
    used only to draw the visual rubber-band rectangle.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(QApplication.primaryScreen().geometry())

        self._dragging = False
        self._start_widget: QPoint | None = None
        self._end_widget: QPoint | None = None
        self._start_screen: tuple[int, int] | None = None
        self._box: tuple[int, int, int, int] | None = None

        hint = QLabel(
            "Drag a box around the full inventory grid — from the outer "
            "top-left corner of the first cell to the outer bottom-right "
            "corner of the last cell.  Esc to cancel.",
            self,
        )
        hint.setStyleSheet(
            "color: white; background: rgba(0,0,0,180); padding: 8px; font-size: 13px;"
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(hint, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

    def result_box(self) -> tuple[int, int, int, int] | None:
        """Return (x1, y1, x2, y2) in screen coords, or None if cancelled."""
        return self._box

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        self._dragging = True
        self._start_widget = event.position().toPoint()
        self._end_widget = self._start_widget
        self._start_screen = pyautogui.position()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._end_widget = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        x1, y1 = self._start_screen
        x2, y2 = pyautogui.position()

        if abs(x2 - x1) < _MIN_DRAG_PX or abs(y2 - y1) < _MIN_DRAG_PX:
            self._start_widget = None
            self.update()
            return

        self._box = (x1, y1, x2, y2)
        self.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self._start_widget and self._end_widget:
            rect = QRect(self._start_widget, self._end_widget).normalized()
            painter.fillRect(rect, QColor(255, 200, 0, 40))
            painter.setPen(QPen(QColor(255, 200, 0), 2))
            painter.drawRect(rect)
