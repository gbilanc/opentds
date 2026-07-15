"""
Esportazione professionale dello stage in PNG e PDF multi-pagina.

PDF strutturato:
  1. Copertina con riepilogo
  2. Piantina 2D con griglia e legenda
  3. Lista bersagli completa
  4. Bersagli mobili (parametri)
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QImage, QPainter, QColor, QFont, QPdfWriter, QPageSize,
    QPen, QBrush,
)
from PySide6.QtWidgets import QGraphicsScene

from core.models import Stage, StageItem, ItemType


# ── Mappa colore per tipo ────────────────────────────────────────────────────

TYPE_COLORS: dict[ItemType, str] = {
    ItemType.WALL: "#475569",
    ItemType.PAPER_TARGET: "#8B4513",      # IPSC marrone (Regola 4.1.2.1)
    ItemType.STEEL_TARGET: "#d1d5db",      # IPSC bianco/grigio (Regola 4.1.2.2)
    ItemType.POPPER: "#d1d5db",            # IPSC bianco (App. C1-C2)
    ItemType.METAL_PLATE: "#d1d5db",       # IPSC bianco (App. C3)
    ItemType.MINI_TARGET: "#8B4513",       # IPSC marrone ridotto (App. B3)
    ItemType.MICRO_TARGET: "#8B4513",      # IPSC marrone micro
    ItemType.FAULT_LINE: "#dc2626",        # IPSC rosso (Regola 2.2.1.4)
    ItemType.NO_SHOOT: "#eab308",          # IPSC colore diverso (Regola 4.1.3)
    ItemType.BARRIER: "#fbbf24",
    ItemType.DOOR: "#92400e",
    ItemType.HARD_COVER: "#1e293b",        # Copertura impenetrabile
    ItemType.SOFT_COVER: "#94a3b8",        # Copertura visiva
    ItemType.SWINGER: "#A0522D",           # Bersaglio cartaceo mobile → marrone
    ItemType.DROP_TURNER: "#8B6914",        # Bersaglio cartaceo mobile → marrone
    ItemType.MOVER: "#CD853F",              # Bersaglio cartaceo mobile → marrone
}

TYPE_LABELS: dict[ItemType, str] = {
    ItemType.WALL: "Muro",
    ItemType.PAPER_TARGET: "Bersaglio cartaceo",
    ItemType.STEEL_TARGET: "Bersaglio metallico",
    ItemType.POPPER: "Popper calibrato",
    ItemType.METAL_PLATE: "Piatto metallico",
    ItemType.MINI_TARGET: "Mini target",
    ItemType.MICRO_TARGET: "Micro target",
    ItemType.FAULT_LINE: "Fault line",
    ItemType.NO_SHOOT: "No-shoot",
    ItemType.BARRIER: "Barriera",
    ItemType.DOOR: "Porta",
    ItemType.HARD_COVER: "Hard cover",
    ItemType.SOFT_COVER: "Soft cover",
    ItemType.SWINGER: "Swinger",
    ItemType.DROP_TURNER: "Drop turner",
    ItemType.MOVER: "Mover",
}


# Colori per i nuovi tipi (se non presenti in TYPE_COLORS)
TYPE_COLORS[ItemType.MINI_TARGET] = "#A0522D"
TYPE_COLORS[ItemType.MICRO_TARGET] = "#8B4513"


# ── Helper per briefing ───────────────────────────────────────────────────────


def _format_target_list(stage: Stage) -> str:
    """Formatta l'elenco bersagli per il briefing."""
    counts = {}
    for it in stage.items:
        label = TYPE_LABELS.get(it.item_type, it.label or it.item_type.name)
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "Nessun bersaglio"
    return ", ".join(f"{n}×{t}" for t, n in sorted(counts.items()))


def _count_total_rounds(stage: Stage) -> int:
    """Calcola il numero di colpi richiesti (default: 2 per carta, 1 per metallo)."""
    total = 0
    for it in stage.items:
        if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET,
                            ItemType.MICRO_TARGET, ItemType.SWINGER,
                            ItemType.DROP_TURNER, ItemType.MOVER):
            total += 2
        elif it.item_type in (ItemType.STEEL_TARGET, ItemType.POPPER,
                              ItemType.METAL_PLATE):
            total += 1
    return total


def _format_ready_condition(stage: Stage) -> str:
    """Descrive la condizione di pronto dell'arma."""
    return "Arma carica in fondina"  # default IPSC


def _format_start_position(stage: Stage) -> str:
    """Descrive la posizione di partenza."""
    if stage.properties.get("start_position"):
        return stage.properties["start_position"]
    for sp in stage.shooting_positions:
        if sp.is_start:
            return f"({sp.x:.1f}, {sp.y:.1f}) — {sp.label or 'Start'}"
    return "Area di tiro designata"


def _format_procedure(stage: Stage) -> str:
    """Genera la procedura del briefing."""
    if stage.properties.get("procedure"):
        return stage.properties["procedure"]
    parts = ["Al segnale di avvio, ingaggiare tutti i bersagli."]
    if stage.course_type:
        parts.append(f"Corso: {stage.course_type.value.title()}.")
    moving = [it for it in stage.items
              if it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER,
                                  ItemType.MOVER)]
    if moving:
        parts.append(f"Attenzione ai {len(moving)} bersagli mobili.")
    return " ".join(parts)


# ── PNG ──────────────────────────────────────────────────────────────────────

def export_png(scene: QGraphicsScene, path: Path, dpi: int = 150) -> None:
    """Esporta la scena 2D in PNG ad alta risoluzione."""
    rect = scene.sceneRect()
    scale = dpi / 96.0
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


# ── Helper di disegno PDF ────────────────────────────────────────────────────

def _draw_header(painter: QPainter, title: str, margin: int, page_w: int):
    """Disegna l'intestazione di pagina con linea separatrice."""
    painter.save()
    painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
    painter.setPen(QColor("#0f172a"))
    painter.drawText(margin, margin + 16, title)

    painter.setPen(QPen(QColor("#2563eb"), 2))
    painter.drawLine(margin, margin + 28, page_w - margin, margin + 28)
    painter.setFont(QFont("Segoe UI", 10))
    painter.restore()


def _draw_footer(painter: QPainter, page: int, margin: int, page_w: int, page_h: int):
    """Disegna il piè di pagina con numero."""
    painter.save()
    painter.setFont(QFont("Segoe UI", 8))
    painter.setPen(QColor("#94a3b8"))
    painter.drawText(margin, page_h - 10, f"OpenTDS — Pagina {page}")
    painter.drawText(page_w - margin - 60, page_h - 10, "opentds.dev")
    painter.restore()


def _draw_info_box(painter: QPainter, stage: Stage, x: int, y: int,
                   width: int, violations: Optional[List[str]] = None):
    """Disegna un box riepilogativo con dimensioni, conteggi e violazioni."""
    margin_box = 8
    painter.save()

    # Sfondo
    painter.setBrush(QBrush(QColor("#f8fafc")))
    painter.setPen(QPen(QColor("#e2e8f0"), 1))
    painter.drawRoundedRect(x, y, width, 1, 6, 6)

    # Calcola altezza box
    targets = [it for it in stage.items
               if it.item_type in (ItemType.PAPER_TARGET, ItemType.STEEL_TARGET)]
    steel = [it for it in stage.items if it.item_type == ItemType.STEEL_TARGET]
    moving = [it for it in stage.items if it.item_type in (
        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
    total_items = len(stage.items)
    violations = violations or []
    line_h = 18
    box_h = 220 + len(violations) * line_h

    painter.setBrush(QBrush(QColor("#f8fafc")))
    painter.setPen(QPen(QColor("#e2e8f0"), 1))
    painter.drawRoundedRect(x, y, width, box_h, 6, 6)

    cx = x + margin_box
    cy = y + margin_box + 4
    painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
    painter.setPen(QColor("#0f172a"))
    painter.drawText(cx, cy, "Riepilogo Stage")
    cy += line_h + 4

    lines = [
        (f"Nome:", f"{stage.name}"),
        (f"Dimensioni:", f"{stage.width:.1f} × {stage.depth:.1f} m"),
        (f"Area:", f"{stage.width * stage.depth:.0f} m²"),
        (f"Oggetti totali:", f"{total_items}"),
        (f"Bersagli totali:", f"{len(targets)}"),
        (f"  - Cartacei:", f"{len(targets) - len(steel)}"),
        (f"  - Metallici:", f"{len(steel)}"),
        (f"  - Mobili:", f"{len(moving)}"),
    ]

    painter.setFont(QFont("Segoe UI", 10))
    for label, value in lines:
        painter.setPen(QColor("#64748b"))
        painter.drawText(cx, cy, label)
        painter.setPen(QColor("#0f172a"))
        painter.drawText(cx + 130, cy, value)
        cy += line_h

    # Violazioni
    if violations:
        cy += 4
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor("#dc2626"))
        painter.drawText(cx, cy, "Violazioni:")
        cy += line_h
        painter.setFont(QFont("Segoe UI", 9))
        for v in violations[:6]:  # max 6 violazioni nel box
            painter.setPen(QColor("#dc2626"))
            painter.drawText(cx + 8, cy, f"• {v}")
            cy += line_h

    painter.restore()


def _draw_legend(painter: QPainter, x: int, y: int, width: int, items: List[ItemType]):
    """Disegna la legenda dei colori in fondo alla piantina."""
    painter.save()
    painter.setFont(QFont("Segoe UI", 9))
    col_w = width // 3
    row_h = 22
    ry = y

    for i, it_type in enumerate(ItemType):
        col = i // 5  # 5 tipi per colonna
        row = i % 5
        lx = x + col * col_w + 8
        ly = ry + row * row_h

        color = QColor(TYPE_COLORS.get(it_type, "#808080"))
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        painter.drawRect(lx, ly - 12, 14, 14)

        painter.setPen(QColor("#0f172a"))
        painter.drawText(lx + 20, ly, TYPE_LABELS.get(it_type, it_type.name))

    painter.restore()


# ── PDF ──────────────────────────────────────────────────────────────────────

def export_pdf(stage: Stage, scene: QGraphicsScene, path: Path,
               violations: Optional[List[str]] = None) -> None:
    """Esporta un PDF multi-pagina professionale."""
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize.PageSizeId.A4)
    writer.setResolution(150)

    painter = QPainter(writer)
    margin = 40
    page_w = writer.width()
    page_h = writer.height()
    usable_w = page_w - margin * 2
    usable_h = page_h - margin * 2 - 40  # spazio per header/footer
    page_num = 0

    def _new_page():
        nonlocal page_num
        page_num += 1
        if page_num > 1:
            writer.newPage()
        _draw_footer(painter, page_num, margin, page_w, page_h)

    # ═══════════════════════════════════════════════════════════════════════
    # Pagina 1 — Piantina 2D
    # ═══════════════════════════════════════════════════════════════════════
    _new_page()
    _draw_header(painter, f"Stage: {stage.name}", margin, page_w)

    # Info box (a destra della piantina)
    info_width = 240
    _draw_info_box(painter, stage, page_w - margin - info_width,
                   margin + 40, info_width, violations)

    # Piantina
    rect = scene.sceneRect()
    map_w = usable_w - info_width - 20
    map_h = usable_h
    scale = min(map_w / rect.width(), map_h / rect.height())
    painter.save()
    painter.scale(scale, scale)
    offset_x = margin / scale + 10 / scale
    offset_y = (margin + 40) / scale
    painter.translate(offset_x, offset_y)
    scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
    painter.restore()

    # Legenda in fondo alla piantina
    legend_y = margin + map_h - 60
    _draw_legend(painter, margin, legend_y, usable_w, list(ItemType))

    # ═══════════════════════════════════════════════════════════════════════
    # Pagina 2 — Briefing (Reg. IPSC Sez. 3.2)
    # ═══════════════════════════════════════════════════════════════════════
    _new_page()
    _draw_header(painter, f"Briefing — {stage.name}", margin, page_w)
    y = margin + 50

    briefing_items = [
        ("Bersagli", _format_target_list(stage)),
        ("Colpi conteggiabili", str(_count_total_rounds(stage))),
        ("Punti massimi", str(stage.properties.get("max_points", "—"))),
        ("Condizione di pronto", _format_ready_condition(stage)),
        ("Posizione di partenza", _format_start_position(stage)),
        ("Procedura", _format_procedure(stage)),
        ("Tipo corso", stage.course_type.value if stage.course_type else "Non specificato"),
        ("Divisione", stage.division.value if stage.division else "Tutte"),
        ("Segnale di partenza", stage.properties.get("start_signal", "Acustico")),
        ("Angoli di sicurezza", stage.properties.get("angoli_sicurezza", "90°")),
        ("Coperture", stage.properties.get("hard_cover", "Hard cover")),
        ("Distanza minima metallici", "7 m"),
        ("Note", stage.properties.get("note", "")),
    ]

    painter.setFont(QFont("Segoe UI", 9))
    for label, value in briefing_items:
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#0f172a"))
        painter.drawText(margin, y, label)
        y += 18
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#475569"))
        painter.drawText(margin + 16, y, value)
        y += 28
        if y > page_h - margin - 30:
            _new_page()
            _draw_header(painter, f"Briefing (cont.) — {stage.name}", margin, page_w)
            y = margin + 50

    # ═══════════════════════════════════════════════════════════════════════
    # Pagina 3 — Lista bersagli
    # ═══════════════════════════════════════════════════════════════════════
    _new_page()
    _draw_header(painter, f"Lista bersagli — {stage.name}", margin, page_w)

    # Tabella header
    y = margin + 50
    cols = [
        (margin, 40, "ID"),
        (margin + 45, 170, "Tipo"),
        (margin + 220, 120, "Nome"),
        (margin + 345, 140, "Posizione (m)"),
        (margin + 490, 70, "Rotazione"),
        (margin + 565, 100, "Dimensioni"),
    ]

    painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
    for cx, cw, label in cols:
        painter.drawText(cx, y, label)
    painter.setPen(QPen(QColor("#2563eb"), 1))
    painter.drawLine(margin, y + 4, page_w - margin, y + 4)
    y += 20

    painter.setFont(QFont("Segoe UI", 9))
    for it in stage.items:
        # Colore riga alternato
        if stage.items.index(it) % 2 == 0:
            painter.save()
            painter.setBrush(QBrush(QColor("#f8fafc")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(margin, y - 12, usable_w, 18)
            painter.restore()

        for cx, cw, _ in cols:
            painter.setPen(QColor("#0f172a"))
            if cx == margin:  # ID
                painter.drawText(cx, y, str(it.id))
            elif cx == margin + 45:  # Tipo
                painter.setPen(QColor(TYPE_COLORS.get(it.item_type, "#808080")))
                painter.drawText(cx, y, TYPE_LABELS.get(it.item_type, "—"))
            elif cx == margin + 220:  # Nome
                painter.setPen(QColor("#64748b"))
                painter.drawText(cx, y, it.label or "—")
            elif cx == margin + 345:  # Posizione
                painter.setPen(QColor("#0f172a"))
                painter.drawText(cx, y, f"({it.x:.2f}, {it.y:.2f})")
            elif cx == margin + 490:  # Rotazione
                painter.setPen(QColor("#0f172a"))
                painter.drawText(cx, y, f"{it.rotation:.1f}°")
            elif cx == margin + 565:  # Dimensioni
                painter.setPen(QColor("#64748b"))
                painter.drawText(cx, y, f"{it.width:.2f}×{it.height:.2f}")

        y += 18
        if y > page_h - margin - 30:
            _new_page()
            _draw_header(painter, f"Lista bersagli (cont.) — {stage.name}", margin, page_w)
            y = margin + 50

    # ═══════════════════════════════════════════════════════════════════════
    # Pagina 3 — Bersagli mobili (se presenti)
    # ═══════════════════════════════════════════════════════════════════════
    moving = [it for it in stage.items if it.item_type in (
        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)]
    if moving:
        _new_page()
        _draw_header(painter, f"Bersagli mobili — {stage.name}", margin, page_w)

        y = margin + 50
        for it in moving:
            # Box per ogni bersaglio mobile
            box_h = 50 + len(it.properties) * 16
            painter.save()
            painter.setBrush(QBrush(QColor("#f8fafc")))
            painter.setPen(QPen(QColor("#e2e8f0"), 1))
            painter.drawRoundedRect(margin, y - 8, usable_w, box_h, 4, 4)
            painter.restore()

            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.setPen(QColor(TYPE_COLORS.get(it.item_type, "#808080")))
            painter.drawText(margin + 12, y + 4, f"#{it.id} — {it.label}")
            y += 22

            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(QColor("#64748b"))
            for k, v in it.properties.items():
                painter.drawText(margin + 24, y, f"{k}: {v}")
                y += 16

            y += 14
            if y > page_h - margin - 30:
                _new_page()
                _draw_header(painter, f"Bersagli mobili (cont.)", margin, page_w)
                y = margin + 50

    # ═══════════════════════════════════════════════════════════════════════
    # Pagina 4 — Posizioni di tiro (se presenti)
    # ═══════════════════════════════════════════════════════════════════════
    if stage.shooting_positions:
        _new_page()
        _draw_header(painter, f"Posizioni di tiro — {stage.name}", margin, page_w)
        y = margin + 50
        for sp in stage.shooting_positions:
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.setPen(QColor("#0f172a"))
            painter.drawText(margin, y, f"#{sp.id}: {sp.label or 'Posizione'}")
            y += 20
            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(QColor("#475569"))
            painter.drawText(margin + 16, y, f"Coordinate: ({sp.x:.2f}, {sp.y:.2f})")
            y += 16
            painter.drawText(margin + 16, y, f"Partenza: {'Sì' if sp.is_start else 'No'}")
            y += 16
            if sp.angle:
                painter.drawText(margin + 16, y, f"Direzione: {sp.angle:.0f}°")
                y += 16
            y += 16
            if y > page_h - margin - 30:
                _new_page()
                _draw_header(painter, f"Posizioni di tiro (cont.)", margin, page_w)
                y = margin + 50

    # ═══════════════════════════════════════════════════════════════════════
    # Pagina 4 — Attivatori (se presenti)
    # ═══════════════════════════════════════════════════════════════════════
    activators = [it for it in stage.items
                  if it.item_type in (ItemType.POPPER, ItemType.METAL_PLATE)
                  and it.properties.get("activates")]
    if activators:
        _new_page()
        _draw_header(painter, f"Attivatori — {stage.name}", margin, page_w)
        y = margin + 50

        for a in activators:
            targets_ids = a.properties["activates"]
            target_labels = []
            for tid in targets_ids:
                t = next((it for it in stage.items if it.id == tid), None)
                target_labels.append(t.label if t else f"T{tid}")

            # Box per ogni attivatore
            box_h = 60
            painter.save()
            painter.setBrush(QBrush(QColor("#fef2f2")))
            painter.setPen(QPen(QColor("#fecaca"), 1))
            painter.drawRoundedRect(margin, y - 8, usable_w, box_h, 4, 4)
            painter.restore()

            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.setPen(QColor("#dc2626"))
            painter.drawText(margin + 12, y + 4, f"{a.label} — {a.item_type.name}")
            y += 22

            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(QColor("#475569"))
            painter.drawText(margin + 24, y, f"Attiva: {", ".join(target_labels)}")
            y += 16
            painter.drawText(margin + 24, y, f"Posizione: ({a.x:.2f}, {a.y:.2f})")
            y += 16
            if a.properties.get("calibrated"):
                pf = a.properties.get("calibration_pf", 125)
                painter.drawText(margin + 24, y, f"Calibrato: PF {pf}")
                y += 16

            y += 16
            if y > page_h - margin - 30:
                _new_page()
                _draw_header(painter, f"Attivatori (cont.)", margin, page_w)
                y = margin + 50

    painter.end()
