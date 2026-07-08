# services/exporter.py
"""Esportazione immagini e PDF dello stage."""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPdfWriter, QPageSize
from PySide6.QtWidgets import QGraphicsScene

from core.models import Stage, StageItem, ItemType
from services.serializer import stage_to_dict


def export_png(scene: QGraphicsScene, path: Path, dpi: int = 150) -> None:
    """Esporta la scena 2D in PNG ad alta risoluzione."""
    rect = scene.sceneRect()
    scale = dpi / 96.0  # base 96 DPI
    img_w = int(rect.width() * scale)
    img_h = int(rect.height() * scale)
    image = QImage(img_w, img_h, QImage.Format.Format_ARGB32)
    image.fill(QColor("#ffffff"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale, scale)
    scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
    painter.end()
    image.save(str(path))


def export_pdf(stage: Stage, scene: QGraphicsScene, path: Path) -> None:
    """Esporta un PDF multi-pagina: piantina + lista bersagli."""
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize.PageSizeId.A4)
    writer.setResolution(150)

    painter = QPainter(writer)
    margin = 40
    page_w = writer.width()
    page_h = writer.height()

    def _draw_header(title: str):
        painter.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        painter.drawText(margin, margin, title)
        painter.drawLine(margin, margin + 10, page_w - margin, margin + 10)
        painter.setFont(QFont("Segoe UI", 10))

    # Pagina 1: Piantina
    _draw_header(f"Stage: {stage.name}")
    rect = scene.sceneRect()
    avail_w = page_w - margin * 2
    avail_h = page_h - margin * 2 - 60
    scale = min(avail_w / rect.width(), avail_h / rect.height())
    painter.scale(scale, scale)
    offset_x = margin / scale + (avail_w / scale - rect.width()) / 2
    offset_y = (margin + 60) / scale + (avail_h / scale - rect.height()) / 2
    painter.translate(offset_x, offset_y)
    scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
    painter.resetTransform()

    # Pagina 2: Lista bersagli
    writer.newPage()
    _draw_header(f"Lista bersagli — {stage.name}")
    y = margin + 40
    painter.setFont(QFont("Segoe UI", 10))
    painter.drawText(margin, y, "ID")
    painter.drawText(margin + 60, y, "Tipo")
    painter.drawText(margin + 200, y, "Nome")
    painter.drawText(margin + 360, y, "Posizione (m)")
    painter.drawText(margin + 520, y, "Rotazione")
    y += 20
    painter.drawLine(margin, y, page_w - margin, y)
    y += 15

    for it in stage.items:
        painter.drawText(margin, y, str(it.id))
        painter.drawText(margin + 60, y, it.item_type.name.replace("_", " "))
        painter.drawText(margin + 200, y, it.label or "—")
        painter.drawText(margin + 360, y, f"({it.x:.2f}, {it.y:.2f})")
        painter.drawText(margin + 520, y, f"{it.rotation:.1f}°")
        y += 20
        if y > page_h - margin:
            writer.newPage()
            _draw_header(f"Lista bersagli (cont.) — {stage.name}")
            y = margin + 40

    # Pagina 3: Proprietà mobili (se presenti)
    moving = [it for it in stage.items if it.item_type in (
        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
    if moving:
        writer.newPage()
        _draw_header(f"Bersagli mobili — {stage.name}")
        y = margin + 40
        for it in moving:
            painter.drawText(margin, y, f"#{it.id} {it.label}")
            y += 18
            for k, v in it.properties.items():
                painter.drawText(margin + 20, y, f"  {k}: {v}")
                y += 16
            y += 10
            if y > page_h - margin:
                writer.newPage()
                _draw_header(f"Bersagli mobili (cont.)")
                y = margin + 40

    painter.end()
