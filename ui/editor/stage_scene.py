"""
Scena 2D con undo/redo, griglia, snap e tutti i tipi di oggetto.

Architettura:
  StageItemMixin  → logica comune (snap, rotazione, selezione, sincronia modello)
  ┣━ RectItem     → muri, barriere, porte, swinger, drop_turner, mover
  ┣━ EllipseItem  → bersagli cartacei, metallici, no-shoot
  ┗━ FaultLineItem → linea personalizzata
"""
from __future__ import annotations
from typing import Optional, Callable
import math
from PySide6.QtCore import Qt, Signal, QObject, QPointF, QRectF
from PySide6.QtGui import (
    QPen, QBrush, QColor, QPainter, QPainterPath, QPixmap,
    QUndoStack, QUndoCommand,
)
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsRectItem, QGraphicsEllipseItem,
    QGraphicsItem, QGraphicsPixmapItem,
)

from core.models import Stage, StageItem, ItemType
from core.collision import make_obb, item_obb, overlaps as shapely_overlaps
from shapely.geometry import box as shapely_box, Point as ShapelyPoint

from ui.editor.target_images import TargetImageManager


# Helper per classificazione tipi (condivisa con generator)
def _is_paper_like(t: ItemType) -> bool:
    return t in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET)
def _is_steel_like(t: ItemType) -> bool:
    return t in (ItemType.STEEL_TARGET, ItemType.POPPER, ItemType.METAL_PLATE)
def _is_scoring_target(t: ItemType) -> bool:
    return _is_paper_like(t) or _is_steel_like(t) or t in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
def _is_obstacle(t: ItemType) -> bool:
    return t in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR, ItemType.HARD_COVER, ItemType.SOFT_COVER)


# ═══════════════════════════════════════════════════════════════════════════════
#  Utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _snap_pos(pos: QPointF, scale: float) -> QPointF:
    """Snap a metà della griglia (0.5 m · scale)."""
    snap = 0.5 * scale
    x = round(pos.x() / snap) * snap
    y = round(pos.y() / snap) * snap
    return QPointF(x, y)


# ═══════════════════════════════════════════════════════════════════════════════
#  Wrapper
# ═══════════════════════════════════════════════════════════════════════════════

class StageItemWrapper(QObject):
    """Wrapper Qt per uno StageItem — emette changed quando l'item viene modificato."""
    changed = Signal()

    def __init__(self, item: StageItem, parent=None):
        super().__init__(parent)
        self.item = item


# ═══════════════════════════════════════════════════════════════════════════════
#  Griglia
# ═══════════════════════════════════════════════════════════════════════════════

class GridItem(QGraphicsItem):
    """Griglia metrica sullo sfondo con confini, parapalle e indicazioni direzionali."""
    def __init__(self, width_m: float, depth_m: float, scale: float = 40.0, parent=None):
        super().__init__(parent)
        self.width_m = width_m
        self.depth_m = depth_m
        self.scale = scale
        self.pen = QPen(QColor("#e2e8f0"))
        self.pen.setWidthF(1)

    def boundingRect(self):
        margin = 60
        return QRectF(-margin, -margin,
                       self.width_m * self.scale + margin * 2,
                       self.depth_m * self.scale + margin * 2)

    def paint(self, painter, option, widget=None):
        w = self.width_m * self.scale
        h = self.depth_m * self.scale

        # Parapalle di fondo
        backstop_brush = QBrush(QColor("#5c3a1e"))
        backstop_brush.setStyle(Qt.BrushStyle.CrossPattern)
        painter.setBrush(backstop_brush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, int(h - 20), int(w), 20)
        painter.setPen(QPen(QColor("#5c3a1e"), 1))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(4, int(h - 6), "⬇ PARAPALLE DI FONDO")

        # Area di partenza
        start_brush = QBrush(QColor("#22c55e"))
        start_brush.setStyle(Qt.BrushStyle.Dense4Pattern)
        painter.setBrush(start_brush)
        painter.setPen(Qt.PenStyle.NoPen)
        sw = 2.0 * self.scale
        sh = 2.0 * self.scale
        painter.drawRect(int(w / 2 - sw / 2), 0, int(sw), int(sh))

        # Griglia
        painter.setPen(self.pen)
        for i in range(int(self.width_m) + 1):
            x = i * self.scale
            painter.drawLine(int(x), 0, int(x), int(h))
        for i in range(int(self.depth_m) + 1):
            y = i * self.scale
            painter.drawLine(0, int(y), int(w), int(y))

        # Etichette
        font.setPointSize(8)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#22c55e"), 1))
        painter.drawText(4, 14, "🟢 UP-RANGE (ingresso tiratore)")
        painter.setPen(QPen(QColor("#ef4444"), 1))
        painter.drawText(4, int(h - 22), "🔴 DOWN-RANGE (verso parapalle)")


# ═══════════════════════════════════════════════════════════════════════════════
#  StageItemMixin — logica comune a tutti gli item grafici
# ═══════════════════════════════════════════════════════════════════════════════

class StageItemMixin:
    """Mixin che fornisce a ogni item grafico:
    - snap alla griglia durante il drag
    - sincronia bidirezionale con StageItem (posizione, rotazione)
    - handle di rotazione trascinabile
    - evidenziazione selezione (dashed border)
    - hover cursor
    """

    # ---- init helper (chiamato dalle sottoclassi) ----

    def stage_item_init(self, wrapper: StageItemWrapper, scale: float):
        """Inizializza il mixin. Chiamare nel __init__ della sottoclasse."""
        self.wrapper = wrapper
        self.scale = scale
        self._is_rotating = False
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    # ---- Sincronia posizione / modello ----

    def update_from_model(self):
        """Aggiorna posizione e rotazione dal modello. Le sottoclassi
        sovrascrivono per impostare anche la forma (rect/ellisse)."""
        it = self.wrapper.item
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    # ---- Collisione ostacoli e blocchi percorso ----

    _OBSTACLE_TYPES = {ItemType.WALL, ItemType.BARRIER, ItemType.DOOR}
    # Tipi di bersaglio che non devono essere coperti da ostacoli
    _TARGET_TYPES = {
        ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
        ItemType.POPPER, ItemType.METAL_PLATE,
        ItemType.MINI_TARGET, ItemType.MICRO_TARGET,
        ItemType.NO_SHOOT, ItemType.SWINGER,
        ItemType.DROP_TURNER, ItemType.MOVER,
    }

    def _would_collide_with_obstacles(self, new_pos: QPointF) -> bool:
        """True se il nuovo posizionamento causa sovrapposizione con
        un altro ostacolo (muro, barriera, porta) o copre un bersaglio."""
        it = self.wrapper.item
        if it.item_type not in self._OBSTACLE_TYPES:
            return False

        scene: "StageScene" = self.scene()
        if scene is None:
            return False

        new_x = new_pos.x() / self.scale
        new_y = new_pos.y() / self.scale
        new_obb = make_obb(new_x, new_y,
                           max(it.width, 0.05), max(it.height, 0.05),
                           it.rotation)

        MIN_GAP = 0.05  # 5 cm

        # 1. Contro altri ostacoli (muri, barriere, porte)
        for other_id, other_g in scene._items.items():
            if other_id == it.id:
                continue
            other_it = getattr(other_g, 'wrapper', None)
            if other_it is None:
                continue
            other_it = other_it.item
            if other_it.item_type not in self._OBSTACLE_TYPES:
                continue
            other_obb = item_obb(other_it)
            if other_obb is not None and shapely_overlaps(new_obb, other_obb, MIN_GAP):
                return True

        # 2. Contro bersagli (non devono essere coperti dall'ostacolo)
        MIN_TARGET_GAP = 0.3  # 30 cm
        for other_id, other_g in scene._items.items():
            if other_id == it.id:
                continue
            other_it = getattr(other_g, 'wrapper', None)
            if other_it is None:
                continue
            other_it = other_it.item
            if other_it.item_type not in self._TARGET_TYPES:
                continue
            other_obb = item_obb(other_it)
            if other_obb is not None and shapely_overlaps(new_obb, other_obb, MIN_TARGET_GAP):
                return True

        # 3. Contro i bordi dello stage (non devono sporgere oltre)
        stage = scene.stage
        stage_obb = shapely_box(0, 0, stage.width, stage.depth)
        if not stage_obb.contains(new_obb):
            return True

        return False

    def _would_block_shooter_path(self, new_pos: QPointF) -> bool:
        """True se il posizionamento isolerebbe una posizione di tiro
        dal resto dell'area (shooting position tagliata fuori)."""
        it = self.wrapper.item
        if it.item_type not in self._OBSTACLE_TYPES:
            return False

        scene: "StageScene" = self.scene()
        if scene is None:
            return False

        # Solo se ci sono shooting positions definite
        if not scene.stage.shooting_positions:
            return False

        from shapely import union_all, difference

        new_x = new_pos.x() / self.scale
        new_y = new_pos.y() / self.scale
        new_obb = make_obb(new_x, new_y,
                           max(it.width, 0.05), max(it.height, 0.05),
                           it.rotation)

        # Raccogli TUTTI gli ostacoli (incluso questo nella nuova posizione)
        obstacles = [new_obb]
        for other_id, other_g in scene._items.items():
            if other_id == it.id:
                continue
            other_it = getattr(other_g, 'wrapper', None)
            if other_it is None:
                continue
            other_it = other_it.item
            if other_it.item_type not in self._OBSTACLE_TYPES:
                continue
            other_obb = item_obb(other_it)
            if other_obb is not None:
                obstacles.append(other_obb)

        if not obstacles:
            return False

        # Unione ostacoli
        obs_union = union_all(obstacles)

        # Area stage meno ostacoli
        stage = scene.stage
        stage_area = shapely_box(0, 0, stage.width, stage.depth)
        accessible = difference(stage_area, obs_union)

        if accessible.is_empty:
            return True  # Nessuna area accessibile!

        # Se ci sono più regioni separate, verifica che ogni shooting position
        # sia nella stessa regione (nessuna isolata)
        if hasattr(accessible, 'geoms'):
            regions = list(accessible.geoms)
            if len(regions) > 1:
                # Raccogli shooting positions
                sp_points = [
                    ShapelyPoint(sp.x, sp.y)
                    for sp in scene.stage.shooting_positions
                ]
                if sp_points:
                    # Trova in quale regione sta la prima shooting position
                    first_sp = sp_points[0]
                    main_region_idx = -1
                    for i, reg in enumerate(regions):
                        if reg.contains(first_sp):
                            main_region_idx = i
                            break

                    if main_region_idx >= 0:
                        # Verifica che TUTTE le shooting position siano
                        # nella stessa regione principale
                        for sp_pt in sp_points:
                            if not regions[main_region_idx].contains(sp_pt):
                                return True  # Shooting position isolata!

        return False

    # ---- Sincronia posizione / modello ----

    def update_from_model(self):
        """Aggiorna posizione e rotazione dal modello. Le sottoclassi
        sovrascrivono per impostare anche la forma (rect/ellisse)."""
        it = self.wrapper.item
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            snapped = _snap_pos(value, self.scale)
            if self._would_collide_with_obstacles(snapped):
                return self.pos()  # Rifiuta la mossa
            if self._would_block_shooter_path(snapped):
                return self.pos()  # Rifiuta — blocca il passaggio tiratore
            return snapped
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    # ---- Handle di rotazione ----

    def _rotation_handle_rect(self) -> QRectF:
        br = self.boundingRect()
        handle_size = 12.0
        cx = br.center().x()
        top = br.top()
        return QRectF(cx - handle_size / 2, top - handle_size - 8, handle_size, handle_size)

    # ---- Evidenziazione violazioni ----

    def _draw_violation_highlight(self, painter: QPainter):
        """Disegna un bordo rosso pulsante se l'item ha una violazione IPSC."""
        if not self.wrapper or not self.scene():
            return
        scene: "StageScene" = self.scene()
        if not scene.has_violation(self.wrapper.item.id):
            return
        painter.save()
        pen = QPen(QColor("#dc2626"), 3)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        br = self.boundingRect()
        margin = 6.0
        painter.drawRoundedRect(
            br.adjusted(-margin, -margin, margin, margin),
            8, 8
        )
        painter.restore()

    def _draw_rotation_handle(self, painter: QPainter):
        if not self.isSelected():
            return
        painter.save()
        br = self.boundingRect()
        center = br.center()
        handle_center = self._rotation_handle_rect().center()
        pen = QPen(QColor("#2563eb"), 2)
        painter.setPen(pen)
        painter.drawLine(center, handle_center)
        painter.setBrush(QBrush(QColor("#2563eb")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self._rotation_handle_rect())
        painter.setPen(QPen(QColor("white"), 1))
        f = painter.font()
        f.setPointSize(7)
        painter.setFont(f)
        painter.drawText(self._rotation_handle_rect(), Qt.AlignmentFlag.AlignCenter, "↻")
        painter.restore()

    def _handle_press_on_rotation(self, pos: QPointF) -> bool:
        return self._rotation_handle_rect().contains(pos)

    def mousePressEvent(self, event):
        if self._handle_press_on_rotation(event.pos()):
            if not self.isSelected():
                if self.scene():
                    self.scene().clearSelection()
                self.setSelected(True)
            self._is_rotating = True
            origin = self.scenePos()
            mouse_scene = self.mapToScene(event.pos())
            self._start_scene_angle = math.atan2(
                mouse_scene.y() - origin.y(), mouse_scene.x() - origin.x()
            )
            self._start_rotation = self.rotation()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_rotating:
            origin = self.scenePos()
            mouse_scene = self.mapToScene(event.pos())
            current_angle = math.atan2(
                mouse_scene.y() - origin.y(), mouse_scene.x() - origin.x()
            )
            delta = math.degrees(current_angle - self._start_scene_angle)
            new_rotation = self._start_rotation + delta
            self.setRotation(new_rotation)
            self.wrapper.item.rotation = new_rotation
            self.wrapper.changed.emit()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_rotating:
            self._is_rotating = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        if self.isSelected() and self._handle_press_on_rotation(event.pos()):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverMoveEvent(event)

    # ---- Evidenziazione selezione ----

    def _draw_selection_highlight(self, painter: QPainter):
        """Disegna il bordo tratteggiato di selezione."""
        if not self.isSelected():
            return
        pen = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        br = self.boundingRect().adjusted(-4, -4, 4, 4)
        if isinstance(self, QGraphicsEllipseItem):
            painter.drawEllipse(br)
        elif isinstance(self, QGraphicsRectItem):
            painter.drawRect(br)
        # FaultLineGraphicsItem gestisce il proprio bounding rect in paint()


# ═══════════════════════════════════════════════════════════════════════════════
#  Item grafici concreti (ciascuno eredita StageItemMixin + base Qt)
# ═══════════════════════════════════════════════════════════════════════════════

class RectGraphicsItem(StageItemMixin, QGraphicsRectItem):
    """Classe base per item con forma rettangolare: muro, barriera, porta, bersagli mobili."""

    def __init__(self, wrapper: StageItemWrapper, scale: float,
                 color: str, pen_color: str = "#0f172a", pen_width: int = 2,
                 brush_alpha: int = 255, pen_style: Qt.PenStyle = Qt.PenStyle.SolidLine,
                 parent=None):
        QGraphicsRectItem.__init__(self, parent)
        self.stage_item_init(wrapper, scale)
        self._rect_brush = QBrush(QColor(color))
        if brush_alpha < 255:
            c = QColor(color)
            c.setAlpha(brush_alpha)
            self._rect_brush = QBrush(c)
        self._rect_pen = QPen(QColor(pen_color), pen_width)
        self._rect_pen.setStyle(pen_style)
        self.update_from_model()

    def update_from_model(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        self.setRect(-w / 2, -h / 2, w, h)
        super().update_from_model()

    def paint(self, painter, option, widget=None):
        painter.setBrush(self._rect_brush)
        painter.setPen(self._rect_pen)
        painter.drawRect(self.rect())
        self._paint_decoration(painter)
        self._draw_violation_highlight(painter)
        self._draw_selection_highlight(painter)
        self._draw_rotation_handle(painter)

    def _paint_decoration(self, painter: QPainter):
        """Override per decorazioni specifiche (porta, swinger, mover…)."""
        pass


class EllipseGraphicsItem(StageItemMixin, QGraphicsEllipseItem):
    """Classe base per item con forma ellittica: bersagli carta/steel, no-shoot."""

    def __init__(self, wrapper: StageItemWrapper, scale: float,
                 color: str, pen_color: str = "#0f172a", pen_width: int = 2,
                 brush_alpha: int = 255, parent=None):
        QGraphicsEllipseItem.__init__(self, parent)
        self.stage_item_init(wrapper, scale)
        c = QColor(color)
        if brush_alpha < 255:
            c.setAlpha(brush_alpha)
        self._ellipse_brush = QBrush(c)
        self._ellipse_pen = QPen(QColor(pen_color), pen_width)
        self.update_from_model()

    def update_from_model(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        self.setRect(-w / 2, -h / 2, w, h)
        super().update_from_model()

    def paint(self, painter, option, widget=None):
        painter.setBrush(self._ellipse_brush)
        painter.setPen(self._ellipse_pen)
        painter.drawEllipse(self.rect())
        self._paint_decoration(painter)
        self._draw_violation_highlight(painter)
        self._draw_selection_highlight(painter)
        self._draw_rotation_handle(painter)

    def _paint_decoration(self, painter: QPainter):
        """Override per X di no-shoot, etc."""
        pass


# ─── Implementazioni concrete ────────────────────────────────────────────────

class WallGraphicsItem(RectGraphicsItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)


class TargetGraphicsItem(EllipseGraphicsItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)


class FaultLineGraphicsItem(StageItemMixin, QGraphicsItem):
    """Linea di fault: linea tratteggiata rossa con bounding rect custom."""

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        QGraphicsItem.__init__(self, parent)
        self.stage_item_init(wrapper, scale)
        self.update_from_model()

    def boundingRect(self):
        w = self.wrapper.item.width * self.scale
        pen_w = 8
        return QRectF(-w / 2 - pen_w, -pen_w, w + pen_w * 2, pen_w * 2)

    def paint(self, painter, option, widget=None):
        pen = QPen(QColor("#dc2626"), 3)
        pen.setDashPattern([6, 4])
        painter.setPen(pen)
        w = self.wrapper.item.width * self.scale
        painter.drawLine(-w / 2, 0, w / 2, 0)
        self._draw_violation_highlight(painter)
        self._draw_selection_highlight(painter)
        self._draw_rotation_handle(painter)

    def update_from_model(self):
        self.setPos(self.wrapper.item.x * self.scale, self.wrapper.item.y * self.scale)
        self.setRotation(self.wrapper.item.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            snapped = _snap_pos(value, self.scale)
            if self._would_collide_with_obstacles(snapped):
                return self.pos()
            if self._would_block_shooter_path(snapped):
                return self.pos()
            return snapped
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)


class NoShootGraphicsItem(EllipseGraphicsItem):
    """No-shoot: ellisse rossa semitrasparente con X."""

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#dc2626", pen_width=2, brush_alpha=120)

    def _paint_decoration(self, painter: QPainter):
        r = self.rect()
        pen = QPen(QColor("#7f1d1d"), 2)
        painter.setPen(pen)
        painter.drawLine(r.topLeft(), r.bottomRight())
        painter.drawLine(r.topRight(), r.bottomLeft())


class BarrierGraphicsItem(RectGraphicsItem):
    """Barriera: rettangolo giallo tratteggiato semitrasparente."""

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#f59e0b", pen_width=2, brush_alpha=80,
                         pen_style=Qt.PenStyle.DashLine)


class DoorGraphicsItem(RectGraphicsItem):
    """Porta: rettangolo con maniglia."""

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)

    def _paint_decoration(self, painter: QPainter):
        r = self.rect()
        pen = QPen(QColor("#0f172a"), 1)
        painter.setPen(pen)
        painter.drawLine(r.center().x(), r.top(), r.center().x(), r.bottom())
        handle = QPainterPath()
        hx = r.center().x() + r.width() * 0.15
        hy = r.center().y()
        handle.addEllipse(hx - 3, hy - 3, 6, 6)
        painter.fillPath(handle, QColor("#0f172a"))


class SwingerGraphicsItem(RectGraphicsItem):
    """Swinger: rettangolo viola con arco di oscillazione."""

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)

    def _paint_decoration(self, painter: QPainter):
        amp = self.wrapper.item.properties.get("amplitude", 45)
        pen = QPen(QColor("#a855f7"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = 40
        start_angle = -amp - self.rotation()
        span = amp * 2
        painter.drawArc(-r, -r, r * 2, r * 2, int(start_angle * 16), int(span * 16))


class DropTurnerGraphicsItem(RectGraphicsItem):
    """Drop Turner: rettangolo verde acqua con freccia caduta."""

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)

    def _paint_decoration(self, painter: QPainter):
        pen = QPen(QColor("#0f172a"), 2)
        painter.setPen(pen)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        painter.drawLine(cx, cy - 8, cx, cy + 8)
        painter.drawLine(cx - 4, cy + 4, cx, cy + 8)
        painter.drawLine(cx + 4, cy + 4, cx, cy + 8)


class MoverGraphicsItem(RectGraphicsItem):
    """Mover: rettangolo arancione con linea traiettoria."""

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)

    def _paint_decoration(self, painter: QPainter):
        dist = self.wrapper.item.properties.get("distance", 3.0) * self.scale
        pen = QPen(QColor("#f97316"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        angle = math.radians(self.rotation())
        dx = math.cos(angle) * dist / 2
        dy = math.sin(angle) * dist / 2
        painter.drawLine(-dx, -dy, dx, dy)


# ── Nuovi tipi IPSC (shape-based) ────────────────────────────────────────


class PopperGraphicsItem(EllipseGraphicsItem):
    """Popper: bersaglio metallico calibrato con zona calibrazione."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)

    def _paint_decoration(self, painter: QPainter):
        r = self.rect()
        pen = QPen(QColor("#dc2626"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cal_r = min(r.width(), r.height()) * 0.3
        painter.drawEllipse(r.center(), cal_r, cal_r)


class MetalPlateGraphicsItem(EllipseGraphicsItem):
    """Piatto metallico: cerchio semplice non calibrato."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)


class MiniTargetGraphicsItem(EllipseGraphicsItem):
    """Mini Target: bersaglio cartaceo ridotto (App. B3)."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)

    def _paint_decoration(self, painter: QPainter):
        r = self.rect()
        pen = QPen(QColor("#78350f"), 1, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        ir = min(r.width(), r.height()) * 0.4
        painter.drawEllipse(r.center(), ir, ir)


class MicroTargetGraphicsItem(EllipseGraphicsItem):
    """Micro Target: bersaglio cartaceo micro."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2)


class HardCoverGraphicsItem(RectGraphicsItem):
    """Hard Cover: copertura impenetrabile (Reg. 4.1.4.1)."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#0f172a", pen_width=2, brush_alpha=200)

    def _paint_decoration(self, painter: QPainter):
        r = self.rect()
        pen = QPen(QColor("#94a3b8"), 2)
        painter.setPen(pen)
        painter.drawLine(r.topLeft(), r.bottomRight())
        painter.drawLine(r.topRight(), r.bottomLeft())


class SoftCoverGraphicsItem(RectGraphicsItem):
    """Soft Cover: copertura visiva semitrasparente (Reg. 4.1.4.2)."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(wrapper, scale, wrapper.item.color,
                         pen_color="#475569", pen_width=1, brush_alpha=60,
                         pen_style=Qt.PenStyle.DashLine)


# ═══════════════════════════════════════════════════════════════════════════════
#  PixmapGraphicsItem — item basato su immagini IPSC (dal Regolamento PDF)
# ═══════════════════════════════════════════════════════════════════════════════

class PixmapGraphicsItem(StageItemMixin, QGraphicsPixmapItem):
    """Classe base per bersagli disegnati con immagini PNG estratte dal Regolamento.

    Usa TargetImageManager per caricare, tintare e scalare il pixmap
    in base alle dimensioni reali del bersaglio.

    Le sottoclassi possono sovrascrivere _paint_decoration() per
    aggiungere overlay (X no-shoot, arco swinger, ecc.).
    """

    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        QGraphicsPixmapItem.__init__(self, parent)
        self.stage_item_init(wrapper, scale)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.update_from_model()

    def update_from_model(self):
        it = self.wrapper.item
        w_px = int(it.width * self.scale)
        h_px = int(it.height * self.scale)

        if w_px > 0 and h_px > 0:
            pixmap = TargetImageManager.instance().get_pixmap(
                it.item_type, w_px, h_px
            )
            if pixmap is not None and not pixmap.isNull():
                self.setPixmap(pixmap)
                self.setOffset(-pixmap.width() / 2.0, -pixmap.height() / 2.0)
            else:
                self.setPixmap(QPixmap())
        else:
            self.setPixmap(QPixmap())

        super().update_from_model()

    def paint(self, painter, option, widget=None):
        # Disegna il pixmap (ereditato da QGraphicsPixmapItem)
        super().paint(painter, option, widget)
        # Overlay
        self._paint_decoration(painter)
        self._draw_violation_highlight(painter)
        self._draw_selection_highlight(painter)
        self._draw_rotation_handle(painter)

    def _paint_decoration(self, painter: QPainter):
        """Override per decorazioni specifiche (X, arco, freccia, linea)."""
        pass

    # ---- Override per supportare highlight su bounding corretto ----

    def _draw_selection_highlight(self, painter: QPainter):
        if not self.isSelected():
            return
        pen = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        br = self.boundingRect().adjusted(-4, -4, 4, 4)
        painter.drawRect(br)


# ─── Implementazioni pixmap per tipi bersaglio ──────────────────────────────


class PaperTargetPixmapItem(PixmapGraphicsItem):
    """Bersaglio cartaceo IPSC: silhouette marrone dal Regolamento."""
    pass


class MiniTargetPixmapItem(PixmapGraphicsItem):
    """Mini Target IPSC: silhouette ridotta marrone (App. B3)."""
    pass


class MicroTargetPixmapItem(PixmapGraphicsItem):
    """Micro Target IPSC: silhouette micro marrone."""
    pass


class SteelTargetPixmapItem(PixmapGraphicsItem):
    """Bersaglio metallico: popper grigio dal Regolamento."""
    pass


class PopperPixmapItem(PixmapGraphicsItem):
    """Popper: bersaglio metallico calibrato grigio (App. C2)."""
    pass


class MetalPlatePixmapItem(PixmapGraphicsItem):
    """Piatto metallico: diagramma non calibrato (App. C3)."""
    pass


class NoShootPixmapItem(PixmapGraphicsItem):
    """No-Shoot: silhouette gialla IPSC con X rosso (Reg. 4.1.3)."""

    def _paint_decoration(self, painter: QPainter):
        r = self.boundingRect()
        margin = r.width() * 0.15
        x1 = r.left() + margin
        y1 = r.top() + margin
        x2 = r.right() - margin
        y2 = r.bottom() - margin
        pen = QPen(QColor("#dc2626"), 2)
        painter.setPen(pen)
        painter.drawLine(x1, y1, x2, y2)
        painter.drawLine(x2, y1, x1, y2)


class SwingerPixmapItem(PixmapGraphicsItem):
    """Swinger: silhouette mobile con arco di oscillazione."""

    def _paint_decoration(self, painter: QPainter):
        amp = self.wrapper.item.properties.get("amplitude", 45)
        pen = QPen(QColor("#a855f7"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = 40
        start_angle = -amp - self.rotation()
        span = amp * 2
        painter.drawArc(-r, -r, r * 2, r * 2, int(start_angle * 16), int(span * 16))


class DropTurnerPixmapItem(PixmapGraphicsItem):
    """Drop Turner: silhouette mobile con freccia caduta."""

    def _paint_decoration(self, painter: QPainter):
        pen = QPen(QColor("#0f172a"), 2)
        painter.setPen(pen)
        br = self.boundingRect()
        cx, cy = br.center().x(), br.center().y()
        painter.drawLine(cx, cy - 8, cx, cy + 8)
        painter.drawLine(cx - 4, cy + 4, cx, cy + 8)
        painter.drawLine(cx + 4, cy + 4, cx, cy + 8)


class MoverPixmapItem(PixmapGraphicsItem):
    """Mover: silhouette mobile con linea traiettoria."""

    def _paint_decoration(self, painter: QPainter):
        dist = self.wrapper.item.properties.get("distance", 3.0) * self.scale
        pen = QPen(QColor("#f97316"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        angle = math.radians(self.rotation())
        dx = math.cos(angle) * dist / 2
        dy = math.sin(angle) * dist / 2
        painter.drawLine(-dx, -dy, dx, dy)


# ═══════════════════════════════════════════════════════════════════════════════
#  Undo Commands
# ═══════════════════════════════════════════════════════════════════════════════

class AddItemCommand(QUndoCommand):
    def __init__(self, scene: "StageScene", item: StageItem,
                 description: str = "Aggiungi oggetto"):
        super().__init__(description)
        self.scene = scene
        self.item = item
        self._graphics_item: Optional[QGraphicsItem] = None

    def redo(self):
        self._graphics_item = self.scene._do_add_item(self.item)

    def undo(self):
        if self._graphics_item:
            self.scene._do_remove_item(self.item.id)
            self._graphics_item = None


class RemoveItemCommand(QUndoCommand):
    def __init__(self, scene: "StageScene", item_id: int,
                 description: str = "Rimuovi oggetto"):
        super().__init__(description)
        self.scene = scene
        self.item_id = item_id
        self._backup: Optional[StageItem] = None
        self._backup_index = -1

    def redo(self):
        self._backup = self.scene.stage.get_item(self.item_id)
        if self._backup:
            self._backup_index = self.scene.stage.items.index(self._backup)
            self.scene._do_remove_item(self.item_id)

    def undo(self):
        if self._backup:
            self.scene.stage.items.insert(self._backup_index, self._backup)
            self.scene._do_add_graphics_item(self._backup)


# ═══════════════════════════════════════════════════════════════════════════════
#  StageScene
# ═══════════════════════════════════════════════════════════════════════════════

class StageScene(QGraphicsScene):
    """Scena editor 2D con griglia, undo/redo, e factory di item grafici."""
    itemAdded = Signal(StageItemWrapper)
    itemRemoved = Signal(int)
    itemUpdated = Signal(int)
    selectionChangedWrapper = Signal(object)
    violationsChanged = Signal()  # emesso quando cambiano le violazioni

    def __init__(self, stage: Stage, parent=None):
        super().__init__(parent)
        self.stage = stage
        self.scale = 40.0
        self._items: dict[int, QGraphicsItem] = {}
        self._violation_ids: set[int] = set()
        self.undo_stack = QUndoStack(self)
        self._setup_grid()
        self._sync_from_model()
        self.selectionChanged.connect(self._on_selection_changed)

    def _setup_grid(self):
        self.grid = GridItem(self.stage.width, self.stage.depth, self.scale)
        self.addItem(self.grid)
        self.setSceneRect(
            0, 0,
            self.stage.width * self.scale,
            self.stage.depth * self.scale,
        )

    def _sync_from_model(self):
        for it in self.stage.items:
            self._do_add_graphics_item(it)

    # ── Factory ──────────────────────────────────────────────────────────────

    _GRAPHICS_ITEM_CLASSES: dict[ItemType, tuple[type, str | None]] = {
        ItemType.WALL:          (WallGraphicsItem, None),
        ItemType.PAPER_TARGET:  (PaperTargetPixmapItem, None),
        ItemType.STEEL_TARGET:  (SteelTargetPixmapItem, None),
        ItemType.POPPER:        (PopperPixmapItem, None),
        ItemType.METAL_PLATE:   (MetalPlatePixmapItem, None),
        ItemType.MINI_TARGET:   (MiniTargetPixmapItem, None),
        ItemType.MICRO_TARGET:  (MicroTargetPixmapItem, None),
        ItemType.FAULT_LINE:    (FaultLineGraphicsItem, None),
        ItemType.NO_SHOOT:      (NoShootPixmapItem, None),
        ItemType.BARRIER:       (BarrierGraphicsItem, None),
        ItemType.DOOR:          (DoorGraphicsItem, None),
        ItemType.HARD_COVER:    (HardCoverGraphicsItem, None),
        ItemType.SOFT_COVER:    (SoftCoverGraphicsItem, None),
        ItemType.SWINGER:       (SwingerPixmapItem, None),
        ItemType.DROP_TURNER:   (DropTurnerPixmapItem, None),
        ItemType.MOVER:         (MoverPixmapItem, None),
    }

    def _make_graphics_item(self, item: StageItem) -> QGraphicsItem:
        cls, _ = self._GRAPHICS_ITEM_CLASSES.get(
            item.item_type,
            (WallGraphicsItem, None),
        )
        wrapper = StageItemWrapper(item)
        wrapper.changed.connect(lambda: self.itemUpdated.emit(item.id))
        return cls(wrapper, self.scale)

    # ── Manipolazione item ───────────────────────────────────────────────────

    def _do_add_graphics_item(self, item: StageItem):
        g = self._make_graphics_item(item)
        self.addItem(g)
        self._items[item.id] = g
        self.itemAdded.emit(g.wrapper)

    def _do_add_item(self, item: StageItem) -> QGraphicsItem:
        self.stage.add_item(item)
        self._do_add_graphics_item(item)
        return self._items[item.id]

    def _do_remove_item(self, item_id: int):
        g = self._items.pop(item_id, None)
        if g:
            self.removeItem(g)
        self.stage.remove_item(item_id)
        self.itemRemoved.emit(item_id)

    def _on_selection_changed(self):
        sel = self.selectedItems()
        if len(sel) == 1 and hasattr(sel[0], 'wrapper'):
            self.selectionChangedWrapper.emit(sel[0].wrapper)
        else:
            self.selectionChangedWrapper.emit(None)

    # ── Public API con undo ──────────────────────────────────────────────────

    # ── Evidenziazione violazioni ───────────────────────────────────────────

    def set_violations(self, item_ids: set[int]):
        """Imposta gli ID degli item con violazioni IPSC e forza il repaint."""
        if self._violation_ids == item_ids:
            return
        self._violation_ids = set(item_ids)
        self.violationsChanged.emit()
        for g in self._items.values():
            if hasattr(g, 'update'):
                g.update()

    def has_violation(self, item_id: int) -> bool:
        return item_id in self._violation_ids

    def push_add_item(self, item: StageItem):
        self.undo_stack.push(AddItemCommand(self, item))

    def push_remove_item(self, item_id: int):
        self.undo_stack.push(RemoveItemCommand(self, item_id))

    def push_remove_selected(self):
        for g in list(self.selectedItems()):
            for gid, gi in list(self._items.items()):
                if gi is g:
                    self.push_remove_item(gid)
                    break

    # ── Factory helpers ──────────────────────────────────────────────────────

    def add_wall(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        item = StageItem(0, ItemType.WALL, x, y, w, h, 0, "#475569", "Muro")
        self.push_add_item(item)

    def add_target(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                   item_type: ItemType = ItemType.PAPER_TARGET):
        # IPSC: carta = marrone, metallo = bianco/grigio (Regola 4.1.2)
        color = "#8B4513" if item_type == ItemType.PAPER_TARGET else "#d1d5db"
        label = "Paper" if item_type == ItemType.PAPER_TARGET else "Steel"
        item = StageItem(0, item_type, x, y, w, h, 0, color, label)
        self.push_add_item(item)

    def add_fault_line(self, x: float, y: float, length: float = 3.0):
        item = StageItem(0, ItemType.FAULT_LINE, x, y, length, 0.0, 0, "#dc2626", "Fault Line")
        self.push_add_item(item)

    def add_no_shoot(self, x: float, y: float, w: float = 0.45, h: float = 0.45):
        # IPSC: colore uniforme DIVERSO dai bersagli punti (Regola 4.1.3)
        item = StageItem(0, ItemType.NO_SHOOT, x, y, w, h, 0, "#eab308", "No-Shoot")
        self.push_add_item(item)

    def add_barrier(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        item = StageItem(0, ItemType.BARRIER, x, y, w, h, 0, "#fbbf24", "Barriera")
        self.push_add_item(item)

    def add_door(self, x: float, y: float, w: float = 1.0, h: float = 0.1):
        item = StageItem(0, ItemType.DOOR, x, y, w, h, 0, "#92400e", "Porta")
        self.push_add_item(item)

    def add_swinger(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                    amplitude: float = 45.0, speed: float = 1.0):
        # IPSC: bersaglio cartaceo mobile → marrone
        item = StageItem(0, ItemType.SWINGER, x, y, w, h, 0, "#A0522D", "Swinger",
                         properties={"amplitude": amplitude, "speed": speed, "axis": "y"})
        self.push_add_item(item)

    def add_drop_turner(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                        fall_time: float = 0.5):
        # IPSC: bersaglio cartaceo mobile → marrone
        item = StageItem(0, ItemType.DROP_TURNER, x, y, w, h, 0, "#8B6914", "Drop Turner",
                         properties={"trigger": "hit", "fall_time": fall_time})
        self.push_add_item(item)

    def add_mover(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                  distance: float = 3.0, speed: float = 1.5):
        # IPSC: bersaglio cartaceo mobile → marrone
        item = StageItem(0, ItemType.MOVER, x, y, w, h, 0, "#CD853F", "Mover",
                         properties={"distance": distance, "speed": speed, "direction": 0})
        self.push_add_item(item)

    # ── Nuovi tipi IPSC ──────────────────────────────────────────────────────

    def add_popper(self, x: float, y: float, diameter: float = 0.30):
        """Aggiunge un Popper (bersaglio metallico calibrato, App. C1-C2)."""
        item = StageItem(0, ItemType.POPPER, x, y, diameter, diameter, 0,
                         "#d1d5db", "Popper",
                         properties={"calibrated": True, "calibration_pf": 125})
        self.push_add_item(item)

    def add_metal_plate(self, x: float, y: float, diameter: float = 0.20):
        """Aggiunge un piatto metallico (non calibrato, App. C3)."""
        item = StageItem(0, ItemType.METAL_PLATE, x, y, diameter, diameter, 0,
                         "#d1d5db", "Piatto",
                         properties={"calibrated": False, "diameter": diameter})
        self.push_add_item(item)

    def add_mini_target(self, x: float, y: float):
        """Aggiunge un Mini Target IPSC (bersaglio cartaceo ridotto, App. B3)."""
        item = StageItem(0, ItemType.MINI_TARGET, x, y, 0.30, 0.30, 0,
                         "#8B4513", "Mini Target",
                         properties={"scale": 0.75})
        self.push_add_item(item)

    def add_micro_target(self, x: float, y: float):
        """Aggiunge un Micro Target IPSC."""
        item = StageItem(0, ItemType.MICRO_TARGET, x, y, 0.20, 0.20, 0,
                         "#8B4513", "Micro Target",
                         properties={"scale": 0.50})
        self.push_add_item(item)

    def add_hard_cover(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        """Aggiunge Hard Cover (copertura impenetrabile, Reg. 4.1.4.1)."""
        item = StageItem(0, ItemType.HARD_COVER, x, y, w, h, 0,
                         "#1e293b", "Hard Cover",
                         properties={"impenetrable": True, "height": 2.0})
        self.push_add_item(item)

    def add_soft_cover(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        """Aggiunge Soft Cover (copertura visiva, Reg. 4.1.4.2)."""
        item = StageItem(0, ItemType.SOFT_COVER, x, y, w, h, 0,
                         "#94a3b8", "Soft Cover",
                         properties={"impenetrable": False, "height": 2.0})
        self.push_add_item(item)

    def update_item_from_properties(self, item_id: int, **kwargs):
        it = self.stage.get_item(item_id)
        if not it:
            return
        changed = False
        for k, v in kwargs.items():
            if hasattr(it, k) and getattr(it, k) != v:
                setattr(it, k, v)
                changed = True
        if changed:
            g = self._items.get(item_id)
            if g and hasattr(g, 'update_from_model'):
                g.update_from_model()
            self.itemUpdated.emit(item_id)
