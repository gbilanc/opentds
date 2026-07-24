# ui/editor/target_images.py
"""Gestore SVG vettoriale dei bersagli IPSC.

Carica, colora (tinta) e cachea i rendering SVG dei bersagli IPSC
per usarli nell'editor 2D. Usa QSvgRenderer per un rendering
vettoriale nitido a qualsiasi risoluzione.

I file SVG usano fill="currentColor" per ricevere la tinta
tramite compositing QPainter (SourceIn), preservando il canale alpha.
"""
from __future__ import annotations
import os
from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QImage, QColor, QPainter
from PySide6.QtSvg import QSvgRenderer

from core.models import ItemType
from core.constants import TARGET_COLORS


class TargetSvgManager:
    """Carica e cachea i rendering SVG dei bersagli IPSC.

    Fornisce pixmap tinti (colorati) per ogni ItemType, scalabili
    alle dimensioni desiderate usando rendering vettoriale.
    """

    _instance: Optional["TargetSvgManager"] = None

    # Percorsi SVG per ogni tipo bersaglio (relativi a resources/)
    _SVG_MAP: dict[ItemType, str] = {
        ItemType.PAPER_TARGET:  "targets/ipsc_target.svg",
        ItemType.MINI_TARGET:   "targets/ipsc_target.svg",
        ItemType.MICRO_TARGET:  "targets/ipsc_target.svg",
        ItemType.STEEL_TARGET:  "targets/ipsc_popper.svg",
        ItemType.POPPER:        "targets/ipsc_popper.svg",
        ItemType.METAL_PLATE:   "targets/ipsc_metal_plate.svg",
        ItemType.SWINGER:       "targets/ipsc_target.svg",
        ItemType.DROP_TURNER:   "targets/ipsc_target.svg",
        ItemType.MOVER:         "targets/ipsc_target.svg",
        ItemType.NO_SHOOT:      "targets/ipsc_no_shoot.svg",
    }

    def __init__(self) -> None:
        self._renderers: dict[ItemType, QSvgRenderer] = {}
        self._cache: dict[tuple[ItemType, int, int], QPixmap] = {}
        self._resources_dir = self._find_resources_dir()
        # Colori modificabili a runtime (inizializzati dai default IPSC)
        self._colors: dict[ItemType, QColor] = {}
        self.reset_to_defaults()

    @classmethod
    def instance(cls) -> "TargetSvgManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Forza il ricaricamento (utile dopo cambio configurazione colori)."""
        cls._instance = None

    @staticmethod
    def _find_resources_dir() -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(os.path.dirname(here))
        res = os.path.join(root, "resources")
        if os.path.isdir(res):
            return res
        return os.path.join(os.getcwd(), "resources")

    # ── Color access ──────────────────────────────────────────────────────

    def get_color(self, item_type: ItemType) -> QColor:
        """Restituisce il colore configurato per un tipo bersaglio."""
        return self._colors.get(item_type, QColor("#808080"))

    def set_color(self, item_type: ItemType, color: QColor) -> None:
        """Imposta un nuovo colore per un tipo bersaglio e invalida la cache."""
        self._colors[item_type] = color
        # Invalida solo le entry per questo tipo
        keys_to_del = [k for k in self._cache if k[0] == item_type]
        for k in keys_to_del:
            del self._cache[k]

    def get_all_colors(self) -> dict[ItemType, QColor]:
        """Restituisce la mappa completa dei colori configurati."""
        return dict(self._colors)

    def reset_to_defaults(self) -> None:
        """Ripristina i colori IPSC predefiniti da constants.py."""
        _color_map: dict[ItemType, str] = {
            ItemType.PAPER_TARGET: "paper",
            ItemType.MINI_TARGET: "mini",
            ItemType.MICRO_TARGET: "micro",
            ItemType.STEEL_TARGET: "steel_generic",
            ItemType.POPPER: "popper",
            ItemType.METAL_PLATE: "metal_plate",
            ItemType.SWINGER: "swinger",
            ItemType.DROP_TURNER: "drop_turner",
            ItemType.MOVER: "mover",
            ItemType.NO_SHOOT: "no_shoot",
        }
        for itype, key in _color_map.items():
            hex_color = TARGET_COLORS.get(key, "#808080")
            self._colors[itype] = QColor(hex_color)
        self._cache.clear()

    # ── Caricamento SVG ───────────────────────────────────────────────────

    def _get_renderer(self, item_type: ItemType) -> QSvgRenderer | None:
        """Carica e cachea il QSvgRenderer per un tipo bersaglio."""
        if item_type in self._renderers:
            return self._renderers[item_type]

        rel_path = self._SVG_MAP.get(item_type)
        if not rel_path:
            return None

        full_path = os.path.join(self._resources_dir, rel_path)
        if not os.path.isfile(full_path):
            return None

        renderer = QSvgRenderer(full_path)
        if not renderer.isValid():
            return None

        self._renderers[item_type] = renderer
        return renderer

    # ── API pubblica ──────────────────────────────────────────────────────

    def get_pixmap(
        self, item_type: ItemType,
        target_width: int, target_height: int,
    ) -> QPixmap | None:
        """Restituisce un QPixmap vettoriale tintato e scalato.

        Args:
            item_type: Tipo di bersaglio (ItemType)
            target_width: Larghezza desiderata in pixel
            target_height: Altezza desiderata in pixel

        Returns:
            QPixmap scalato e colorato, oppure None se SVG non disponibile.
        """
        if target_width <= 0 or target_height <= 0:
            return None

        cache_key = (item_type, target_width, target_height)
        if cache_key in self._cache:
            return self._cache[cache_key]

        renderer = self._get_renderer(item_type)
        if renderer is None:
            return None

        # Renderizza SVG su QImage trasparente, poi applica tinta
        image = QImage(
            target_width, target_height,
            QImage.Format_ARGB32,
        )
        image.fill(Qt.GlobalColor.transparent)

        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, target_width, target_height))
        painter.end()

        # Applica tinta colore via compositing SourceIn
        tint_color = self._colors.get(item_type)
        if tint_color is not None:
            tint_painter = QPainter(image)
            tint_painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn,
            )
            tint_painter.fillRect(image.rect(), tint_color)
            tint_painter.end()

        pixmap = QPixmap.fromImage(image)
        self._cache[cache_key] = pixmap
        return pixmap

    def get_default_color_hex(self, item_type: ItemType) -> str:
        """Restituisce il colore predefinito come hex string."""
        return self._colors.get(item_type, QColor("#808080")).name()

    def has_svg_for(self, item_type: ItemType) -> bool:
        """Verifica se esiste un SVG per questo ItemType."""
        return item_type in self._SVG_MAP
