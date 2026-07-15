"""
Generatore di texture procedurali per il viewer 3D.

Usa QImage + QPainter per creare texture PNG realistiche
(cemento, legno, metallo, terra, sagoma IPSC) senza
dipendenze esterne.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF, QBrush, QFont

TEXTURES_DIR: Final[Path] = Path(__file__).parent.parent / "assets" / "textures"

# ── Palette colori ──────────────────────────────────────────────
_CONCRETE_BASE = QColor("#6b7280")
_CONCRETE_LIGHT = QColor("#9ca3af")
_CONCRETE_DARK = QColor("#4b5563")

_WOOD_BASE = QColor("#a16207")
_WOOD_LIGHT = QColor("#ca8a04")
_WOOD_DARK = QColor("#713f12")

_METAL_BASE = QColor("#9ca3af")
_METAL_LIGHT = QColor("#d1d5db")
_METAL_DARK = QColor("#6b7280")

_EARTH_BASE = QColor("#5c3a1e")
_EARTH_LIGHT = QColor("#7c4a2e")
_EARTH_DARK = QColor("#3c2210")

_COVER_BASE = QColor("#1e293b")
_COVER_LIGHT = QColor("#334155")

_TARP_BASE = QColor("#4a5d23")
_TARP_LIGHT = QColor("#5c7a2e")

_TARGET_BROWN = QColor("#8B4513")
_TARGET_TAN = QColor("#D2691E")
_TARGET_WHITE = QColor("#f5f5f0")


def _rng_seed(seed: int | None = None) -> random.Random:
    return random.Random(seed if seed is not None else 42)


def _add_noise(
    image: QImage,
    rng: random.Random,
    intensity: int = 16,
    alpha: bool = False,
) -> None:
    """Aggiunge rumore casuale a ogni canale di ogni pixel."""
    w, h = image.width(), image.height()
    for y in range(h):
        for x in range(w):
            c = QColor(image.pixel(x, y))
            dr = rng.randint(-intensity, intensity)
            dg = rng.randint(-intensity, intensity)
            db = rng.randint(-intensity, intensity)
            nr = max(0, min(255, c.red() + dr))
            ng = max(0, min(255, c.green() + dg))
            nb = max(0, min(255, c.blue() + db))
            if alpha:
                image.setPixel(x, y, QColor(nr, ng, nb, c.alpha()).rgba())
            else:
                image.setPixel(x, y, QColor(nr, ng, nb).rgb())


def _draw_vertical_grain(
    image: QImage,
    base: QColor,
    light: QColor,
    dark: QColor,
    rng: random.Random,
    band_width: int = 4,
    noise: int = 8,
) -> None:
    """Disegna grana verticale (venatura legno semplice)."""
    w, h = image.width(), image.height()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    y = 0
    while y < h:
        bh = rng.randint(band_width // 2, band_width * 2)
        t = rng.random()
        if t < 0.3:
            c = light
        elif t < 0.7:
            c = base
        else:
            c = dark
        painter.fillRect(0, y, w, bh, c)
        y += bh
    painter.end()
    _add_noise(image, rng, noise)


def _draw_horizontal_grain(
    image: QImage,
    base: QColor,
    light: QColor,
    dark: QColor,
    rng: random.Random,
    band_width: int = 4,
    noise: int = 8,
) -> None:
    """Disegna grana orizzontale."""
    w, h = image.width(), image.height()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    x = 0
    while x < w:
        bw = rng.randint(band_width // 2, band_width * 2)
        t = rng.random()
        if t < 0.3:
            c = light
        elif t < 0.7:
            c = base
        else:
            c = dark
        painter.fillRect(x, 0, bw, h, c)
        x += bw
    painter.end()
    _add_noise(image, rng, noise)


# ── Texture pubbliche ───────────────────────────────────────────


def generate_floor_concrete(
    size: int = 512,
    seed: int | None = None,
) -> QImage:
    """Texture pavimento cemento industriale."""
    rng = _rng_seed(seed)
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(_CONCRETE_BASE.rgb())

    # Chiazze più chiare e scure
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for _ in range(60):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        radius = rng.randint(8, 40)
        shade = rng.choice([_CONCRETE_LIGHT, _CONCRETE_DARK])
        alpha = rng.randint(20, 60)
        c = QColor(shade.red(), shade.green(), shade.blue(), alpha)
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx, cy, radius, radius)
    painter.end()

    _add_noise(img, rng, 24)

    # Linee di taglio / crepe leggere
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(0, 0, 0, 30), 1)
    painter.setPen(pen)
    for _ in range(8):
        x1 = rng.randint(0, size)
        y1 = rng.randint(0, size)
        x2 = x1 + rng.randint(-60, 60)
        y2 = y1 + rng.randint(-60, 60)
        painter.drawLine(x1, y1, x2, y2)
    painter.end()

    return img


def generate_wall_drywall(
    size: int = 512,
    seed: int | None = None,
) -> QImage:
    """Texture parete cartongesso/gesso."""
    rng = _rng_seed(seed)
    base = QColor("#e2e8f0")
    light = QColor("#f1f5f9")
    dark = QColor("#cbd5e1")

    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(base.rgb())

    _draw_vertical_grain(img, base, light, dark, rng, band_width=6, noise=6)

    # Texture stucco: piccole chiazze irregolari
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for _ in range(120):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        radius = rng.randint(2, 12)
        shade = rng.choice([light, dark])
        c = QColor(shade.red(), shade.green(), shade.blue(), rng.randint(40, 80))
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx, cy, radius, radius)
    painter.end()

    return img


def generate_backstop_earth(
    size: int = 512,
    seed: int | None = None,
) -> QImage:
    """Texture parapalle terra battuta."""
    rng = _rng_seed(seed)
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(_EARTH_BASE.rgb())

    # Stratificazione orizzontale
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    y = 0
    while y < size:
        bh = rng.randint(8, 32)
        t = rng.random()
        if t < 0.25:
            c = _EARTH_DARK
        elif t < 0.75:
            c = _EARTH_BASE
        else:
            c = _EARTH_LIGHT
        painter.fillRect(0, y, size, bh, c)
        y += bh
    painter.end()

    _add_noise(img, rng, 32)

    # Granuli (pietrisco)
    painter = QPainter(img)
    for _ in range(300):
        px = rng.randint(0, size)
        py = rng.randint(0, size)
        shade = rng.choice([_EARTH_LIGHT, _EARTH_DARK, QColor("#2d1810")])
        painter.setPen(QPen(shade, 1))
        painter.drawPoint(px, py)
    painter.end()

    return img


def generate_target_ipsc(
    width: int = 256,
    height: int = 512,
    seed: int | None = None,
) -> QImage:
    """Sagoma bersaglio carta IPSC con zone punteggio.

    Disegna la silhouette caratteristica del bersaglio IPSC
    (torso umano) con la zona A (centrale) visibile.
    """
    rng = _rng_seed(seed)
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(_TARGET_WHITE.rgb())

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Silhouette torso IPSC (poligono approssimato)
    cx = width / 2
    head_r = width * 0.18
    head_y = height * 0.12

    # Testa (cerchio)
    painter.setBrush(QBrush(_TARGET_BROWN))
    painter.setPen(QPen(QColor("#5a2d0c"), 2))
    painter.drawEllipse(int(cx - head_r), int(head_y - head_r), int(head_r * 2), int(head_r * 2))

    # Torso (poligono)
    shoulder_w = width * 0.40
    hip_w = width * 0.32
    neck_y = head_y + head_r * 1.1
    waist_y = height * 0.55
    bottom_y = height * 0.92

    body = QPolygonF([
        QPointF(cx - shoulder_w, neck_y),
        QPointF(cx + shoulder_w, neck_y),
        QPointF(cx + shoulder_w * 0.85, height * 0.30),
        QPointF(cx + hip_w, waist_y),
        QPointF(cx + hip_w * 1.1, height * 0.65),
        QPointF(cx + hip_w * 0.8, bottom_y),
        QPointF(cx - hip_w * 0.8, bottom_y),
        QPointF(cx - hip_w * 1.1, height * 0.65),
        QPointF(cx - hip_w, waist_y),
        QPointF(cx - shoulder_w * 0.85, height * 0.30),
    ])
    painter.setBrush(QBrush(_TARGET_BROWN))
    painter.setPen(QPen(QColor("#5a2d0c"), 2))
    painter.drawPolygon(body)

    # Zona A centrale (area punteggio massimo) — rettangolo
    zone_a_w = width * 0.22
    zone_a_h = height * 0.20
    zone_a_x = cx - zone_a_w / 2
    zone_a_y = height * 0.28
    painter.setBrush(QBrush(_TARGET_TAN))
    painter.setPen(QPen(QColor("#8B4513"), 2))
    painter.drawRoundedRect(
        int(zone_a_x), int(zone_a_y),
        int(zone_a_w), int(zone_a_h),
        4, 4
    )

    # Label "A" nella zona A
    painter.setPen(QPen(QColor("#5a2d0c"), 1))
    font = painter.font()
    font.setPixelSize(14)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        int(zone_a_x), int(zone_a_y),
        int(zone_a_w), int(zone_a_h),
        Qt.AlignmentFlag.AlignCenter,
        "A"
    )

    # Linea divisoria punteggio (orizzontale)
    pen = QPen(QColor("#5a2d0c"), 2)
    painter.setPen(pen)
    line_y = height * 0.60
    painter.drawLine(int(cx - hip_w * 0.7), int(line_y), int(cx + hip_w * 0.7), int(line_y))

    # Label "B/C" sotto linea
    font.setPixelSize(10)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QPen(QColor("#5a2d0c"), 1))
    painter.drawText(
        int(cx - hip_w * 0.7), int(line_y + 2),
        int(hip_w * 1.4), int(height * 0.25),
        Qt.AlignmentFlag.AlignCenter,
        "B / C / D"
    )

    painter.end()

    # Bordo marrone scuro
    painter = QPainter(img)
    painter.setPen(QPen(QColor("#5a2d0c"), 3))
    painter.drawRect(1, 1, width - 3, height - 3)
    painter.end()

    # Aggiungi rumore leggero per effetto carta
    _add_noise(img, rng, 6)

    return img


def generate_steel_metal(
    size: int = 256,
    seed: int | None = None,
) -> QImage:
    """Texture metallica per bersagli steel/popper."""
    rng = _rng_seed(seed)
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(_METAL_BASE.rgb())

    # Chiazze di colore per effetto metallo spazzolato
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for _ in range(50):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        w = rng.randint(6, 30)
        h = rng.randint(6, 30)
        shade = rng.choice([_METAL_LIGHT, _METAL_DARK, QColor("#d4d4d8")])
        alpha = rng.randint(30, 80)
        c = QColor(shade.red(), shade.green(), shade.blue(), alpha)
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(cx, cy, w, h, 2, 2)
    painter.end()

    # Spazzolatura: linee orizzontali sottili
    painter = QPainter(img)
    pen = QPen(QColor(255, 255, 255, 20), 1)
    painter.setPen(pen)
    for y in range(0, size, 3):
        painter.drawLine(0, y, size, y)
    pen = QPen(QColor(0, 0, 0, 15), 1)
    painter.setPen(pen)
    for y in range(1, size, 3):
        painter.drawLine(0, y, size, y)
    painter.end()

    _add_noise(img, rng, 8)

    return img


def generate_wood_planks(
    width: int = 512,
    height: int = 256,
    seed: int | None = None,
) -> QImage:
    """Texture doghe di legno per barriere."""
    rng = _rng_seed(seed)
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(_WOOD_BASE.rgb())

    # Doghe verticali
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    x = 0
    plank_count = 0
    while x < width:
        pw = rng.randint(40, 80)  # larghezza doga
        gap = rng.randint(2, 4)  # fessura tra doghe
        # Ombreggiatura doga
        t = rng.random()
        if t < 0.2:
            c = _WOOD_LIGHT
        elif t < 0.8:
            c = _WOOD_BASE
        else:
            c = _WOOD_DARK
        painter.fillRect(x, 0, pw, height, c)

        # Fessura (linea scura)
        if x + pw + gap < width:
            painter.fillRect(x + pw, 0, gap, height, QColor("#1c0f00"))

        # Nodo del legno occasionale
        if pw > 12 and rng.random() < 0.25:
            knot_x = x + rng.randint(4, max(5, pw - 4))
            knot_y = rng.randint(10, max(11, height - 10))
            knot_r = rng.randint(4, 10)
            painter.setBrush(QBrush(_WOOD_DARK))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(knot_x, knot_y, knot_r, knot_r)
            # Anelli concentrici attorno al nodo
            for r in range(knot_r + 2, knot_r + 12, 3):
                pen = QPen(QColor("#5a3e0a"), 1)
                painter.setPen(pen)
                painter.drawEllipse(knot_x, knot_y, r, r)

        x += pw + gap
        plank_count += 1
    painter.end()

    # Venature verticali
    painter = QPainter(img)
    pen = QPen(QColor(0, 0, 0, 25), 1)
    painter.setPen(pen)
    for _ in range(plank_count * 3):
        lx = rng.randint(0, width)
        ly = rng.randint(0, height)
        painter.drawLine(lx, ly, lx + rng.randint(-2, 2), ly + rng.randint(10, 60))
    painter.end()

    _add_noise(img, rng, 10)

    return img


def generate_hard_cover(
    size: int = 256,
    seed: int | None = None,
) -> QImage:
    """Texture copertura metallica (hard cover)."""
    rng = _rng_seed(seed)
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(_COVER_BASE.rgb())

    # Pannelli metallici
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    cols = rng.randint(3, 5)
    rows = rng.randint(3, 5)
    pw = size // cols
    ph = size // rows

    for row in range(rows):
        for col in range(cols):
            shade = rng.choice([_COVER_BASE, _COVER_LIGHT, QColor("#0f172a")])
            painter.fillRect(col * pw, row * ph, pw - 1, ph - 1, shade)

    painter.end()

    # Rivetti
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rivet_color = QColor("#64748b")
    rivet_shadow = QColor("#334155")
    for row in range(rows + 1):
        for col in range(cols + 1):
            rx = col * pw
            ry = row * ph
            # Ombra rivetto
            painter.setBrush(QBrush(rivet_shadow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rx - 3, ry - 3, 6, 6)
            # Rivetto
            painter.setBrush(QBrush(rivet_color))
            painter.drawEllipse(rx - 4, ry - 4, 6, 6)
    painter.end()

    _add_noise(img, rng, 12)

    return img


def generate_soft_cover(
    size: int = 256,
    seed: int | None = None,
) -> QImage:
    """Texture copertura morbida (telo/tarp)."""
    rng = _rng_seed(seed)
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(_TARP_BASE.rgb())

    # Texture tessile incrociata
    painter = QPainter(img)
    pen = QPen(QColor(0, 0, 0, 30), 1)
    painter.setPen(pen)
    for i in range(0, size, 4):
        painter.drawLine(0, i, size, i)
        painter.drawLine(i, 0, i, size)
    painter.end()

    # Chiazze irregolari
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for _ in range(40):
        cx = rng.randint(0, size)
        cy = rng.randint(0, size)
        rw = rng.randint(10, 40)
        rh = rng.randint(10, 40)
        shade = rng.choice([_TARP_LIGHT, QColor("#3d4f1c")])
        alpha = rng.randint(30, 60)
        c = QColor(shade.red(), shade.green(), shade.blue(), alpha)
        painter.setBrush(QBrush(c))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(cx, cy, rw, rh, 6, 6)
    painter.end()

    _add_noise(img, rng, 14)

    return img


def generate_wood_planks_wide(
    width: int = 512,
    height: int = 256,
    seed: int | None = None,
) -> QImage:
    """Texture doghe legno larghe (per porte)."""
    rng = _rng_seed(seed)
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(_WOOD_DARK.rgb())

    # Doghe verticali larghe, stile legno scuro
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    x = 0
    while x < width:
        pw = rng.randint(60, 100)
        if x + pw > width:
            pw = width - x
        t = rng.random()
        if t < 0.2:
            c = _WOOD_BASE
        elif t < 0.8:
            c = _WOOD_DARK
        else:
            c = QColor("#451a03")
        painter.fillRect(x, 0, pw, height, c)

        if pw > 20 and rng.random() < 0.30:
            knot_x = x + rng.randint(8, max(9, pw - 8))
            knot_y = rng.randint(8, max(9, height - 8))
            painter.setBrush(QBrush(QColor("#2d0f00")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(knot_x, knot_y, rng.randint(4, 8), rng.randint(4, 8))

        x += pw + rng.randint(1, 3)
    painter.end()

    _add_noise(img, rng, 8)

    return img


# ── Generatore principale ────────────────────────────────────────

TEXTURE_DEFS: Final[dict[str, tuple]] = {
    "floor_concrete.png": (generate_floor_concrete, {"size": 512}),
    "wall_drywall.png": (generate_wall_drywall, {"size": 512}),
    "backstop_earth.png": (generate_backstop_earth, {"size": 512}),
    "target_ipsc.png": (generate_target_ipsc, {"width": 256, "height": 512}),
    "steel_metal.png": (generate_steel_metal, {"size": 256}),
    "wood_planks.png": (generate_wood_planks, {"width": 512, "height": 256}),
    "hard_cover.png": (generate_hard_cover, {"size": 256}),
    "soft_cover.png": (generate_soft_cover, {"size": 256}),
    "wood_porte.png": (generate_wood_planks_wide, {"width": 512, "height": 256}),
}


def generate_all(force: bool = False) -> list[Path]:
    """Genera tutte le texture mancanti (o tutte se force=True).

    Returns:
        Lista dei percorsi delle texture generate/esistenti.
    """
    TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for name, (func, kwargs) in TEXTURE_DEFS.items():
        path = TEXTURES_DIR / name
        if path.exists() and not force:
            generated.append(path)
            continue

        print(f"  Genero {name}...")
        image = func(**kwargs)
        image.save(str(path))
        generated.append(path)

    return generated


def generate_one(name: str, force: bool = False) -> Path | None:
    """Genera una texture specifica per nome file.

    Returns:
        Percorso della texture generata, o None se sconosciuta.
    """
    if name not in TEXTURE_DEFS:
        return None

    TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
    func, kwargs = TEXTURE_DEFS[name]
    path = TEXTURES_DIR / name

    if path.exists() and not force:
        return path

    image = func(**kwargs)
    image.save(str(path))
    return path


if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print(f"Generazione texture in {TEXTURES_DIR}...")
    paths = generate_all(force="--force" in sys.argv)

    print(f"\nFatte! {len(paths)} texture:")
    for p in paths:
        status = "✓" if p.exists() else "✗"
        print(f"  {status} {p.name} ({p.stat().st_size // 1024} KB)")
