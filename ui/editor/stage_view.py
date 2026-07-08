# ui/editor/stage_view.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QKeyEvent
from PySide6.QtWidgets import QGraphicsView


class StageView(QGraphicsView):
    """Vista 2D con zoom tramite rotella e rotazione tramite tastiera."""
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            self.renderHints() |
            QPainter.RenderHint.Antialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 0.9
        self.scale(factor, factor)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_BracketLeft:
            self._rotate_selected(-15)
        elif event.key() == Qt.Key.Key_BracketRight:
            self._rotate_selected(15)
        else:
            super().keyPressEvent(event)

    def _rotate_selected(self, degrees: float):
        """Ruota tutti gli oggetti selezionati di `degrees` gradi."""
        scene = self.scene()
        if scene is None:
            return
        for g_item in scene.selectedItems():
            wrapper = getattr(g_item, 'wrapper', None)
            if wrapper is None:
                continue
            wrapper.item.rotation = (wrapper.item.rotation + degrees) % 360
            g_item.setRotation(wrapper.item.rotation)
            wrapper.changed.emit()
