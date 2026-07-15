# ui/viewer3d/quick_3d_widget.py
from __future__ import annotations
from typing import List, Dict, Any
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Property, QUrl
from PySide6.QtQuickWidgets import QQuickWidget

from core.models import Stage, StageItem, ItemType

ASSETS_DIR = Path(__file__).parent.parent.parent / "assets"
TEXTURES_DIR = ASSETS_DIR / "textures"


def _tex(name: str) -> str:
    """Restituisce il path assoluto a una texture."""
    return (TEXTURES_DIR / name).resolve().as_uri()  # URI per QML


def _material_type(it: StageItem) -> str:
    """Determina il tipo di materiale PBR per l'oggetto."""
    if it.item_type == ItemType.WALL:
        return "wall"
    elif it.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET,
                          ItemType.MINI_TARGET, ItemType.MICRO_TARGET):
        return "target"
    elif it.item_type in (ItemType.POPPER, ItemType.METAL_PLATE):
        return "steel"
    elif it.item_type == ItemType.FAULT_LINE:
        return "fault"
    elif it.item_type == ItemType.NO_SHOOT:
        return "noshoot"
    elif it.item_type == ItemType.BARRIER:
        return "barrier"
    elif it.item_type == ItemType.DOOR:
        return "door"
    elif it.item_type == ItemType.HARD_COVER:
        return "hard_cover"
    elif it.item_type == ItemType.SOFT_COVER:
        return "soft_cover"
    elif it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER):
        return "target"
    return "generic"


def _is_collidable(it: StageItem) -> bool:
    """Determina se l'oggetto blocca il movimento in FP mode."""
    return it.item_type in (
        ItemType.WALL,
        ItemType.BARRIER,
        ItemType.DOOR,
        ItemType.HARD_COVER,
        ItemType.SOFT_COVER,
    )


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
        base: dict[str, Any] = {
            "x": it.x,
            "z": it.y,
            "rotation": it.rotation,
            "color": it.color,
            "mat": _material_type(it),
            "collidable": _is_collidable(it),
        }

        type_geom: dict[str, Any] = {
            ItemType.WALL:               {"y": 1.0, "sx": it.width, "sy": 2.0, "sz": 0.1},
            ItemType.PAPER_TARGET:       {"y": 0.9, "sx": it.width, "sy": it.height, "sz": 0.02},
            ItemType.STEEL_TARGET:       {"y": 0.9, "sx": it.width, "sy": it.height, "sz": 0.02},
            ItemType.MINI_TARGET:        {"y": 0.9, "sx": it.width, "sy": it.height, "sz": 0.02},
            ItemType.MICRO_TARGET:       {"y": 0.9, "sx": it.width, "sy": it.height, "sz": 0.02},
            ItemType.POPPER:             {"y": 0.5, "sx": it.width, "sy": it.width, "sz": 0.02},
            ItemType.METAL_PLATE:        {"y": 0.5, "sx": it.width, "sy": it.width, "sz": 0.02},
            ItemType.FAULT_LINE:         {"y": 0.005, "sx": it.width, "sy": 0.01, "sz": 0.06},
            ItemType.NO_SHOOT:           {"y": 0.9, "sx": it.width, "sy": it.height, "sz": 0.02},
            ItemType.BARRIER:            {"y": 0.6, "sx": it.width, "sy": 1.2, "sz": 0.1},
            ItemType.DOOR:               {"y": 1.0, "sx": it.width, "sy": 2.0, "sz": 0.05},
            ItemType.HARD_COVER:         {"y": 1.0, "sx": it.width, "sy": 2.0, "sz": 0.1},
            ItemType.SOFT_COVER:         {"y": 1.0, "sx": it.width, "sy": 2.0, "sz": 0.08},
            ItemType.SWINGER:            {"y": 1.2, "sx": it.width, "sy": it.height, "sz": 0.02},
            ItemType.DROP_TURNER:        {"y": 1.0, "sx": it.width, "sy": it.height, "sz": 0.02},
            ItemType.MOVER:              {"y": 0.9, "sx": it.width, "sy": it.height, "sz": 0.02},
        }

        geom = type_geom.get(it.item_type)
        if geom is None:
            return None

        base.update(geom)

        # Proprietà specifiche
        if it.item_type == ItemType.SWINGER:
            base["amplitude"] = it.properties.get("amplitude", 45)
            base["speed"] = it.properties.get("speed", 1.0)
        elif it.item_type == ItemType.DROP_TURNER:
            base["fall_time"] = it.properties.get("fall_time", 0.5)
        elif it.item_type == ItemType.MOVER:
            base["distance"] = it.properties.get("distance", 3.0)
            base["speed"] = it.properties.get("speed", 1.5)

        return base

    @Property(list, notify=objectsChanged)
    def objects(self) -> List[Dict[str, Any]]:
        return self._objects


class Quick3DWidget(QQuickWidget):
    """Wrapper QQuickWidget per il viewer 3D."""
    def __init__(self, stage: Stage, parent=None):
        super().__init__(parent)
        self._stage = stage
        self._model = Stage3DModel(stage, self)

        # Esponi contesto
        ctx = self.rootContext()
        ctx.setContextProperty("stage3dModel", self._model)
        ctx.setContextProperty("stageWidth", stage.width)
        ctx.setContextProperty("stageDepth", stage.depth)

        # Path texture per QML
        tex_uris = {
            "floor_concrete": _tex("floor_concrete.png"),
            "wall_drywall": _tex("wall_drywall.png"),
            "backstop_earth": _tex("backstop_earth.png"),
            "target_ipsc": _tex("target_ipsc.png"),
            "steel_metal": _tex("steel_metal.png"),
            "wood_planks": _tex("wood_planks.png"),
            "hard_cover": _tex("hard_cover.png"),
            "soft_cover": _tex("soft_cover.png"),
            "wood_porte": _tex("wood_porte.png"),
        }
        for k, v in tex_uris.items():
            ctx.setContextProperty(f"tex_{k}", v)

        qml_file = Path(__file__).with_name("StageScene.qml")
        self.setSource(QUrl.fromLocalFile(str(qml_file)))
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)

    def refresh(self):
        self._model.rebuild()

    def update_dimensions(self, width: float, depth: float):
        """Aggiorna le dimensioni dello stage nel contesto 3D."""
        ctx = self.rootContext()
        ctx.setContextProperty("stageWidth", width)
        ctx.setContextProperty("stageDepth", depth)
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
