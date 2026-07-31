"""
Shooting path editor for OpenTDS.

Provides:
- PathPolylineItem: QGraphicsItem rendering the shooter's path as a polyline
- PathEditorPanel: QDockWidget for managing waypoints and engagements
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from core.models import Stage
from core.path import ShootingPath
from core.scoring import is_blocking_wall, is_scoring_target
from ui.icons import load_icon

# ═══════════════════════════════════════════════════════════════════════════════
#  PathPolylineItem — rendering della polilinea sulla scena QGraphics
# ═══════════════════════════════════════════════════════════════════════════════


class PathPolylineItem(QGraphicsItem):
    """Rende il percorso del tiratore come polilinea con frecce e distanze.

    Si aggiorna automaticamente quando il path cambia.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._waypoints: list[tuple[float, float, str, bool]] = []
        self._scale: float = 40.0
        self._visible: bool = True
        self._path_color: str = "#3b82f6"
        self.setZValue(5)  # sopra la griglia, sotto i bersagli
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def set_path(
        self,
        waypoints: list[tuple[float, float, str, bool]],
        scale: float,
        color: str = "#3b82f6",
    ):
        """Set the path waypoints and redraw.

        Args:
            waypoints: List of (x, y, label, is_start)
            scale: Scene scale factor (pixels per meter)
            color: Hex color for the path line
        """
        self._waypoints = list(waypoints)
        self._scale = scale
        self._path_color = color
        self.prepareGeometryChange()
        self.setVisible(self._visible)
        self.update()

    def set_path_visible(self, visible: bool):
        """Toggle path visibility."""
        self._visible = visible
        self.setVisible(visible)
        self.update()

    def boundingRect(self) -> QRectF:
        if not self._waypoints:
            return QRectF()
        xs = [p[0] * self._scale for p in self._waypoints]
        ys = [p[1] * self._scale for p in self._waypoints]
        margin = 30
        return QRectF(
            min(xs) - margin,
            min(ys) - margin,
            max(xs) - min(xs) + margin * 2,
            max(ys) - min(ys) + margin * 2,
        )

    def paint(self, painter: QPainter, option, widget=None):
        if len(self._waypoints) < 2:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(self._path_color)
        s = self._scale

        # ── Polyline ──
        pen = QPen(color, 3)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)

        path = QPainterPath()
        x0, y0, _, _ = self._waypoints[0]
        path.moveTo(x0 * s, y0 * s)
        for i in range(1, len(self._waypoints)):
            x, y, _, _ = self._waypoints[i]
            path.lineTo(x * s, y * s)
        painter.drawPath(path)

        # ── Direction arrows ──
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(color))

        for i in range(1, len(self._waypoints)):
            x1, y1, _, _ = self._waypoints[i - 1]
            x2, y2, _, _ = self._waypoints[i]
            # Midpoint of segment
            mx = (x1 + x2) / 2 * s
            my = (y1 + y2) / 2 * s
            # Direction
            angle = math.atan2(y2 - y1, x2 - x1)
            # Draw arrowhead
            arrow_size = 8
            for side in [-1, 1]:
                ax = mx + math.cos(angle + side * 2.5) * arrow_size
                ay = my + math.sin(angle + side * 2.5) * arrow_size
                painter.drawLine(QPointF(mx, my), QPointF(ax, ay))

        # ── Waypoint markers ──
        for i, (x, y, label, is_start) in enumerate(self._waypoints):
            px, py = x * s, y * s

            # Circle
            marker_color = QColor("#22c55e") if is_start else QColor(color)
            painter.setBrush(QBrush(marker_color))
            painter.setPen(QPen(QColor("#1e293b"), 1.5))
            painter.drawEllipse(QPointF(px, py), 10, 10)

            # Label inside
            painter.setPen(QPen(QColor("white"), 1))
            f = painter.font()
            f.setPointSize(8)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(
                QRectF(px - 9, py - 9, 18, 18),
                Qt.AlignmentFlag.AlignCenter,
                str(i + 1),
            )

            # Distance label
            if i > 0:
                x_prev, y_prev, _, _ = self._waypoints[i - 1]
                dist_m = math.hypot(x - x_prev, y - y_prev)
                mid_x = (px + x_prev * s) / 2
                mid_y = (py + y_prev * s) / 2
                painter.setPen(QPen(QColor("#64748b"), 1))
                f2 = painter.font()
                f2.setPointSize(7)
                f2.setBold(False)
                painter.setFont(f2)
                painter.drawText(
                    QRectF(mid_x - 20, mid_y - 14, 40, 12),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{dist_m:.1f}m",
                )

        painter.restore()


# ═══════════════════════════════════════════════════════════════════════════════
#  PathEditorPanel — pannello di controllo del percorso
# ═══════════════════════════════════════════════════════════════════════════════


class PathEditorPanel(QFrame):
    """Pannello per editare il percorso di tiro.

    Signals:
        pathChanged: emesso quando il percorso viene modificato
        waypointSelected(int): emesso quando un waypoint viene selezionato
        waypointMoved(int, float, float): waypoint spostato (id, x, y)
    """

    pathChanged = Signal()
    waypointSelected = Signal(int)  # waypoint id
    waypointMoved = Signal(int, float, float)  # id, x, y

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stage: Stage | None = None
        self._shooting_path: ShootingPath | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        title = QLabel("Percorso di Tiro")
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #0f172a;")
        layout.addWidget(title)

        desc = QLabel(
            "Disegna il percorso che il tiratore segue nello stage.\n"
            "Usa le posizioni di tiro come waypoint."
        )
        desc.setStyleSheet("font-size: 11px; color: #64748b;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Visibility toggle
        self._vis_check = QCheckBox("Mostra percorso")
        self._vis_check.setChecked(True)
        self._vis_check.toggled.connect(self._on_visibility_toggled)
        layout.addWidget(self._vis_check)

        # Auto-generate button
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_auto = QPushButton(load_icon("path_reset"), "Auto-genera")
        self._btn_auto.setToolTip("Genera il percorso dalle posizioni di tiro esistenti")
        self._btn_auto.clicked.connect(self._on_auto_generate)
        btn_row.addWidget(self._btn_auto)

        self._btn_clear = QPushButton(load_icon("delete"), "Cancella")
        self._btn_clear.setToolTip("Rimuovi tutti i waypoint")
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_clear)

        layout.addLayout(btn_row)

        # Waypoint list
        self._list_label = QLabel("Waypoint (trascina per riordinare)")
        self._list_label.setStyleSheet("font-size: 11px; color: #64748b; margin-top: 8px;")
        layout.addWidget(self._list_label)

        self._waypoint_list = QListWidget()
        self._waypoint_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self._waypoint_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._waypoint_list.setMinimumHeight(120)
        self._waypoint_list.model().rowsMoved.connect(self._on_rows_moved)
        self._waypoint_list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self._waypoint_list, 1)

        # Status
        self._status_label = QLabel("Nessun percorso definito")
        self._status_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        layout.addWidget(self._status_label)

    # ── Public API ──────────────────────────────────────────────────────

    def set_stage(self, stage: Stage):
        """Set the stage and auto-generate path from shooting positions."""
        self._stage = stage
        self._on_auto_generate()

    def get_shooting_path(self) -> ShootingPath | None:
        """Return the current shooting path."""
        return self._shooting_path

    def get_waypoint_data(self) -> list[tuple[float, float, str, bool]]:
        """Return waypoint data for PathPolylineItem rendering.

        Returns: list of (x, y, label, is_start) in order
        """
        if not self._shooting_path:
            return []
        return [(wp.x, wp.y, wp.label, wp.is_start) for wp in self._shooting_path.ordered_waypoints]

    def sync_from_stage(self):
        """Sync path from stage.shooting_positions (after external changes)."""
        if not self._stage:
            return
        self._on_auto_generate()

    # ── UI Handlers ─────────────────────────────────────────────────────

    def _on_auto_generate(self):
        """Generate path from existing shooting positions.
        Ordina le posizioni con il percorso minimo
        evitando barriere e muri.
        Il percorso resta sempre dentro l'area di tiro."""
        if not self._stage:
            return

        targets = [it for it in self._stage.items if is_scoring_target(it.item_type)]
        blockers = [it for it in self._stage.items if is_blocking_wall(it.item_type)]
        # Recupera il poligono dell'area di tiro
        perimeter_poly = self._stage.properties.get("perimeter_poly")
        self._shooting_path = ShootingPath.from_shooting_positions(
            self._stage.shooting_positions,
            targets=targets,
            blockers=blockers,
            perimeter_poly=perimeter_poly,
        )
        self._refresh_list()
        self._update_status()
        self.pathChanged.emit()

    def _on_clear(self):
        """Clear all waypoints."""
        self._shooting_path = None
        self._waypoint_list.clear()
        self._update_status()
        self.pathChanged.emit()

    def _on_visibility_toggled(self, checked: bool):
        """Toggle path visibility."""
        if self._shooting_path:
            self._shooting_path.visible = checked
        self.pathChanged.emit()

    def _on_rows_moved(self):
        """Handle drag-reorder in the waypoint list."""
        if not self._shooting_path:
            return
        # Read new order from list widget
        new_ids: list[int] = []
        for i in range(self._waypoint_list.count()):
            item = self._waypoint_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole):
                new_ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        if new_ids:
            self._shooting_path.reorder(new_ids)
        self.pathChanged.emit()

    def _on_selection_changed(self, row: int):
        """Emit waypointSelected when user selects a waypoint."""
        if row < 0 or not self._shooting_path:
            return
        item = self._waypoint_list.item(row)
        if item and item.data(Qt.ItemDataRole.UserRole):
            wp_id = int(item.data(Qt.ItemDataRole.UserRole))
            self.waypointSelected.emit(wp_id)

    # ── Internal ────────────────────────────────────────────────────────

    def _refresh_list(self):
        """Rebuild the waypoint list from the current path."""
        self._waypoint_list.blockSignals(True)
        self._waypoint_list.clear()

        if not self._shooting_path:
            self._waypoint_list.blockSignals(False)
            return

        for wp in self._shooting_path.ordered_waypoints:
            engaged_count = len(wp.engaged_target_ids)
            visible_count = len(wp.visible_target_ids)
            start_mark = " [START]" if wp.is_start else ""
            text = f"#{wp.order + 1}{start_mark} — ({wp.x:.1f}, {wp.y:.1f})"
            if engaged_count > 0:
                text += f" [{engaged_count} bersagli]"
            elif visible_count > 0:
                text += f" [{visible_count} visibili]"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, str(wp.id))
            if wp.is_start:
                item.setForeground(QColor("#22c55e"))
            self._waypoint_list.addItem(item)

        self._waypoint_list.blockSignals(False)

    def _update_status(self):
        """Update status label."""
        if not self._shooting_path or not self._shooting_path.waypoints:
            self._status_label.setText("Nessun percorso definito")
        else:
            n = len(self._shooting_path.waypoints)
            total_dist = 0.0
            ordered = self._shooting_path.ordered_waypoints
            for i in range(1, len(ordered)):
                total_dist += math.hypot(
                    ordered[i].x - ordered[i - 1].x,
                    ordered[i].y - ordered[i - 1].y,
                )
            self._status_label.setText(
                f"{n} waypoint{'i' if n != 1 else 'o'} · {total_dist:.1f}m totali"
            )
