# ui/viewer3d/quick_3d_widget.py
from __future__ import annotations
from typing import List, Dict, Any
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Property, QUrl
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtQuick import QQuickView

from core.models import Stage, StageItem, ItemType


class Stage3DModel(QObject):
    """Modello dati esposto a QML per la scena 3D."""
    objectsChanged = Signal()

    def __init__(self, stage: Stage, parent=None):
        super().__init__(parent)
        self._stage = stage
        self._objects: List[Dict[str, Any]] = []
        self.rebuild()

    def rebuild(self):
        """Ricostruisce la lista oggetti dal modello Python."""
        new_objs = []
        for it in self._stage.items:
            obj = self._item_to_dict(it)
            if obj:
                new_objs.append(obj)
        self._objects = new_objs
        self.objectsChanged.emit()

    def _item_to_dict(self, it: StageItem) -> Dict[str, Any] | None:
        if it.item_type == ItemType.WALL:
            # Muro verticale: altezza fissa 2.0m, spessore 0.1m
            return {
                "type": "wall",
                "x": it.x,
                "y": 1.0,  # centro verticale
                "z": it.y,
                "scaleX": it.width,
                "scaleY": 2.0,
                "scaleZ": 0.1,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                              ItemType.MINI_TARGET, ItemType.MICRO_TARGET):
            return {
                "type": "target",
                "x": it.x,
                "y": 0.9,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": it.height,
                "scaleZ": 0.02,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type in (ItemType.POPPER, ItemType.METAL_PLATE):
            return {
                "type": "steel",
                "x": it.x,
                "y": 0.5,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": it.width,
                "scaleZ": 0.02,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type == ItemType.FAULT_LINE:
            # Fault line rialzata (visibile come cordolo basso)
            return {
                "type": "fault",
                "x": it.x,
                "y": 0.03,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": 0.06,
                "scaleZ": 0.08,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type in (ItemType.HARD_COVER, ItemType.SOFT_COVER):
            # Copertura: usa la stessa geometria di WALL ma colore diverso
            return {
                "type": "wall",
                "x": it.x,
                "y": 1.0,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": 2.0,
                "scaleZ": 0.1,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type == ItemType.NO_SHOOT:
            return {
                "type": "noshoot",
                "x": it.x,
                "y": 0.9,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": it.height,
                "scaleZ": 0.02,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type == ItemType.BARRIER:
            return {
                "type": "barrier",
                "x": it.x,
                "y": 0.6,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": 1.2,
                "scaleZ": 0.1,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type == ItemType.DOOR:
            return {
                "type": "door",
                "x": it.x,
                "y": 1.0,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": 2.0,
                "scaleZ": 0.05,
                "rotation": it.rotation,
                "color": it.color,
            }
        elif it.item_type == ItemType.SWINGER:
            return {
                "type": "swinger",
                "x": it.x,
                "y": 1.2,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": it.height,
                "scaleZ": 0.02,
                "rotation": it.rotation,
                "color": it.color,
                "amplitude": it.properties.get("amplitude", 45),
                "speed": it.properties.get("speed", 1.0),
            }
        elif it.item_type == ItemType.DROP_TURNER:
            return {
                "type": "drop_turner",
                "x": it.x,
                "y": 1.0,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": it.height,
                "scaleZ": 0.02,
                "rotation": it.rotation,
                "color": it.color,
                "fall_time": it.properties.get("fall_time", 0.5),
            }
        elif it.item_type == ItemType.MOVER:
            return {
                "type": "mover",
                "x": it.x,
                "y": 0.9,
                "z": it.y,
                "scaleX": it.width,
                "scaleY": it.height,
                "scaleZ": 0.02,
                "rotation": it.rotation,
                "color": it.color,
                "distance": it.properties.get("distance", 3.0),
                "speed": it.properties.get("speed", 1.5),
            }
        return None

    @Property(list, notify=objectsChanged)
    def objects(self) -> List[Dict[str, Any]]:
        return self._objects


class Quick3DWidget(QQuickWidget):
    """Wrapper QQuickWidget per il viewer 3D."""
    def __init__(self, stage: Stage, parent=None):
        super().__init__(parent)
        self._stage = stage
        self._model = Stage3DModel(stage, self)
        self.rootContext().setContextProperty("stage3dModel", self._model)
        self.rootContext().setContextProperty("stageWidth", stage.width)
        self.rootContext().setContextProperty("stageDepth", stage.depth)

        qml_file = Path(__file__).with_name("StageScene.qml")
        self.setSource(QUrl.fromLocalFile(str(qml_file)))
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)

    def refresh(self):
        self._model.rebuild()

    def update_dimensions(self, width: float, depth: float):
        """Aggiorna le dimensioni dello stage nel context 3D."""
        self.rootContext().setContextProperty("stageWidth", width)
        self.rootContext().setContextProperty("stageDepth", depth)
        self._model.rebuild()

    def reset_camera(self):
        """Resetta la camera 3D alla posizione orbitale iniziale."""
        root = self.rootObject()
        if root:
            root.resetOrbitCamera()

    def connect_fullscreen_signal(self, callback):
        """Collega il segnale requestFullscreen del QML a un callback."""
        root = self.rootObject()
        if root:
            root.requestFullscreen.connect(callback)
