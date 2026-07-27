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

from ui.editor.target_images import TargetSvgManager
from ui.editor.path_editor import PathPolylineItem


# ═══════════════════════════════════════════════════════════════════════════════
#  Utility: ricostruzione poligono area di tiro da fault-line
# ═══════════════════════════════════════════════════════════════════════════════

def _build_polygon_from_fault_lines(items: list[StageItem]) -> list[tuple[float, float]] | None:
    """Ricostruisce il poligono dell'area di tiro dalle fault-line perimetrali.

    Le fault-line con `properties["perimeter"] = True` formano una catena
    chiusa. L'algoritmo ricostruisce gli endpoint di ogni segmento e li
    concatena in ordine per formare il poligono.

    Returns:
        Lista di vertici (x, y) o None se non ci sono abbastanza fault-line.
    """
    fault_lines = [
        it for it in items
        if it.item_type == ItemType.FAULT_LINE and it.properties.get("perimeter")
    ]
    if len(fault_lines) < 3:
        return None

    # Calcola gli endpoint di ogni segmento
    segments: list[tuple[tuple[float, float], tuple[float, float], int]] = []
    for fl in fault_lines:
        rad = math.radians(fl.rotation)
        half = fl.width / 2
        dx = math.cos(rad) * half
        dy = math.sin(rad) * half
        p1 = (round(fl.x - dx, 4), round(fl.y - dy, 4))
        p2 = (round(fl.x + dx, 4), round(fl.y + dy, 4))
        segments.append((p1, p2, fl.id))

    # Costruisci la catena: per ogni segmento, trova il successivo
    # il cui primo endpoint è vicino al secondo endpoint del corrente
    eps = 0.15  # tolleranza 15 cm
    chain: list[tuple[float, float]] = []
    used: set[int] = set()

    # Parti dal primo segmento
    p1, p2, sid = segments[0]
    chain.append(p1)
    chain.append(p2)
    used.add(sid)

    # Segui la catena
    while len(used) < len(segments):
        last = chain[-1]
        found = False
        for s1, s2, sid in segments:
            if sid in used:
                continue
            d1 = math.hypot(s1[0] - last[0], s1[1] - last[1])
            d2 = math.hypot(s2[0] - last[0], s2[1] - last[1])
            if d1 < eps:
                chain.append(s2)
                used.add(sid)
                found = True
                break
            elif d2 < eps:
                chain.append(s1)
                used.add(sid)
                found = True
                break
        if not found:
            break  # catena interrotta

    # Chiudi il poligono (rimuovi l'ultimo punto se coincide col primo)
    if len(chain) >= 3:
        d_close = math.hypot(chain[0][0] - chain[-1][0], chain[0][1] - chain[-1][1])
        if d_close < eps:
            chain.pop()

    return chain if len(chain) >= 3 else None


# ═══════════════════════════════════════════════════════════════════════════════
#  ShootingPositionMarker — marker per posizione di tiro
# ═══════════════════════════════════════════════════════════════════════════════

class ShootingPositionMarker(QGraphicsItem):
    """Marker circolare per una shooting position.

    Usato durante la Fase 2 per visualizzare le posizioni di tiro
    impostate dall'utente.
    - Start: cerchio verde con "S"
    - Intermedie: cerchio blu con numero

    Supporta:
    - Drag per spostamento (snap a griglia)
    - Callback on_changed per sincronizzare la lista
    - Callback on_deleted per rimuovere dalla lista
    """

    def __init__(self, x: float, y: float, scale: float,
                 label: str = "S", is_start: bool = True,
                 index: int = 1, parent=None,
                 on_changed: callable = None,
                 on_deleted: callable = None):
        super().__init__(parent)
        self._x = x
        self._y = y
        self._scale = scale
        self._label = label
        self._is_start = is_start
        self._index = index
        self._on_changed = on_changed
        self._on_deleted = on_deleted
        self.setPos(x * scale, y * scale)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def boundingRect(self):
        s = 22
        return QRectF(-s / 2, -s / 2, s, s)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#22c55e") if self._is_start else QColor("#3b82f6")
        painter.setBrush(QBrush(color))
        if self.isSelected():
            painter.setPen(QPen(QColor("#ffffff"), 3))
        else:
            painter.setPen(QPen(QColor("#0f172a"), 2))
        painter.drawEllipse(-9, -9, 18, 18)
        # Etichetta
        painter.setPen(QPen(QColor("white"), 1))
        f = painter.font()
        f.setPointSize(9)
        f.setBold(True)
        painter.setFont(f)
        s = 18
        br = QRectF(-s / 2, -s / 2, s, s)
        painter.drawText(br, Qt.AlignmentFlag.AlignCenter, self._label)
        painter.restore()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            snapped = _snap_pos(value, self._scale)
            return super().itemChange(change, snapped)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._x = self.pos().x() / self._scale
            self._y = self.pos().y() / self._scale
            if self._on_changed:
                self._on_changed(self)
        return super().itemChange(change, value)

    @property
    def pos_m(self) -> tuple[float, float]:
        return (self._x, self._y)

    @property
    def is_start(self) -> bool:
        return self._is_start

    @property
    def label_text(self) -> str:
        return self._label


# ═══════════════════════════════════════════════════════════════════════════════
#  EngagementAreaItem — area di ingaggio 90° per posizione di tiro
# ═══════════════════════════════════════════════════════════════════════════════

class EngagementAreaItem(QGraphicsItem):
    """Mostra l'area di ingaggio di 180° da una posizione di tiro.

    Visualizza un cono di 180° (90° per lato, angoli sicurezza IPSC)
    dalla posizione di tiro verso il fondo dello stage. Le barriere/muri
    che intersecano il cono generano zone d'ombra (aree non visibili).
    """

    def __init__(self, pos_x: float, pos_y: float, scale: float,
                 angle: float = 90.0, range_m: float = 30.0,
                 obstacles: list = None, parent=None):
        super().__init__(parent)
        self._px = pos_x
        self._py = pos_y
        self._scale = scale
        self._angle = angle  # direzione di ingaggio in gradi (0=destra, 90=su/y+)  
        self._range = range_m
        self._obstacles = obstacles or []
        self.setZValue(5)  # sopra shooting area, sotto marker
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def set_obstacles(self, obstacles: list):
        """Aggiorna la lista di ostacoli (x, y, w, h, rot) per il calcolo ombre."""
        self._obstacles = obstacles
        self.update()

    def set_position(self, x: float, y: float):
        self._px = x
        self._py = y
        self.update()

    def boundingRect(self):
        r = self._range * self._scale
        cx = self._px * self._scale
        cy = self._py * self._scale
        return QRectF(cx - r, cy - r, r * 2, r * 2)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        scale = self._scale
        cx = self._px * scale
        cy = self._py * scale
        r = self._range * scale

        # Direzione di ingaggio: verso Y+ (down-range = backstop)
        # 0° = destra (+X), 90° = giù (+Y = backstop), 180° = sinistra
        angle_rad = math.radians(self._angle)

        # Cono di 180°: 90° per lato (angoli di sicurezza IPSC)
        half_cone = math.radians(90)

        # Vertici del cono
        start_a = angle_rad - half_cone
        end_a = angle_rad + half_cone

        # Costruisci il path del cono
        path = QPainterPath()
        path.moveTo(cx, cy)

        steps = 40
        for i in range(steps + 1):
            t = start_a + (end_a - start_a) * i / steps
            px = cx + r * math.cos(t)
            py = cy + r * math.sin(t)
            path.lineTo(px, py)
        path.closeSubpath()

        # Disegna il cono pieno (area visibile)
        visible_brush = QBrush(QColor(0, 200, 80, 30))  # verde trasp
        visible_pen = QPen(QColor(0, 180, 60, 80), 1.5, Qt.PenStyle.DashLine)
        painter.setBrush(visible_brush)
        painter.setPen(visible_pen)
        painter.drawPath(path)

        # Linee dei bordi del cono
        edge_pen = QPen(QColor(0, 180, 60, 120), 2)
        painter.setPen(edge_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(cx, cy, cx + r * math.cos(start_a), cy + r * math.sin(start_a))
        painter.drawLine(cx, cy, cx + r * math.cos(end_a), cy + r * math.sin(end_a))

        # ── Evidenzia ostacoli che bloccano la visuale ──
        # Disegna ogni muro/barriera/hard-cover nel cono con un
        # riempimento rosso per indicare l'area bloccata.
        # Per ogni ostacolo viene anche proiettata un'ombra radiale
        # dalla posizione di tiro fino al bordo del cono.
        block_brush = QBrush(QColor(180, 50, 50, 45))
        block_pen = QPen(QColor(200, 40, 40, 120), 2)
        obs_fill = QBrush(QColor(200, 60, 60, 90))
        obs_pen = QPen(QColor(220, 30, 30, 200), 3)

        for obs in self._obstacles:
            ox, oy, ow, oh, orot = obs
            ocx = ox * scale
            ocy = oy * scale

            dx = ocx - cx
            dy = ocy - cy
            dist = math.hypot(dx, dy)
            if dist < 1:
                continue

            obs_angle = math.atan2(dy, dx)
            if not (start_a <= obs_angle <= end_a):
                continue

            # OBB con rotazione
            rot_rad = math.radians(orot)
            hw = ow * scale / 2
            hh = oh * scale / 2
            cos_r, sin_r = math.cos(rot_rad), math.sin(rot_rad)
            corners = []
            for lx, ly in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
                corners.append((ocx + lx * cos_r - ly * sin_r,
                                ocy + lx * sin_r + ly * cos_r))

            # Proiezioni radiali dei vertici al bordo del cono
            proj = []
            for vx, vy in corners:
                vdx, vdy = vx - cx, vy - cy
                vd = math.hypot(vdx, vdy)
                ratio = (r + 10) / max(vd, 1)
                proj.append((cx + vdx * ratio, cy + vdy * ratio))

            # Ombra: proietta i 2 lati che "guardano" verso la posizione
            # (i lati con normale che punta verso cx,cy)
            shadow = QPainterPath()
            for i in range(4):
                j = (i + 1) % 4
                # Normale del lato (puntante verso l'esterno dell'ostacolo)
                ex = corners[j][0] - corners[i][0]
                ey = corners[j][1] - corners[i][1]
                # Vettore dal centro ostacolo alla posizione di tiro
                to_cam = (cx - ocx, cy - ocy)
                # Prodotto scalare normale·to_cam: se >0 il lato guarda la camera
                nx, ny = ey, -ex  # normale ruotata 90°
                if nx * to_cam[0] + ny * to_cam[1] > 0:
                    p = QPainterPath()
                    p.moveTo(corners[i][0], corners[i][1])
                    p.lineTo(corners[j][0], corners[j][1])
                    p.lineTo(proj[j][0], proj[j][1])
                    p.lineTo(proj[i][0], proj[i][1])
                    p.closeSubpath()
                    shadow.addPath(p)

            if not shadow.isEmpty():
                painter.setBrush(block_brush)
                painter.setPen(block_pen)
                painter.drawPath(shadow)

            # Corpo dell'ostacolo in rosso
            obs_path = QPainterPath()
            obs_path.moveTo(corners[0][0], corners[0][1])
            for k in range(1, 4):
                obs_path.lineTo(corners[k][0], corners[k][1])
            obs_path.closeSubpath()
            painter.setBrush(obs_fill)
            painter.setPen(obs_pen)
            painter.drawPath(obs_path)

        painter.restore()


# ═══════════════════════════════════════════════════════════════════════════════
#  ObstacleMarker — marker per ostacoli posizionati dall'utente
# ═══════════════════════════════════════════════════════════════════════════════

class ObstacleMarker(QGraphicsItem):
    """Marker per ostacoli (muri/barriere) posizionati dall'utente.

    Supporta:
    - Drag per spostamento (snap a griglia)
    - Rotazione tramite handle circolare
    - Callback on_changed per sincronizzare la lista
    """

    def __init__(self, x: float, y: float, scale: float,
                 width: float = 3.0, rotation: float = 0.0,
                 is_wall: bool = True, label: str = "",
                 on_changed: callable = None,
                 on_deleted: callable = None, parent=None):
        super().__init__(parent)
        self._x = x
        self._y = y
        self._scale = scale
        self._width = width
        self._rotation = rotation
        self._is_wall = is_wall
        self._label = label
        self._on_changed = on_changed
        self._on_deleted = on_deleted
        self._is_rotating = False
        self._start_scene_angle = 0.0
        self._start_rotation = 0.0

        self.setPos(x * scale, y * scale)
        self.setRotation(rotation)
        self.setZValue(9)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        w = max(self._width * self._scale, 24)
        margin = 16
        # L'area include l'handle di rotazione che sta sopra (y negativo)
        top = -42  # spazio per handle rotazione
        bottom = 28
        return QRectF(-w / 2 - margin, top, w + margin * 2, bottom - top)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = max(self._width * self._scale, 24)
        h = 10

        if self._is_wall:
            color = QColor("#475569")
            pen_color = QColor("#0f172a")
        else:
            color = QColor("#fbbf24")
            color.setAlpha(180)
            pen_color = QColor("#f59e0b")

        painter.setBrush(QBrush(color))
        if self.isSelected():
            painter.setPen(QPen(QColor("#ffffff"), 3))
        else:
            if self._is_wall:
                painter.setPen(QPen(pen_color, 2))
            else:
                painter.setPen(QPen(pen_color, 2, Qt.PenStyle.DashLine))

        painter.drawRoundedRect(-w / 2, -h / 2, w, h, 3, 3)

        # Etichetta
        painter.setPen(QPen(QColor("white"), 1))
        f = painter.font()
        f.setPointSize(8)
        f.setBold(True)
        painter.setFont(f)
        label = self._label or ("M" if self._is_wall else "B")
        br = QRectF(-w / 2, -h / 2, w, h)
        painter.drawText(br, Qt.AlignmentFlag.AlignCenter, label)

        # Handle di rotazione (solo se selezionato)
        if self.isSelected():
            painter.setPen(QPen(QColor("#2563eb"), 2))
            painter.setBrush(QBrush(QColor("#2563eb")))
            handle_rect = self._rotation_handle_rect()
            painter.drawLine(0, -h / 2, handle_rect.center().x(), handle_rect.center().y())
            painter.drawEllipse(handle_rect)
            painter.setPen(QPen(QColor("white"), 1))
            painter.drawText(handle_rect, Qt.AlignmentFlag.AlignCenter, "↻")

        painter.restore()

    def _rotation_handle_rect(self) -> QRectF:
        """Rettangolo dell'handle di rotazione sopra il marker."""
        s = 14
        return QRectF(-s / 2, -22 - s, s, s)

    # ── Intercettazione eventi per rotazione ──

    def hoverMoveEvent(self, event):
        if self.isSelected() and self._rotation_handle_rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self._rotation_handle_rect().contains(event.pos()):
            self._is_rotating = True
            origin = self.scenePos()
            mouse_scene = self.mapToScene(event.pos())
            self._start_scene_angle = math.atan2(
                mouse_scene.y() - origin.y(), mouse_scene.x() - origin.x())
            self._start_rotation = self.rotation()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_rotating:
            origin = self.scenePos()
            mouse_scene = self.mapToScene(event.pos())
            current_angle = math.atan2(
                mouse_scene.y() - origin.y(), mouse_scene.x() - origin.x())
            delta = math.degrees(current_angle - self._start_scene_angle)
            new_rotation = (self._start_rotation + delta) % 360
            self.setRotation(new_rotation)
            self._rotation = new_rotation
            self._notify_changed()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_rotating:
            self._is_rotating = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Snap alla griglia durante il drag
            snapped = _snap_pos(value, self._scale)
            return snapped
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._x = self.pos().x() / self._scale
            self._y = self.pos().y() / self._scale
            self._notify_changed()
        if change == QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged:
            self._rotation = self.rotation()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()  # ridisegna handle
        return super().itemChange(change, value)

    def _notify_changed(self):
        """Chiama il callback se registrato."""
        if self._on_changed:
            self._on_changed(self)

    @property
    def pos_m(self) -> tuple[float, float]:
        return (self._x, self._y)

    @property
    def width_m(self) -> float:
        return self._width

    @property
    def rotation_deg(self) -> float:
        return self._rotation


# ═══════════════════════════════════════════════════════════════════════════════
#  ShootingAreaItem — evidenziazione area di tiro
# ═══════════════════════════════════════════════════════════════════════════════

class ShootingAreaItem(QGraphicsItem):
    """Evidenzia l'area di tiro (delimitata dalle fault-line) in verde."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._polygon: list[tuple[float, float]] = []
        self._scale: float = 40.0
        self.setZValue(-1)  # dietro la griglia ma sopra lo sfondo
        self.setAcceptHoverEvents(False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def set_polygon(self, poly: list[tuple[float, float]], scale: float):
        """Imposta il poligono dell'area di tiro."""
        self._polygon = poly
        self._scale = scale
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        if not self._polygon:
            return QRectF()
        xs = [p[0] * self._scale for p in self._polygon]
        ys = [p[1] * self._scale for p in self._polygon]
        return QRectF(min(xs) - 2, min(ys) - 2,
                       max(xs) - min(xs) + 4, max(ys) - min(ys) + 4)

    def paint(self, painter: QPainter, option, widget=None):
        if len(self._polygon) < 3:
            return
        painter.save()
        # Riempimento verde semitrasparente
        fill_color = QColor("#22c55e")
        fill_color.setAlpha(40)
        painter.setBrush(QBrush(fill_color))
        # Bordo verde
        pen = QPen(QColor("#16a34a"))
        pen.setWidthF(2.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)

        path = QPainterPath()
        first = self._polygon[0]
        path.moveTo(first[0] * self._scale, first[1] * self._scale)
        for p in self._polygon[1:]:
            path.lineTo(p[0] * self._scale, p[1] * self._scale)
        path.closeSubpath()
        painter.drawPath(path)
        painter.restore()


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
        painter.setPen(QPen(QColor("#64748b"), 1))
        painter.drawText(4, 14, "UP-RANGE (ingresso tiratore)")
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
        """Disegna il bordo di selezione con angoli."""
        if not self.isSelected():
            return
        br = self.boundingRect().adjusted(-4, -4, 4, 4)
        # Bordo principale
        pen = QPen(QColor("#3b82f6"), 2.5, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if isinstance(self, QGraphicsEllipseItem):
            painter.drawEllipse(br)
        elif isinstance(self, QGraphicsRectItem):
            painter.drawRect(br)
        else:
            painter.drawRoundedRect(br, 4, 4)
        # Angoli di selezione (solo per item rettangolari)
        if isinstance(self, QGraphicsRectItem) and not isinstance(self, FaultLineGraphicsItem):
            pen.setWidth(1)
            pen.setColor(QColor("#ffffff"))
            painter.setPen(pen)
            brush = QBrush(QColor("#3b82f6"))
            painter.setBrush(brush)
            s = 5.0
            for corner in [
                br.topLeft(), br.topRight(),
                br.bottomLeft(), br.bottomRight(),
            ]:
                painter.drawRect(QRectF(corner.x() - s / 2, corner.y() - s / 2, s, s))

    _resize_handle_size = 8.0
    _resize_handle_color = QColor("#3b82f6")

    def _resize_handle_rects(self) -> list[QRectF]:
        """Restituisce i rettangoli delle maniglie di resize."""
        if not self.isSelected():
            return []
        br = self.boundingRect()
        s = self._resize_handle_size
        half = s / 2
        return [
            QRectF(br.left() - half, br.top() - half, s, s),       # TL
            QRectF(br.center().x() - half, br.top() - half, s, s), # TC
            QRectF(br.right() - half, br.top() - half, s, s),      # TR
            QRectF(br.left() - half, br.center().y() - half, s, s),# LC
            QRectF(br.right() - half, br.center().y() - half, s, s),# RC
            QRectF(br.left() - half, br.bottom() - half, s, s),    # BL
            QRectF(br.center().x() - half, br.bottom() - half, s, s),# BC
            QRectF(br.right() - half, br.bottom() - half, s, s),   # BR
        ]

    def _draw_resize_handles(self, painter: QPainter):
        """Disegna le maniglie di ridimensionamento sugli angoli."""
        if not self.isSelected():
            return
        if isinstance(self, (FaultLineGraphicsItem, QGraphicsPixmapItem)):
            return  # niente resize per fault line e pixmap
        painter.save()
        pen = QPen(QColor("#ffffff"), 1.5)
        painter.setPen(pen)
        painter.setBrush(QBrush(self._resize_handle_color))
        for rect in self._resize_handle_rects():
            painter.drawRect(rect)
        painter.restore()

    def _handle_press_on_resize(self, pos: QPointF) -> int | None:
        """Restituisce l'indice della maniglia premuta, o None."""
        if not self.isSelected():
            return None
        for idx, rect in enumerate(self._resize_handle_rects()):
            if rect.contains(pos):
                return idx
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Item grafici concreti (ciascuno eredita StageItemMixin + base Qt)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Helper: bounding rect esteso per includere handle rotazione ──

def _with_rotation_handle(br: QRectF) -> QRectF:
    """Estende un QRectF verso l'alto per includere l'handle di rotazione."""
    top = br.top() - 24  # spazio per handle (12px) + margine
    return QRectF(br.left(), top, br.width(), br.bottom() - top)


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

    def boundingRect(self) -> QRectF:
        return _with_rotation_handle(super().boundingRect())

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
        self._draw_resize_handles(painter)
        self._draw_rotation_handle(painter)

    def _paint_decoration(self, painter: QPainter):
        """Override per decorazioni specifiche (porta, swinger, mover…)."""
        pass


class EllipseGraphicsItem(StageItemMixin, QGraphicsEllipseItem):
    """Classe base per item con forma ellittica: bersagli carta/steel, no-shoot."""

    def boundingRect(self) -> QRectF:
        return _with_rotation_handle(super().boundingRect())

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
        self._draw_resize_handles(painter)
        self._draw_rotation_handle(painter)

    def _paint_decoration(self, painter: QPainter):
        """Override per X di no-shoot, etc."""
        pass


# ─── Implementazioni concrete ────────────────────────────────────────────────

class WallGraphicsItem(RectGraphicsItem):
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
        return _with_rotation_handle(QRectF(-w / 2 - pen_w, -pen_w, w + pen_w * 2, pen_w * 2))

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


# ── Nuovi tipi IPSC (ostacoli) ────────────────────────────────────────


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
#  SvgTargetGraphicsItem — bersaglio vettoriale unificato (SVG)
# ═══════════════════════════════════════════════════════════════════════════════

class SvgTargetGraphicsItem(StageItemMixin, QGraphicsItem):
    """Bersaglio renderizzato da SVG vettoriale con tinta colore.

    Sostituisce tutte le precedenti classi per bersagli
    (PixmapGraphicsItem, EllipseGraphicsItem, TargetGraphicsItem, ecc.).

    Il SVG viene rasterizzato via QSvgRenderer alla risoluzione
    corrente e tintato con il colore configurato per il tipo.
    Le decorazioni (X no-shoot, arco swinger, ecc.) sono
    disegnate via QPainter in _paint_decoration().
    """

    # Bersagli che richiedono decorazioni speciali
    _DECORATED_TYPES: set[ItemType] = {
        ItemType.NO_SHOOT,
        ItemType.SWINGER,
        ItemType.DROP_TURNER,
        ItemType.MOVER,
    }

    def __init__(self, wrapper: StageItemWrapper, scale: float,
                 parent: QGraphicsItem | None = None):
        QGraphicsItem.__init__(self, parent)
        self.stage_item_init(wrapper, scale)
        self._cached_pixmap: QPixmap | None = None
        self._cached_size: tuple[int, int] = (0, 0)
        self.update_from_model()

    def _get_pixmap(self) -> QPixmap | None:
        """Ottiene il pixmap SVG renderizzato per le dimensioni correnti."""
        it = self.wrapper.item
        w_px = max(1, int(it.width * self.scale))
        h_px = max(1, int(it.height * self.scale))

        if (w_px, h_px) == self._cached_size and self._cached_pixmap is not None:
            return self._cached_pixmap

        manager = TargetSvgManager.instance()
        pixmap = manager.get_pixmap(it.item_type, w_px, h_px)
        if pixmap is not None and not pixmap.isNull():
            self._cached_pixmap = pixmap
            self._cached_size = (w_px, h_px)
            return pixmap
        return None

    def update_from_model(self) -> None:
        """Aggiorna posizione, rotazione e invalida cache pixmap."""
        self._cached_size = (0, 0)  # forza refresh
        self.prepareGeometryChange()
        super().update_from_model()

    def boundingRect(self) -> QRectF:
        it = self.wrapper.item
        w_px = it.width * self.scale
        h_px = it.height * self.scale
        return _with_rotation_handle(QRectF(-w_px / 2, -h_px / 2, w_px, h_px))

    def paint(self, painter: QPainter, option, widget=None) -> None:
        pixmap = self._get_pixmap()
        if pixmap is not None:
            r = self.boundingRect()
            painter.drawPixmap(r.toRect(), pixmap)
        else:
            # Fallback: ellisse colorata
            it = self.wrapper.item
            painter.setBrush(QBrush(QColor(it.color)))
            painter.setPen(QPen(QColor("#0f172a"), 2))
            painter.drawEllipse(self.boundingRect())

        self._paint_decoration(painter)
        self._draw_violation_highlight(painter)
        self._draw_selection_highlight(painter)
        self._draw_resize_handles(painter)
        self._draw_rotation_handle(painter)

    def _paint_decoration(self, painter: QPainter) -> None:
        """Decorazioni specifiche per tipo bersaglio."""
        it = self.wrapper.item
        br = self.boundingRect()

        if it.item_type == ItemType.NO_SHOOT:
            # X rossa
            margin = br.width() * 0.15
            pen = QPen(QColor("#dc2626"), 2)
            painter.setPen(pen)
            painter.drawLine(
                br.left() + margin, br.top() + margin,
                br.right() - margin, br.bottom() - margin,
            )
            painter.drawLine(
                br.right() - margin, br.top() + margin,
                br.left() + margin, br.bottom() - margin,
            )

        elif it.item_type == ItemType.SWINGER:
            # Arco di oscillazione
            amp = it.properties.get("amplitude", 45)
            pen = QPen(QColor("#a855f7"), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = 40
            start_angle = -amp - self.rotation()
            span = amp * 2
            painter.drawArc(-r, -r, r * 2, r * 2,
                            int(start_angle * 16), int(span * 16))

        elif it.item_type == ItemType.DROP_TURNER:
            # Freccia caduta
            pen = QPen(QColor("#0f172a"), 2)
            painter.setPen(pen)
            cx, cy = br.center().x(), br.center().y()
            painter.drawLine(cx, cy - 8, cx, cy + 8)
            painter.drawLine(cx - 4, cy + 4, cx, cy + 8)
            painter.drawLine(cx + 4, cy + 4, cx, cy + 8)

        elif it.item_type == ItemType.MOVER:
            # Linea traiettoria
            dist = it.properties.get("distance", 3.0) * self.scale
            pen = QPen(QColor("#f97316"), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            angle = math.radians(self.rotation())
            dx = math.cos(angle) * dist / 2
            dy = math.sin(angle) * dist / 2
            painter.drawLine(-dx, -dy, dx, dy)

    def _draw_selection_highlight(self, painter: QPainter) -> None:
        if not self.isSelected():
            return
        pen = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        br = self.boundingRect().adjusted(-4, -4, 4, 4)
        painter.drawRect(br)

    # I target non sono resizeables (le dimensioni sono fisse per tipo)
    def _draw_resize_handles(self, painter: QPainter) -> None:
        return  # no resize per bersagli

    def _handle_press_on_resize(self, pos: QPointF) -> None:
        return None  # no resize per bersagli


# ═══════════════════════════════════════════════════════════════════════════════
#  CompositeTargetGraphicsItem — bersagli compositi (doppi, bobber, ecc.)
# ═══════════════════════════════════════════════════════════════════════════════

class CompositeTargetGraphicsItem(StageItemMixin, QGraphicsItem):
    """Renderizza bersagli compositi: doppietti, bobber, ecc.

    Ogni tipo composito è formato da più sub-target (paper, steel,
    no-shoot) disegnati come rettangoli colorati con etichette.
    """

    def __init__(self, wrapper: StageItemWrapper, scale: float,
                 parent: QGraphicsItem | None = None):
        QGraphicsItem.__init__(self, parent)
        self.stage_item_init(wrapper, scale)
        self.update_from_model()

    def boundingRect(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        margin = 10
        return QRectF(-w / 2 - margin, -h / 2 - margin, w + margin * 2, h + margin * 2)

    def paint(self, painter, option, widget=None):
        it = self.wrapper.item
        s = self.scale
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Determina la composizione
        from core.scoring import get_composite_info
        info = get_composite_info(it.item_type)
        if not info:
            painter.restore()
            return

        sub_targets = info.get("sub_targets", [])
        bobber_mode = it.item_type in (ItemType.BOBBER_PLATE, ItemType.DOUBLE_BOBBER)

        for dx, dy, sub_type, label in sub_targets:
            cx = dx * s
            cy = dy * s

            if sub_type == ItemType.PAPER_TARGET:
                # Rettangolo marrone
                color = QColor("#8B4513")
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor("#5c2e0d"), 1.5))
                pw, ph = 0.45 * s, 0.75 * s
                painter.drawRoundedRect(QRectF(cx - pw / 2, cy - ph / 2, pw, ph), 4, 4)
                # Label
                painter.setPen(QPen(QColor("white"), 1))
                painter.drawText(QRectF(cx - pw / 2, cy - ph / 2, pw, ph),
                                 Qt.AlignmentFlag.AlignCenter, label)

            elif sub_type == ItemType.NO_SHOOT:
                # Rettangolo giallo con X
                color = QColor("#eab308")
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor("#a16207"), 1.5))
                pw, ph = 0.45 * s, 0.75 * s
                painter.drawRoundedRect(QRectF(cx - pw / 2, cy - ph / 2, pw, ph), 4, 4)
                # X rossa
                pen = QPen(QColor("#dc2626"), 2)
                painter.setPen(pen)
                painter.drawLine(cx - pw / 4, cy - ph / 4, cx + pw / 4, cy + ph / 4)
                painter.drawLine(cx + pw / 4, cy - ph / 4, cx - pw / 4, cy + ph / 4)
                # Label
                painter.setPen(QPen(QColor("#5c2e0d"), 1))
                painter.drawText(QRectF(cx - pw / 2, cy - ph / 2, pw, ph),
                                 Qt.AlignmentFlag.AlignCenter, label)

            elif sub_type == ItemType.METAL_PLATE:
                # Cerchio arancione (bobber) o grigio
                if bobber_mode:
                    color = QColor("#f97316")
                else:
                    color = QColor("#d1d5db")
                painter.setBrush(QBrush(color))
                pen_width = 2 if bobber_mode else 1.5
                painter.setPen(QPen(QColor("#1e293b"), pen_width))
                r = 0.10 * s  # raggio
                painter.drawEllipse(QPointF(cx, cy), r, r)
                if bobber_mode:
                    # Frecina verso l'alto per indicare "pop-up"
                    painter.setPen(QPen(QColor("#1e293b"), 2))
                    painter.drawLine(cx, cy - r - 4, cx, cy - r - 10)
                    painter.drawLine(cx - 3, cy - r - 7, cx, cy - r - 10)
                    painter.drawLine(cx + 3, cy - r - 7, cx, cy - r - 10)
                # Label
                painter.setPen(QPen(QColor("white"), 1))
                f = painter.font()
                f.setPointSize(7)
                f.setBold(True)
                painter.setFont(f)
                painter.drawText(QRectF(cx - r, cy - r, r * 2, r * 2),
                                 Qt.AlignmentFlag.AlignCenter, label)

        # Etichetta riepilogativa sotto il composito
        desc = info.get("description", "")
        if desc:
            painter.setPen(QPen(QColor("#64748b"), 1))
            f = painter.font()
            f.setPointSize(7)
            f.setBold(False)
            painter.setFont(f)
            pw_tot = it.width * s
            painter.drawText(QRectF(-pw_tot / 2, s * 0.4, pw_tot, 14),
                             Qt.AlignmentFlag.AlignCenter, desc)

        painter.restore()

    def _draw_selection_highlight(self, painter: QPainter) -> None:
        if not self.isSelected():
            return
        pen = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        br = self.boundingRect().adjusted(-4, -4, 4, 4)
        painter.drawRect(br)


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
    markerSelected = Signal(object, object)  # {props} dict or None, marker_ref
    violationsChanged = Signal()  # emesso quando cambiano le violazioni

    def __init__(self, stage: Stage, parent=None):
        super().__init__(parent)
        self.stage = stage
        self.scale = 40.0
        self._items: dict[int, QGraphicsItem] = {}
        self._violation_ids: set[int] = set()
        self._last_violations: list[str] = []
        self.undo_stack = QUndoStack(self)
        self._shooting_area: ShootingAreaItem | None = None
        self._engagement_area: EngagementAreaItem | None = None
        self._path_item: PathPolylineItem = PathPolylineItem()
        self._setup_grid()
        self._sync_from_model()
        self._update_shooting_area()
        self.selectionChanged.connect(self._on_selection_changed)
        # Aggiorna area di tiro quando un item viene aggiunto/rimosso/modificato
        self.itemAdded.connect(lambda w: self._update_shooting_area())
        self.itemRemoved.connect(lambda i: self._update_shooting_area())
        self.itemUpdated.connect(lambda i: self._update_shooting_area())

    def _setup_grid(self):
        # Rimuovi grid e shooting area precedenti (se ancora validi)
        if hasattr(self, 'grid') and self.grid is not None:
            try:
                self.removeItem(self.grid)
            except RuntimeError:
                pass  # C++ object già eliminato (es. dopo scene.clear())
        if self._shooting_area is not None:
            try:
                self.removeItem(self._shooting_area)
            except RuntimeError:
                pass
        self._shooting_area = None
        # Rimuovi vecchi stage item grafici dalla scena
        for g in list(self._items.values()):
            try:
                self.removeItem(g)
            except RuntimeError:
                pass
        self._items.clear()

        self.grid = GridItem(self.stage.width, self.stage.depth, self.scale)
        self._shooting_area = ShootingAreaItem()
        self._path_item = PathPolylineItem()
        self.addItem(self.grid)
        self.addItem(self._shooting_area)
        self.addItem(self._path_item)
        self.setSceneRect(
            0, 0,
            self.stage.width * self.scale,
            self.stage.depth * self.scale,
        )

    def _update_shooting_area(self):
        """Ricalcola e ridisegna l'area di tiro dal poligono perimetrale."""
        if self._shooting_area is None:
            return
        # Priorità 1: poligono salvato nelle properties (da generatore)
        poly = self.stage.properties.get("perimeter_poly")
        # Priorità 2: ricostruisci dalle fault-line
        if not poly:
            poly = _build_polygon_from_fault_lines(self.stage.items)
        self._shooting_area.set_polygon(poly or [], self.scale)

    def set_shooting_path(
        self,
        waypoints: list[tuple[float, float, str, bool]],
        color: str = "#3b82f6",
    ):
        """Update the path polyline rendering."""
        self._path_item.set_path(waypoints, self.scale, color)

    def reload_all_targets(self):
        """Ricarica tutti i bersagli dopo un cambio di configurazione aspetto."""
        from ui.editor.target_images import TargetSvgManager
        # Invalida cache SVG
        TargetSvgManager.reset_instance()
        # Aggiorna tutti gli SvgTargetGraphicsItem nella scena
        for item_id, gitem in self._items.items():
            if isinstance(gitem, SvgTargetGraphicsItem):
                gitem.update_from_model()

    def _sync_from_model(self):
        for it in self.stage.items:
            self._do_add_graphics_item(it)

    # ── Factory ──────────────────────────────────────────────────────────────

    _GRAPHICS_ITEM_CLASSES: dict[ItemType, tuple[type, str | None]] = {
        # Ostacoli (forme geometriche)
        ItemType.WALL:          (WallGraphicsItem, None),
        ItemType.BARRIER:       (BarrierGraphicsItem, None),
        ItemType.DOOR:          (DoorGraphicsItem, None),
        ItemType.HARD_COVER:    (HardCoverGraphicsItem, None),
        ItemType.SOFT_COVER:    (SoftCoverGraphicsItem, None),
        ItemType.FAULT_LINE:    (FaultLineGraphicsItem, None),
        # Bersagli standard (SVG vettoriali unificati)
        ItemType.PAPER_TARGET:  (SvgTargetGraphicsItem, None),
        ItemType.STEEL_TARGET:  (SvgTargetGraphicsItem, None),
        ItemType.POPPER:        (SvgTargetGraphicsItem, None),
        ItemType.METAL_PLATE:   (SvgTargetGraphicsItem, None),
        ItemType.MINI_TARGET:   (SvgTargetGraphicsItem, None),
        ItemType.MICRO_TARGET:  (SvgTargetGraphicsItem, None),
        ItemType.NO_SHOOT:      (SvgTargetGraphicsItem, None),
        ItemType.SWINGER:       (SvgTargetGraphicsItem, None),
        ItemType.DROP_TURNER:   (SvgTargetGraphicsItem, None),
        ItemType.MOVER:         (SvgTargetGraphicsItem, None),
        # Bersagli compositi (disegnati proceduralmente)
        ItemType.DOUBLET_SIDE:             (CompositeTargetGraphicsItem, None),
        ItemType.DOUBLET_OVERLAP:          (CompositeTargetGraphicsItem, None),
        ItemType.DOUBLET_SIDE_HOSTAGE:     (CompositeTargetGraphicsItem, None),
        ItemType.DOUBLET_OVERLAP_HOSTAGE:  (CompositeTargetGraphicsItem, None),
        ItemType.BOBBER_PLATE:             (CompositeTargetGraphicsItem, None),
        ItemType.DOUBLE_BOBBER:            (CompositeTargetGraphicsItem, None),
        ItemType.TARGET_PLUS_NOSHOOT:        (CompositeTargetGraphicsItem, None),
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
        if len(sel) == 1:
            g = sel[0]
            if hasattr(g, 'wrapper'):
                self.selectionChangedWrapper.emit(g.wrapper)
                self._hide_engagement_area()
            elif isinstance(g, ShootingPositionMarker):
                self.selectionChangedWrapper.emit(None)
                self.markerSelected.emit({
                    'type': 'shooting_position',
                    'x': g.pos_m[0],
                    'y': g.pos_m[1],
                    'is_start': g._is_start,
                    'label': g._label,
                }, g)
                self._show_engagement_area(g)
            elif isinstance(g, ObstacleMarker):
                self.selectionChangedWrapper.emit(None)
                self.markerSelected.emit({
                    'type': 'obstacle',
                    'x': g.pos_m[0],
                    'y': g.pos_m[1],
                    'width': g.width_m,
                    'rotation': g.rotation_deg,
                    'is_wall': g._is_wall,
                    'label': g._label,
                }, g)
                self._hide_engagement_area()
            else:
                self.selectionChangedWrapper.emit(None)
                self.markerSelected.emit(None, None)
                self._hide_engagement_area()
        else:
            self.selectionChangedWrapper.emit(None)
            self.markerSelected.emit(None, None)
            self._hide_engagement_area()
        # Forza repaint per aggiornare handle e bounding box
        self.invalidate()
        for g in self._items.values():
            if hasattr(g, 'update'):
                g.update()

    # ── Public API con undo ──────────────────────────────────────────────────

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Disegna la bounding box collettiva per selezione multipla."""
        super().drawForeground(painter, rect)
        sel = self.selectedItems()
        if len(sel) < 2:
            return
        # Calcola bounding box collettiva
        has_wrapper = all(hasattr(g, 'wrapper') for g in sel)
        if not has_wrapper:
            return
        br = None
        for g in sel:
            if br is None:
                br = g.sceneBoundingRect()
            else:
                br = br.united(g.sceneBoundingRect())
        if br is None:
            return
        painter.save()
        pen = QPen(QColor("#6366f1"), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#6366f1"), Qt.BrushStyle.Dense4Pattern))
        margin = 8.0
        painter.drawRoundedRect(
            br.adjusted(-margin, -margin, margin, margin),
            6, 6
        )
        # Etichetta col conteggio
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setBrush(QBrush(QColor("#6366f1")))
        txt = f"{len(sel)} selezionati"
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(txt) + 12
        th = fm.height() + 6
        lbl_rect = QRectF(br.center().x() - tw / 2, br.top() - th - margin - 4, tw, th)
        painter.drawRoundedRect(lbl_rect, 4, 4)
        painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, txt)
        painter.restore()

    # ── Evidenziazione violazioni ───────────────────────────────────────────

    def has_violation(self, item_id: int) -> bool:
        return item_id in self._violation_ids

    def get_violation_tooltip(self, item_id: int) -> str | None:
        """Restituisce tooltip descrittivo della violazione per un item."""
        if not self._last_violations:
            return None
        for v_text in self._last_violations:
            import re
            if re.search(rf'#{item_id}\b', v_text):
                return f"⚠️ {v_text}"
        return None

    def set_violations(self, item_ids: set[int], violations: list[str] | None = None):
        """Imposta gli ID degli item con violazioni IPSC.

        Salva anche il testo delle violazioni per tooltip.
        """
        self._last_violations = violations or []
        self._violation_ids = set(item_ids)
        self.violationsChanged.emit()
        for g in self._items.values():
            if hasattr(g, 'update'):
                g.update()

    # ── Area di ingaggio (per shooting position) ───────────────────────

    def _show_engagement_area(self, marker: ShootingPositionMarker):
        """Mostra l'area di ingaggio di 90° per una posizione di tiro."""
        if self._engagement_area:
            self.removeItem(self._engagement_area)
            self._engagement_area = None

        # Raccogli ostacoli (muri, barriere, coperture) dallo stage
        obstacles = []
        for it in self.stage.items:
            if it.item_type in (ItemType.WALL, ItemType.BARRIER, ItemType.HARD_COVER):
                obstacles.append((it.x, it.y, it.width, it.height, it.rotation))

        # Direzione di ingaggio: usa l'angolo della posizione o default 90° (verso backstop)
        sp_angle = 90.0
        for sp in self.stage.shooting_positions:
            if abs(sp.x - marker.pos_m[0]) < 1.0 and abs(sp.y - marker.pos_m[1]) < 1.0:
                sp_angle = sp.angle
                break

        self._engagement_area = EngagementAreaItem(
            marker.pos_m[0], marker.pos_m[1], self.scale,
            angle=sp_angle, range_m=max(self.stage.width, self.stage.depth) * 1.2,
            obstacles=obstacles,
        )
        self.addItem(self._engagement_area)

    def _hide_engagement_area(self):
        """Nasconde l'area di ingaggio."""
        if self._engagement_area:
            self.removeItem(self._engagement_area)
            self._engagement_area = None

    def push_add_item(self, item: StageItem):
        self.undo_stack.push(AddItemCommand(self, item))

    def push_remove_item(self, item_id: int):
        self.undo_stack.push(RemoveItemCommand(self, item_id))

    def push_remove_selected(self):
        """Rimuove tutti gli oggetti selezionati.

        Scansiona TUTTI gli item della scena (non solo selectedItems())
        perché i marker figli del grid potrebbero non essere rilevati
        da selectedItems() in alcuni contesti Qt.
        """
        for g in list(self.items()):
            if not g.isSelected():
                continue
            if isinstance(g, (ShootingPositionMarker, ObstacleMarker)):
                self._remove_marker(g)
            else:
                # Item stage normale
                for gid, gi in list(self._items.items()):
                    if gi is g:
                        self.push_remove_item(gid)
                        break

    def _remove_marker(self, g):
        """Rimuove un marker e notifica il callback."""
        self.removeItem(g)
        if hasattr(g, '_on_deleted') and g._on_deleted:
            g._on_deleted(g)

    def remove_marker_by_item(self, g):
        """Rimuove un marker specifico (chiamato da view)."""
        if isinstance(g, (ShootingPositionMarker, ObstacleMarker)):
            self._remove_marker(g)
            return True
        return False

    # ── Factory helpers ──────────────────────────────────────────────────────

    def add_wall(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        item = StageItem(0, ItemType.WALL, x, y, w, h, 0, "#475569", "Muro")
        self.push_add_item(item)

    def add_target(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                   item_type: ItemType = ItemType.PAPER_TARGET):
        from core.constants import TARGET_COLORS
        if item_type == ItemType.PAPER_TARGET:
            color = TARGET_COLORS.get("paper", "#8B4513")
            label = "Paper"
        else:
            color = TARGET_COLORS.get("steel_generic", "#d1d5db")
            label = "Steel"
        item = StageItem(0, item_type, x, y, w, h, 0, color, label)
        self.push_add_item(item)

    def add_fault_line(self, x: float, y: float, length: float = 3.0):
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.FAULT_LINE, x, y, length, 0.0, 0,
                         TARGET_COLORS.get("fault_line", "#dc2626"), "Fault Line")
        self.push_add_item(item)

    def add_no_shoot(self, x: float, y: float, w: float = 0.45, h: float = 0.45):
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.NO_SHOOT, x, y, w, h, 0,
                         TARGET_COLORS.get("no_shoot", "#eab308"), "No-Shoot")
        self.push_add_item(item)

    def add_barrier(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.BARRIER, x, y, w, h, 0,
                         TARGET_COLORS.get("barrier", "#fbbf24"), "Barriera")
        self.push_add_item(item)

    def add_door(self, x: float, y: float, w: float = 1.0, h: float = 0.1):
        item = StageItem(0, ItemType.DOOR, x, y, w, h, 0, "#92400e", "Porta")
        self.push_add_item(item)

    def add_swinger(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                    amplitude: float = 45.0, speed: float = 1.0):
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.SWINGER, x, y, w, h, 0,
                         TARGET_COLORS.get("swinger", "#A0522D"), "Swinger",
                         properties={"amplitude": amplitude, "speed": speed, "axis": "y"})
        self.push_add_item(item)

    def add_drop_turner(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                        fall_time: float = 0.5):
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.DROP_TURNER, x, y, w, h, 0,
                         TARGET_COLORS.get("drop_turner", "#8B6914"), "Drop Turner",
                         properties={"trigger": "hit", "fall_time": fall_time})
        self.push_add_item(item)

    def add_mover(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                  distance: float = 3.0, speed: float = 1.5):
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.MOVER, x, y, w, h, 0,
                         TARGET_COLORS.get("mover", "#CD853F"), "Mover",
                         properties={"distance": distance, "speed": speed, "direction": 0})
        self.push_add_item(item)

    # ── Nuovi tipi IPSC ──────────────────────────────────────────────────────

    def add_popper(self, x: float, y: float, diameter: float = 0.30):
        """Aggiunge un Popper (bersaglio metallico calibrato, App. C1-C2)."""
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.POPPER, x, y, diameter, diameter, 0,
                         TARGET_COLORS.get("popper", "#d1d5db"), "Popper",
                         properties={"calibrated": True, "calibration_pf": 125})
        self.push_add_item(item)

    def add_metal_plate(self, x: float, y: float, diameter: float = 0.20):
        """Aggiunge un piatto metallico (non calibrato, App. C3)."""
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.METAL_PLATE, x, y, diameter, diameter, 0,
                         TARGET_COLORS.get("metal_plate", "#e5e7eb"), "Piatto",
                         properties={"calibrated": False, "diameter": diameter})
        self.push_add_item(item)

    def add_mini_target(self, x: float, y: float):
        """Aggiunge un Mini Target IPSC (bersaglio cartaceo ridotto, App. B3)."""
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.MINI_TARGET, x, y, 0.30, 0.30, 0,
                         TARGET_COLORS.get("mini", "#8B4513"), "Mini Target",
                         properties={"scale": 0.75})
        self.push_add_item(item)

    def add_micro_target(self, x: float, y: float):
        """Aggiunge un Micro Target IPSC."""
        from core.constants import TARGET_COLORS
        item = StageItem(0, ItemType.MICRO_TARGET, x, y, 0.20, 0.20, 0,
                         TARGET_COLORS.get("micro", "#8B4513"), "Micro Target",
                         properties={"scale": 0.50})
        self.push_add_item(item)

    def add_composite(self, x: float, y: float, item_type: ItemType):
        """Aggiunge un bersaglio composito (doppietti, bobber, target+noshoot)."""
        from core.constants import TARGET_DIMENSIONS, TARGET_COLORS
        from core.scoring import get_composite_info
        key = item_type.name.lower()
        w, h = TARGET_DIMENSIONS.get(key, (0.70, 0.75))
        color = TARGET_COLORS.get(key, "#808080")
        info = get_composite_info(item_type)
        props = dict(info.get("props", {})) if info else {}
        item = StageItem(0, item_type, x, y, w, h, 0, color, info.get("description", "") if info else "", properties=props)
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

    # ══════════════════════════════════════════════════════════════════════
    #  Shooting position markers (Fase 2)
    # ══════════════════════════════════════════════════════════════════════

    def add_shooting_position_marker(self, x: float, y: float,
                                      is_start: bool = True,
                                      index: int = 1,
                                      on_changed: callable = None,
                                      on_deleted: callable = None,
                                      ) -> ShootingPositionMarker:
        """Aggiunge un marker visivo per una shooting position.
        Mostra il numero progressivo (1, 2, 3...).
        Il colore verde indica la posizione di partenza (Start).
        """
        label = str(index)
        marker = ShootingPositionMarker(
            x, y, self.scale,
            label=label, is_start=is_start, index=index,
            on_changed=on_changed,
            on_deleted=on_deleted,
        )
        marker.setParentItem(self.grid)  # aggiunge automaticamente alla scena
        return marker

    def clear_shooting_position_markers(self):
        """Rimuove tutti i marker di shooting position dalla scena.
        Usa attributo pos_m come fallback per identificare i marker."""
        count = 0
        for item in list(self.items()):
            if isinstance(item, ShootingPositionMarker):
                self.removeItem(item)
                count += 1
            elif hasattr(item, 'pos_m') and hasattr(item, '_is_start'):
                # Fallback: qualunque item con attributi da shooting position
                self.removeItem(item)
                count += 1
        if count > 0:
            self.stage.shooting_positions.clear()

    def sync_shooting_positions(self):
        """Sincronizza i marker con stage.shooting_positions."""
        self.clear_shooting_position_markers()
        for i, sp in enumerate(self.stage.shooting_positions):
            self.add_shooting_position_marker(
                sp.x, sp.y, is_start=sp.is_start, index=i + 1,
            )

    # ══════════════════════════════════════════════════════════════════════
    #  Obstacle markers (Fase 2)
    # ══════════════════════════════════════════════════════════════════════

    def add_obstacle_marker(self, x: float, y: float,
                             width: float = 3.0, rotation: float = 0.0,
                             is_wall: bool = True,
                             label: str = "",
                             on_changed: callable = None,
                             on_deleted: callable = None) -> ObstacleMarker:
        """Aggiunge un marker visivo per un ostacolo posizionato dall'utente."""
        marker = ObstacleMarker(
            x, y, self.scale,
            width=width, rotation=rotation,
            is_wall=is_wall, label=label,
            on_changed=on_changed,
            on_deleted=on_deleted,
        )
        marker.setParentItem(self.grid)  # aggiunge automaticamente alla scena
        return marker

    def clear_obstacle_markers(self):
        """Rimuove tutti i marker di ostacoli dalla scena."""
        for item in list(self.items()):
            if isinstance(item, ObstacleMarker):
                self.removeItem(item)

    def sync_obstacles_from_items(self):
        """Sincronizza i marker con gli ostacoli nello stage.
        Mostra marker solo per ostacoli con properties["user_placed"] = True.
        """
        self.clear_obstacle_markers()
        for it in self.stage.items:
            if it.properties.get("user_placed"):
                is_wall = it.item_type == ItemType.WALL
                self.add_obstacle_marker(
                    it.x, it.y,
                    width=it.width,
                    rotation=it.rotation,
                    is_wall=is_wall,
                    label=it.label or ("M" if is_wall else "B"),
                )
