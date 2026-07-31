# ui/editor/stage_view.py
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QGraphicsView


class StageView(QGraphicsView):
    """Vista 2D con zoom (rotella), rotazione (Shift+rotella / [ ]),
    selezione rettangolare, snap alla griglia e modalità posizionamento
    shooting position.

    Signals:
        shootingPositionPlaced(x, y, is_start): emesso quando l'utente
            clicca sulla mappa in modalità posizionamento shooting position.
        obstaclePlaced(x, y, width, rotation, is_wall): emesso quando
            l'utente clicca in modalità posizionamento ostacolo.
    """

    shootingPositionPlaced = Signal(float, float, bool)  # x, y, is_start
    obstaclePlaced = Signal(float, float, float, float, bool)  # x, y, width, rotation, is_wall

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            self.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
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
        # Modalità posizionamento ostacoli
        self._placing_obstacle = False
        self._placing_is_wall = True  # True = muro, False = barriera
        self._placing_obstacle_width = 3.0  # larghezza default
        self._placing_obstacle_rotation = 0.0  # rotazione default

    # ── Modalità posizionamento shooting position ───────────────────

    def set_placing_position_mode(self, active: bool):
        """Attiva/disattiva la modalità posizionamento shooting position.

        Quando attiva, il click sinistro sulla mappa aggiunge una
        shooting position (la prima è Start, le successive intermedie).
        Disattiva eventuale modalità ostacoli.
        """
        self._placing_position = active
        self._pos_count = 0
        if active:
            self._placing_obstacle = False
        self._update_cursor_and_drag()

    def reset_placement_count(self):
        """Resetta il contatore posizioni (utile quando si svuota la lista)."""
        self._pos_count = 0

    # ── Modalità posizionamento ostacoli ───────────────────────────

    def set_placing_obstacle_mode(
        self, active: bool, is_wall: bool = True, width: float = 3.0, rotation: float = 0.0
    ):
        """Attiva/disattiva la modalità posizionamento ostacoli.

        Args:
            active: True per attivare.
            is_wall: True = muro, False = barriera.
            width: Larghezza dell'ostacolo in metri (default 3.0).
            rotation: Rotazione in gradi (default 0).
        """
        self._placing_obstacle = active
        if active:
            self._placing_is_wall = is_wall
            self._placing_obstacle_width = width
            self._placing_obstacle_rotation = rotation
            self._placing_position = False  # disattiva altra modalità
        self._update_cursor_and_drag()

    def set_obstacle_width(self, width: float):
        self._placing_obstacle_width = width

    # ── Helpers ────────────────────────────────────────────────────

    def _update_cursor_and_drag(self):
        """Aggiorna cursore e drag mode in base alla modalità attiva."""
        placing = self._placing_position or self._placing_obstacle
        if placing:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def _snap_to_grid(self, scene_pos) -> tuple[float, float]:
        """Snap coordinate a 0.5 metri."""
        if scene_pos is None:
            return (0.0, 0.0)
        snap = 0.5 * 40.0  # scala = 40 px/m
        x = round(scene_pos.x() / snap) * snap / 40.0
        y = round(scene_pos.y() / snap) * snap / 40.0
        return (x, y)

    # ── Eventi ───────────────────────────────────────────────────────

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
        # Modalità posizionamento shooting position
        if self._placing_position and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            x, y = self._snap_to_grid(scene_pos)
            is_start = self._pos_count == 0
            self._pos_count += 1
            self.shootingPositionPlaced.emit(x, y, is_start)
            event.accept()
            return

        # Modalità posizionamento ostacoli
        if self._placing_obstacle and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            x, y = self._snap_to_grid(scene_pos)
            self.obstaclePlaced.emit(
                x,
                y,
                self._placing_obstacle_width,
                self._placing_obstacle_rotation,
                self._placing_is_wall,
            )
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            if self._placing_position:
                if self._pos_count > 0:
                    self._pos_count -= 1
                event.accept()
                return
            if self._placing_obstacle:
                event.accept()
                return

        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_BracketLeft:
            self._rotate_selected(-15)
        elif event.key() == Qt.Key.Key_BracketRight:
            self._rotate_selected(15)
        elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self._delete_selected()
        elif event.key() == Qt.Key.Key_Escape:
            if self._placing_position:
                self.set_placing_position_mode(False)
            if self._placing_obstacle:
                self.set_placing_obstacle_mode(False)
            scene = self.scene()
            if scene:
                scene.clearSelection()
        else:
            super().keyPressEvent(event)

    def _delete_selected(self):
        """Elimina gli oggetti selezionati delegando alla scena."""
        scene = self.scene()
        if scene is None:
            return
        if hasattr(scene, "push_remove_selected"):
            scene.push_remove_selected()

    def _rotate_selected(self, degrees: float):
        """Ruota tutti gli oggetti selezionati di `degrees` gradi."""
        scene = self.scene()
        if scene is None:
            return
        for g_item in scene.selectedItems():
            wrapper = getattr(g_item, "wrapper", None)
            if wrapper is None:
                continue
            wrapper.item.rotation = (wrapper.item.rotation + degrees) % 360
            g_item.setRotation(wrapper.item.rotation)
            wrapper.changed.emit()
        if hasattr(scene, "invalidate"):
            scene.invalidate()
