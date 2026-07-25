# ui/editor/stage_view.py
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QKeyEvent, QMouseEvent, QCursor
from PySide6.QtWidgets import QGraphicsView


class StageView(QGraphicsView):
    """Vista 2D con zoom (rotella), rotazione (Shift+rotella / [ ]),
    selezione rettangolare, snap alla griglia e modalità posizionamento
    shooting position.

    Signals:
        shootingPositionPlaced(x, y, is_start): emesso quando l'utente
            clicca sulla mappa in modalità posizionamento shooting position.
    """

    shootingPositionPlaced = Signal(float, float, bool)  # x, y, is_start

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

        # Modalità posizionamento shooting position
        self._placing_position = False
        self._pos_count = 0  # contatore posizioni piazzate

    def set_placing_position_mode(self, active: bool):
        """Attiva/disattiva la modalità posizionamento shooting position.

        Quando attiva, il click sinistro sulla mappa aggiunge una
        shooting position (la prima è Start, le successive intermedie).
        """
        self._placing_position = active
        self._pos_count = 0
        if active:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def reset_placement_count(self):
        """Resetta il contatore posizioni (utile quando si svuota la lista)."""
        self._pos_count = 0

    def wheelEvent(self, event):
        """Zoom con rotella, rotazione se premuto Shift."""
        modifiers = event.modifiers()
        delta = event.angleDelta().y()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            step = 5 if abs(delta) < 120 else 15
            degrees = step if delta > 0 else -step
            self._rotate_selected(degrees)
        else:
            factor = 1.1 if delta > 0 else 0.9
            self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent):
        if self._placing_position and event.button() == Qt.MouseButton.LeftButton:
            # Converte coordinate schermo → scena
            scene_pos = self.mapToScene(event.pos())
            if scene_pos is None:
                return
            # Snap a 0.5 m
            snap = 0.5 * 40.0  # scala = 40 px/m
            x = round(scene_pos.x() / snap) * snap / 40.0
            y = round(scene_pos.y() / snap) * snap / 40.0
            is_start = (self._pos_count == 0)
            self._pos_count += 1
            self.shootingPositionPlaced.emit(x, y, is_start)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton and self._placing_position:
            # Click destro: rimuove l'ultima posizione
            if self._pos_count > 0:
                self._pos_count -= 1
            event.accept()
            return

        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_BracketLeft:
            self._rotate_selected(-15)
        elif event.key() == Qt.Key.Key_BracketRight:
            self._rotate_selected(15)
        elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            scene = self.scene()
            if scene and hasattr(scene, 'push_remove_selected'):
                scene.push_remove_selected()
        elif event.key() == Qt.Key.Key_Escape:
            if self._placing_position:
                self.set_placing_position_mode(False)
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
        if hasattr(scene, 'invalidate'):
            scene.invalidate()
