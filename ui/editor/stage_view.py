# ui/editor/stage_view.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QKeyEvent
from PySide6.QtWidgets import QGraphicsView


class StageView(QGraphicsView):
    """Vista 2D con zoom (rotella), rotazione (Shift+rotella / [ ]),
    selezione rettangolare e snap alla griglia."""
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            self.renderHints() |
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, False)

    def wheelEvent(self, event):
        """Zoom con rotella, rotazione se premuto Shift."""
        modifiers = event.modifiers()
        delta = event.angleDelta().y()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Rotazione con Shift+Rotella
            step = 5 if abs(delta) < 120 else 15
            degrees = step if delta > 0 else -step
            self._rotate_selected(degrees)
        else:
            # Zoom normale
            factor = 1.1 if delta > 0 else 0.9
            self.scale(factor, factor)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_BracketLeft:
            self._rotate_selected(-15)
        elif event.key() == Qt.Key.Key_BracketRight:
            self._rotate_selected(15)
        elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            # Elimina selezionati (oltre al pulsante toolbar)
            scene = self.scene()
            if scene and hasattr(scene, 'push_remove_selected'):
                scene.push_remove_selected()
        elif event.key() == Qt.Key.Key_Escape:
            self.scene().clearSelection()
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
        # Forza refresh completo dopo rotazione collettiva
        if hasattr(scene, 'invalidate'):
            scene.invalidate()
