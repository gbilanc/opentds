# ui/editor/target_images.py
"""Gestore delle immagini dei bersagli IPSC estratte dal Regolamento.

Carica, colora (tinta) e cachea le immagini PNG dei bersagli IPSC
per usarle nell'editor 2D al posto di shape geometrici.
"""
from __future__ import annotations
import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QImage, QColor, QPainter

from core.models import ItemType


class TargetImageManager:
    """Carica e cachea i pixmap dei bersagli IPSC.

    Fornisce pixmap tinti (colorati) per ogni ItemType, scalabili
    alle dimensioni desiderate.
    """
    _instance: Optional["TargetImageManager"] = None

    # Percorsi delle immagini sorgente (rispetto alla directory resources/)
    _SOURCE_MAP: dict[ItemType, str] = {
        ItemType.PAPER_TARGET:  "targets/ipsc_target_clean.png",
        ItemType.MINI_TARGET:   "targets/ipsc_mini_target_clean.png",
        ItemType.MICRO_TARGET:  "targets/ipsc_mini_target_clean.png",
        ItemType.STEEL_TARGET:  "targets/ipsc_popper_clean.png",
        ItemType.POPPER:        "targets/ipsc_popper_clean.png",
        ItemType.METAL_PLATE:   "targets/ipsc_metal_plates_clean.png",
        ItemType.SWINGER:       "targets/ipsc_target_clean.png",
        ItemType.DROP_TURNER:   "targets/ipsc_target_clean.png",
        ItemType.MOVER:         "targets/ipsc_target_clean.png",
        ItemType.NO_SHOOT:      "targets/ipsc_target_clean.png",
    }

    # Colori IPSC per tinta (Regola 4.1.2)
    _TINT_COLORS: dict[ItemType, QColor] = {
        ItemType.PAPER_TARGET:  QColor("#8B4513"),   # Marrone IPSC
        ItemType.MINI_TARGET:   QColor("#8B4513"),   # Marrone IPSC
        ItemType.MICRO_TARGET:  QColor("#8B4513"),   # Marrone IPSC
        ItemType.STEEL_TARGET:  QColor("#d1d5db"),   # Grigio chiaro
        ItemType.POPPER:        QColor("#d1d5db"),   # Grigio chiaro
        ItemType.METAL_PLATE:   QColor("#d1d5db"),   # Grigio chiaro
        ItemType.SWINGER:       QColor("#A0522D"),   # Marrone scuro mobile
        ItemType.DROP_TURNER:   QColor("#8B6914"),   # Marrone scuro mobile
        ItemType.MOVER:         QColor("#CD853F"),   # Marrone chiaro mobile
        ItemType.NO_SHOOT:      QColor("#eab308"),   # Giallo IPSC
    }

    def __init__(self):
        self._loaded: dict[ItemType, QImage] = {}
        self._tinted: dict[tuple[ItemType, int, int], QPixmap] = {}
        self._resources_dir = self._find_resources_dir()

    @classmethod
    def instance(cls) -> "TargetImageManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _find_resources_dir() -> str:
        """Trova la directory resources/ partendo dalla posizione di questo file."""
        # Partiamo da ui/editor/target_images.py → risaliamo fino alla radice
        here = os.path.dirname(os.path.abspath(__file__))
        # ui/editor/ → ui/ → radice
        root = os.path.dirname(os.path.dirname(here))
        res = os.path.join(root, "resources")
        if os.path.isdir(res):
            return res
        # Fallback: cwd
        return os.path.join(os.getcwd(), "resources")

    # ── Caricamento immagini ──────────────────────────────────────────────

    def _load_source(self, item_type: ItemType) -> Optional[QImage]:
        """Carica l'immagine sorgente per un ItemType, una sola volta."""
        if item_type in self._loaded:
            return self._loaded[item_type]

        rel_path = self._SOURCE_MAP.get(item_type)
        if not rel_path:
            return None

        full_path = os.path.join(self._resources_dir, rel_path)
        if not os.path.isfile(full_path):
            print(f"[TargetImageManager] Immagine non trovata: {full_path}")
            return None

        img = QImage(full_path)
        if img.isNull():
            print(f"[TargetImageManager] Errore caricamento: {full_path}")
            return None

        self._loaded[item_type] = img
        return img

    def _load_source_name(self, name: str) -> Optional[QImage]:
        """Carica un'immagine per nome file (senza ItemType)."""
        full_path = os.path.join(self._resources_dir, "targets", name)
        if not os.path.isfile(full_path):
            return None
        img = QImage(full_path)
        return img if not img.isNull() else None

    # ── Tinta (colorazione) ───────────────────────────────────────────────

    def _apply_tint(self, image: QImage, color: QColor) -> QImage:
        """Applica una tinta veloce usando QPainter compositing.

        Usa CompositionMode_SourceIn per riempire le aree non trasparenti
        con il colore di tinta, preservando il canale alpha.
        Per le miniature nell'editor (≤50px) il risultato è eccellente.
        """
        result = image.convertToFormat(QImage.Format_ARGB32)
        painter = QPainter(result)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(result.rect(), color)
        painter.end()
        return result

    # ── API pubblica ──────────────────────────────────────────────────────

    def get_pixmap(self, item_type: ItemType,
                   target_width: int, target_height: int) -> Optional[QPixmap]:
        """Restituisce un QPixmap tintato e scalato per il tipo di bersaglio.

        Args:
            item_type: Tipo di bersaglio (ItemType)
            target_width: Larghezza desiderata in pixel
            target_height: Altezza desiderata in pixel

        Returns:
            QPixmap scalato e colorato, oppure None se non disponibile.
        """
        if target_width <= 0 or target_height <= 0:
            return None

        # Cache chiave: (tipo, larghezza, altezza)
        cache_key = (item_type, target_width, target_height)
        if cache_key in self._tinted:
            return self._tinted[cache_key]

        # Carica sorgente
        source = self._load_source(item_type)
        if source is None:
            return None

        # Applica tinta
        tint_color = self._TINT_COLORS.get(item_type)
        if tint_color:
            tinted = self._apply_tint(source, tint_color)
        else:
            tinted = source.copy()

        # Scala
        scaled = tinted.scaled(target_width, target_height,
                               Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)

        pixmap = QPixmap.fromImage(scaled)
        self._tinted[cache_key] = pixmap
        return pixmap

    def has_image_for(self, item_type: ItemType) -> bool:
        """Verifica se esiste un'immagine per questo ItemType."""
        return item_type in self._SOURCE_MAP
