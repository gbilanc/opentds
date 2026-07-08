# ui/editor/stage_scene.py
"""Scena 2D con undo/redo, griglia, snap e tutti i tipi di oggetto."""
from __future__ import annotations
from typing import Optional
import math
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QPen, QBrush, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsRectItem, QGraphicsEllipseItem,
    QGraphicsItem
)
from PySide6.QtGui import QUndoStack, QUndoCommand

from core.models import Stage, StageItem, ItemType


class StageItemWrapper(QObject):
    """Wrapper Qt per uno StageItem."""
    changed = Signal()

    def __init__(self, item: StageItem, parent=None):
        super().__init__(parent)
        self.item = item


class GridItem(QGraphicsItem):
    """Griglia metrica sullo sfondo."""
    def __init__(self, width_m: float, depth_m: float, scale: float = 40.0, parent=None):
        super().__init__(parent)
        self.width_m = width_m
        self.depth_m = depth_m
        self.scale = scale
        self.pen = QPen(QColor("#e2e8f0"))
        self.pen.setWidthF(1)

    def boundingRect(self):
        from PySide6.QtCore import QRectF
        return QRectF(0, 0, self.width_m * self.scale, self.depth_m * self.scale)

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen)
        w = self.width_m * self.scale
        h = self.depth_m * self.scale
        for i in range(int(self.width_m) + 1):
            x = i * self.scale
            painter.drawLine(x, 0, x, h)
        for i in range(int(self.depth_m) + 1):
            y = i * self.scale
            painter.drawLine(0, y, w, y)


def _snap_pos(pos, scale):
    snap = 0.5 * scale
    x = round(pos.x() / snap) * snap
    y = round(pos.y() / snap) * snap
    from PySide6.QtCore import QPointF
    return QPointF(x, y)


def _base_item_flags(item: QGraphicsItem):
    item.setFlags(
        QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
        QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
        QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
    )
    item.setAcceptHoverEvents(True)


# ---------- ROTATION HANDLE MIXIN ----------

class RotationHandleMixin:
    """Mixin che aggiunge un handle di rotazione trascinabile agli item selezionati."""

    _is_rotating = False

    def _rotation_handle_rect(self):
        br = self.boundingRect()
        handle_size = 12.0
        cx = br.center().x()
        top = br.top()
        from PySide6.QtCore import QRectF
        return QRectF(cx - handle_size / 2, top - handle_size - 8, handle_size, handle_size)

    def _draw_rotation_handle(self, painter):
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

    def _handle_press_on_rotation(self, pos):
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
            if hasattr(self, 'wrapper'):
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


class WallGraphicsItem(RotationHandleMixin, QGraphicsRectItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        self.setBrush(QBrush(QColor(wrapper.item.color)))
        self.setPen(QPen(QColor("#0f172a"), 2))

    def update_from_model(self):
        it = self.wrapper.item
        half_w = (it.width * self.scale) / 2
        half_h = (it.height * self.scale) / 2
        self.setRect(-half_w, -half_h, it.width * self.scale, it.height * self.scale)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            pen = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


class TargetGraphicsItem(RotationHandleMixin, QGraphicsEllipseItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        self.setBrush(QBrush(QColor(wrapper.item.color)))
        self.setPen(QPen(QColor("#0f172a"), 2))

    def update_from_model(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        self.setRect(-w/2, -h/2, w, h)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            pen = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


class FaultLineGraphicsItem(RotationHandleMixin, QGraphicsItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()

    def boundingRect(self):
        from PySide6.QtCore import QRectF
        w = self.wrapper.item.width * self.scale
        pen_w = 8
        return QRectF(-w/2 - pen_w, -pen_w, w + pen_w*2, pen_w*2)

    def paint(self, painter, option, widget=None):
        pen = QPen(QColor("#dc2626"), 3)
        pen.setDashPattern([6, 4])
        painter.setPen(pen)
        w = self.wrapper.item.width * self.scale
        painter.drawLine(-w/2, 0, w/2, 0)
        if self.isSelected():
            sel = QPen(QColor("#2563eb"), 1, Qt.PenStyle.DashLine)
            painter.setPen(sel)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
        self._draw_rotation_handle(painter)

    def update_from_model(self):
        self.setPos(self.wrapper.item.x * self.scale, self.wrapper.item.y * self.scale)
        self.setRotation(self.wrapper.item.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)


class NoShootGraphicsItem(RotationHandleMixin, QGraphicsEllipseItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        c = QColor(wrapper.item.color)
        c.setAlpha(120)
        self.setBrush(QBrush(c))
        self.setPen(QPen(QColor("#dc2626"), 2))

    def update_from_model(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        self.setRect(-w/2, -h/2, w, h)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        r = self.rect()
        pen = QPen(QColor("#7f1d1d"), 2)
        painter.setPen(pen)
        painter.drawLine(r.topLeft(), r.bottomRight())
        painter.drawLine(r.topRight(), r.bottomLeft())
        if self.isSelected():
            sel = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(sel)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


class BarrierGraphicsItem(RotationHandleMixin, QGraphicsRectItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        c = QColor(wrapper.item.color)
        c.setAlpha(80)
        self.setBrush(QBrush(c))
        pen = QPen(QColor("#f59e0b"), 2)
        pen.setDashPattern([6, 4])
        self.setPen(pen)

    def update_from_model(self):
        it = self.wrapper.item
        half_w = (it.width * self.scale) / 2
        half_h = (it.height * self.scale) / 2
        self.setRect(-half_w, -half_h, it.width * self.scale, it.height * self.scale)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.isSelected():
            sel = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(sel)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


class DoorGraphicsItem(RotationHandleMixin, QGraphicsRectItem):
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        self.setBrush(QBrush(QColor(wrapper.item.color)))
        self.setPen(QPen(QColor("#0f172a"), 2))

    def update_from_model(self):
        it = self.wrapper.item
        half_w = (it.width * self.scale) / 2
        half_h = (it.height * self.scale) / 2
        self.setRect(-half_w, -half_h, it.width * self.scale, it.height * self.scale)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        r = self.rect()
        pen = QPen(QColor("#0f172a"), 1)
        painter.setPen(pen)
        painter.drawLine(r.center().x(), r.top(), r.center().x(), r.bottom())
        handle = QPainterPath()
        hx = r.center().x() + r.width()*0.15
        hy = r.center().y()
        handle.addEllipse(hx-3, hy-3, 6, 6)
        painter.fillPath(handle, QColor("#0f172a"))
        if self.isSelected():
            sel = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(sel)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


class SwingerGraphicsItem(RotationHandleMixin, QGraphicsRectItem):
    """Swinger: bersaglio con arco di oscillazione 2D."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        self.setBrush(QBrush(QColor("#a855f7")))
        self.setPen(QPen(QColor("#0f172a"), 2))

    def update_from_model(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        self.setRect(-w/2, -h/2, w, h)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Arco di oscillazione
        amp = self.wrapper.item.properties.get("amplitude", 45)
        pen = QPen(QColor("#a855f7"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = 40
        start = -amp - self.rotation()
        span = amp * 2
        painter.drawArc(int(-r), int(-r), int(r*2), int(r*2), int(start*16), int(span*16))
        if self.isSelected():
            sel = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(sel)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


class DropTurnerGraphicsItem(RotationHandleMixin, QGraphicsRectItem):
    """Drop Turner: bersaglio che cade quando colpito."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        self.setBrush(QBrush(QColor("#14b8a6")))
        self.setPen(QPen(QColor("#0f172a"), 2))

    def update_from_model(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        self.setRect(-w/2, -h/2, w, h)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Freccia verso il basso
        pen = QPen(QColor("#0f172a"), 2)
        painter.setPen(pen)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        painter.drawLine(int(cx), int(cy-8), int(cx), int(cy+8))
        painter.drawLine(int(cx-4), int(cy+4), int(cx), int(cy+8))
        painter.drawLine(int(cx+4), int(cy+4), int(cx), int(cy+8))
        if self.isSelected():
            sel = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(sel)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


class MoverGraphicsItem(RotationHandleMixin, QGraphicsRectItem):
    """Mover: bersaglio su rotaia con traiettoria 2D."""
    def __init__(self, wrapper: StageItemWrapper, scale: float, parent=None):
        super().__init__(parent)
        self.wrapper = wrapper
        self.scale = scale
        _base_item_flags(self)
        self.update_from_model()
        self.setBrush(QBrush(QColor("#f97316")))
        self.setPen(QPen(QColor("#0f172a"), 2))

    def update_from_model(self):
        it = self.wrapper.item
        w = it.width * self.scale
        h = it.height * self.scale
        self.setRect(-w/2, -h/2, w, h)
        self.setPos(it.x * self.scale, it.y * self.scale)
        self.setRotation(it.rotation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            return _snap_pos(value, self.scale)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.wrapper.item.x = self.pos().x() / self.scale
            self.wrapper.item.y = self.pos().y() / self.scale
            self.wrapper.changed.emit()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Linea traiettoria
        dist = self.wrapper.item.properties.get("distance", 3.0) * self.scale
        pen = QPen(QColor("#f97316"), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        angle = math.radians(self.rotation())
        dx = math.cos(angle) * dist / 2
        dy = math.sin(angle) * dist / 2
        painter.drawLine(int(-dx), int(-dy), int(dx), int(dy))
        if self.isSelected():
            sel = QPen(QColor("#2563eb"), 2, Qt.PenStyle.DashLine)
            painter.setPen(sel)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-4, -4, 4, 4))
        self._draw_rotation_handle(painter)


# ---------- UNDO COMMANDS ----------

class AddItemCommand(QUndoCommand):
    def __init__(self, scene: "StageScene", item: StageItem, description: str = "Aggiungi oggetto"):
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
    def __init__(self, scene: "StageScene", item_id: int, description: str = "Rimuovi oggetto"):
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


# ---------- SCENE ----------

class StageScene(QGraphicsScene):
    itemAdded = Signal(StageItemWrapper)
    itemRemoved = Signal(int)
    itemUpdated = Signal(int)
    selectionChangedWrapper = Signal(object)

    def __init__(self, stage: Stage, parent=None):
        super().__init__(parent)
        self.stage = stage
        self.scale = 40.0
        self._items: dict[int, QGraphicsItem] = {}
        self.undo_stack = QUndoStack(self)
        self._setup_grid()
        self._sync_from_model()
        self.selectionChanged.connect(self._on_selection_changed)

    def _setup_grid(self):
        self.grid = GridItem(self.stage.width, self.stage.depth, self.scale)
        self.addItem(self.grid)
        self.setSceneRect(0, 0, self.stage.width * self.scale, self.stage.depth * self.scale)

    def _sync_from_model(self):
        for it in self.stage.items:
            self._do_add_graphics_item(it)

    def _make_graphics_item(self, item: StageItem) -> QGraphicsItem:
        wrapper = StageItemWrapper(item)
        wrapper.changed.connect(lambda: self.itemUpdated.emit(item.id))
        if item.item_type == ItemType.WALL:
            return WallGraphicsItem(wrapper, self.scale)
        elif item.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET):
            return TargetGraphicsItem(wrapper, self.scale)
        elif item.item_type == ItemType.FAULT_LINE:
            return FaultLineGraphicsItem(wrapper, self.scale)
        elif item.item_type == ItemType.NO_SHOOT:
            return NoShootGraphicsItem(wrapper, self.scale)
        elif item.item_type == ItemType.BARRIER:
            return BarrierGraphicsItem(wrapper, self.scale)
        elif item.item_type == ItemType.DOOR:
            return DoorGraphicsItem(wrapper, self.scale)
        elif item.item_type == ItemType.SWINGER:
            return SwingerGraphicsItem(wrapper, self.scale)
        elif item.item_type == ItemType.DROP_TURNER:
            return DropTurnerGraphicsItem(wrapper, self.scale)
        elif item.item_type == ItemType.MOVER:
            return MoverGraphicsItem(wrapper, self.scale)
        else:
            return WallGraphicsItem(wrapper, self.scale)

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

    # ---- PUBLIC API with undo ----

    def push_add_item(self, item: StageItem):
        cmd = AddItemCommand(self, item)
        self.undo_stack.push(cmd)

    def push_remove_item(self, item_id: int):
        cmd = RemoveItemCommand(self, item_id)
        self.undo_stack.push(cmd)

    def push_remove_selected(self):
        for g in list(self.selectedItems()):
            for gid, gi in list(self._items.items()):
                if gi is g:
                    self.push_remove_item(gid)
                    break

    # ---- Factory helpers ----

    def add_wall(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        item = StageItem(0, ItemType.WALL, x, y, w, h, 0, "#475569", "Muro")
        self.push_add_item(item)

    def add_target(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                   item_type: ItemType = ItemType.PAPER_TARGET):
        color = "#ef4444" if item_type == ItemType.PAPER_TARGET else "#3b82f6"
        label = "Paper" if item_type == ItemType.PAPER_TARGET else "Steel"
        item = StageItem(0, item_type, x, y, w, h, 0, color, label)
        self.push_add_item(item)

    def add_fault_line(self, x: float, y: float, length: float = 3.0):
        item = StageItem(0, ItemType.FAULT_LINE, x, y, length, 0.0, 0, "#dc2626", "Fault Line")
        self.push_add_item(item)

    def add_no_shoot(self, x: float, y: float, w: float = 0.45, h: float = 0.45):
        item = StageItem(0, ItemType.NO_SHOOT, x, y, w, h, 0, "#f87171", "No-Shoot")
        self.push_add_item(item)

    def add_barrier(self, x: float, y: float, w: float = 2.0, h: float = 0.2):
        item = StageItem(0, ItemType.BARRIER, x, y, w, h, 0, "#fbbf24", "Barriera")
        self.push_add_item(item)

    def add_door(self, x: float, y: float, w: float = 1.0, h: float = 0.1):
        item = StageItem(0, ItemType.DOOR, x, y, w, h, 0, "#92400e", "Porta")
        self.push_add_item(item)

    def add_swinger(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                    amplitude: float = 45.0, speed: float = 1.0):
        item = StageItem(0, ItemType.SWINGER, x, y, w, h, 0, "#a855f7", "Swinger",
                         properties={"amplitude": amplitude, "speed": speed, "axis": "y"})
        self.push_add_item(item)

    def add_drop_turner(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                        fall_time: float = 0.5):
        item = StageItem(0, ItemType.DROP_TURNER, x, y, w, h, 0, "#14b8a6", "Drop Turner",
                         properties={"trigger": "hit", "fall_time": fall_time})
        self.push_add_item(item)

    def add_mover(self, x: float, y: float, w: float = 0.45, h: float = 0.45,
                  distance: float = 3.0, speed: float = 1.5):
        item = StageItem(0, ItemType.MOVER, x, y, w, h, 0, "#f97316", "Mover",
                         properties={"distance": distance, "speed": speed, "direction": 0})
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
