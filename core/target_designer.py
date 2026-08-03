"""
Target Designer — modelli e utility per creare bersagli SVG personalizzati.

Permette di definire sagome IPSC con zone di punteggio (A/B/C/D),
esportarle come SVG con fill="currentColor" per la tinta automatica,
e reimportarle per modifica.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import List, Optional
from xml.etree import ElementTree as ET

# ═══════════════════════════════════════════════════════════════════════════════
#  Modelli
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SvgZone:
    """Una zona di punteggio sul bersaglio (es. zona A, B, C, D).

    shape_type: "rect" | "ellipse" | "path"
    coordinates: per rect: (x, y, w, h); per ellipse: (cx, cy, rx, ry);
                per path: stringa d-path
    """

    label: str = "A"
    color: str = "#000000"
    points: int = 5
    shape_type: str = "rect"  # rect | ellipse | path
    x: float = 0.0
    y: float = 0.0
    width: float = 50.0
    height: float = 50.0
    path_data: str = ""  # per shape_type="path"
    rx: float = 0.0  # per ellipse
    ry: float = 0.0

    def to_svg_element(self) -> str:
        """Genera l'elemento SVG per questa zona."""
        if self.shape_type == "rect":
            return (
                f'<rect x="{self.x}" y="{self.y}" '
                f'width="{self.width}" height="{self.height}" '
                f'fill="{self.color}" stroke="#fff" stroke-width="1" opacity="0.85"/>'
            )
        elif self.shape_type == "ellipse":
            cx = self.x + self.width / 2
            cy = self.y + self.height / 2
            rx = self.width / 2
            ry = self.height / 2
            return (
                f'<ellipse cx="{cx}" cy="{cy}" '
                f'rx="{rx}" ry="{ry}" '
                f'fill="{self.color}" stroke="#fff" stroke-width="1" opacity="0.85"/>'
            )
        elif self.shape_type == "octagon":
            cx = self.x + self.width / 2
            cy = self.y + self.height / 2
            rx = self.width / 2
            ry = self.height / 2
            points = []
            for i in range(8):
                angle = math.pi * 2 * i / 8 - math.pi / 8
                px = cx + rx * math.cos(angle)
                py = cy + ry * math.sin(angle)
                points.append(f"{px:.1f},{py:.1f}")
            return (
                f'<polygon points="{" ".join(points)}" '
                f'fill="{self.color}" stroke="#fff" stroke-width="1" opacity="0.85"/>'
            )
        elif self.shape_type == "path":
            return (
                f'<path d="{self.path_data}" '
                f'fill="{self.color}" stroke="#fff" stroke-width="1" opacity="0.85"/>'
            )
        return ""


@dataclass
class SvgTargetDesign:
    """Un bersaglio SVG personalizzato completo.

    Può essere esportato come file SVG valido per l'uso nell'app.

    `num_targets` e `target_kinds` descrivono i bersagli CONTENUTI
    nell'SVG (un file può disegnare più sagome, es. doppio affiancato
    o doppio + ostaggio). Vengono serializzati come `<metadata>` dentro
    l'SVG stesso e usati dal motore per conteggi corretti.
    """

    name: str = "Nuovo Bersaglio"
    width: float = 100.0  # viewBox width
    height: float = 100.0  # viewBox height
    silhouette_path: str = ""  # path del contorno principale (fill="currentColor")
    zones: List[SvgZone] = field(default_factory=list)
    description: str = ""
    num_targets: int = 1  # numero di bersagli contenuti
    target_kinds: List[str] = field(default_factory=list)  # tipo per bersaglio

    def effective_kinds(self) -> List[str]:
        """Tipi effettivi dei bersagli contenuti.

        Priorità a `target_kinds` (per-target); altrimenti `num_targets`
        ripetizioni del tipo di default (paper). Ritorna sempre almeno
        un elemento valido.
        """
        if self.target_kinds:
            kinds = [k for k in self.target_kinds if k in VALID_TARGET_KINDS]
            if kinds:
                return kinds
        return [KIND_PAPER] * max(1, self.num_targets)

    def add_zone(self, zone: SvgZone) -> None:
        self.zones.append(zone)

    def remove_zone(self, index: int) -> None:
        if 0 <= index < len(self.zones):
            self.zones.pop(index)

    def to_svg(self) -> str:
        """Genera il documento SVG completo."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}">',
            f"  <!-- {self.name} -->",
            f"  <desc>{self.description or 'Bersaglio personalizzato'}</desc>",
            _metadata_xml(self.effective_kinds()),
            "",
            "  <!-- Silhouette principale (tintabile con currentColor) -->",
        ]
        if self.silhouette_path:
            lines.append(f'  <path d="{self.silhouette_path}" fill="currentColor"/>')
        else:
            # Default: rettangolo arrotondato
            lines.append(
                f'  <rect x="2" y="2" width="{self.width - 4}" '
                f'height="{self.height - 4}" rx="8" fill="currentColor"/>'
            )

        lines.append("")
        lines.append("  <!-- Zone di punteggio -->")
        for zone in self.zones:
            elem = zone.to_svg_element()
            if elem:
                lines.append(f"  {elem}")
                # Label della zona
                cx = zone.x + zone.width / 2
                cy = zone.y + zone.height / 2
                lines.append(
                    f'  <text x="{cx}" y="{cy + 4}" '
                    f'text-anchor="middle" fill="white" '
                    f'font-size="14" font-weight="bold">{zone.label}</text>'
                )

        lines.append("</svg>")
        return "\n".join(lines)

    def to_svg_bytes(self) -> bytes:
        return self.to_svg().encode("utf-8")

    @staticmethod
    def from_svg(filepath: str) -> Optional[SvgTargetDesign]:
        """Importa un SVG esistente per modifica."""
        if not os.path.isfile(filepath):
            return None
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()

            # ViewBox
            vb = root.get("viewBox", "0 0 100 100")
            parts = vb.split()
            w = float(parts[2]) if len(parts) >= 3 else 100.0
            h = float(parts[3]) if len(parts) >= 4 else 100.0

            # Nome dal file (salta nomi temporanei)
            name = os.path.splitext(os.path.basename(filepath))[0]
            if name.startswith("tmp") or name.startswith("temp"):
                name = "Bersaglio Importato"
            else:
                name = name.replace("_", " ").replace("-", " ").title()

            design = SvgTargetDesign(name=name, width=w, height=h)

            # Metadati bersagli contenuti (numero e tipo)
            meta = _read_metadata(root)
            if meta:
                design.target_kinds = list(meta)
                design.num_targets = len(meta)

            # Trova il path principale (fill="currentColor")
            ns = {"svg": "http://www.w3.org/2000/svg"}
            for path_elem in root.findall(".//svg:path", ns):
                fill = path_elem.get("fill", "")
                if fill == "currentColor":
                    design.silhouette_path = path_elem.get("d", "")
                    break

            # Trova le zone (elementi con fill diverso da currentColor)
            for elem in root.findall(".//svg:rect", ns):
                fill = elem.get("fill", "")
                if fill and fill != "currentColor" and fill != "none":
                    zone = SvgZone(
                        shape_type="rect",
                        x=float(elem.get("x", 0)),
                        y=float(elem.get("y", 0)),
                        width=float(elem.get("width", 30)),
                        height=float(elem.get("height", 30)),
                        color=fill,
                    )
                    # Cerca il label (testo vicino)
                    tx, ty = zone.x + zone.width / 2, zone.y + zone.height / 2
                    for text_elem in root.findall(".//svg:text", ns):
                        tx_e = float(text_elem.get("x", 0))
                        ty_e = float(text_elem.get("y", 0))
                        if abs(tx_e - tx) < 5 and abs(ty_e - ty - 4) < 5:
                            zone.label = text_elem.text or "?"
                            break
                    design.zones.append(zone)

            for elem in root.findall(".//svg:ellipse", ns):
                fill = elem.get("fill", "")
                if fill and fill != "currentColor" and fill != "none":
                    cx = float(elem.get("cx", 50))
                    cy = float(elem.get("cy", 50))
                    rx = float(elem.get("rx", 20))
                    ry = float(elem.get("ry", 20))
                    zone = SvgZone(
                        shape_type="ellipse",
                        x=cx - rx,
                        y=cy - ry,
                        width=rx * 2,
                        height=ry * 2,
                        color=fill,
                    )
                    for text_elem in root.findall(".//svg:text", ns):
                        tx_e = float(text_elem.get("x", 0))
                        ty_e = float(text_elem.get("y", 0))
                        if abs(tx_e - cx) < 5 and abs(ty_e - cy - 4) < 5:
                            zone.label = text_elem.text or "?"
                            break
                    design.zones.append(zone)

            # Poligoni (es. ottagoni)
            for elem in root.findall(".//svg:polygon", ns):
                fill = elem.get("fill", "")
                if fill and fill != "currentColor" and fill != "none":
                    points_str = elem.get("points", "")
                    pts = []
                    for pair in points_str.split():
                        if "," in pair:
                            x, y = pair.split(",")
                            pts.append((float(x.strip()), float(y.strip())))
                    if len(pts) >= 3:
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        min_x, max_x = min(xs), max(xs)
                        min_y, max_y = min(ys), max(ys)
                        shape = "octagon" if len(pts) == 8 else "polygon"
                        zone = SvgZone(
                            shape_type=shape,
                            x=min_x,
                            y=min_y,
                            width=max_x - min_x,
                            height=max_y - min_y,
                            color=fill,
                        )
                        # Cerca label al centro del poligono
                        cx = (min_x + max_x) / 2
                        cy = (min_y + max_y) / 2
                        for text_elem in root.findall(".//svg:text", ns):
                            tx_e = float(text_elem.get("x", 0))
                            ty_e = float(text_elem.get("y", 0))
                            if abs(tx_e - cx) < 5 and abs(ty_e - cy - 4) < 5:
                                zone.label = text_elem.text or "?"
                                break
                        design.zones.append(zone)

            return design
        except Exception:
            import traceback

            traceback.print_exc()
            return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "silhouette_path": self.silhouette_path,
            "description": self.description,
            "num_targets": len(self.effective_kinds()),
            "target_kinds": list(self.effective_kinds()),
            "zones": [
                {
                    "label": z.label,
                    "color": z.color,
                    "points": z.points,
                    "shape_type": z.shape_type,
                    "x": z.x,
                    "y": z.y,
                    "width": z.width,
                    "height": z.height,
                    "path_data": z.path_data,
                }
                for z in self.zones
            ],
        }

    @staticmethod
    def from_dict(data: dict) -> SvgTargetDesign:
        design = SvgTargetDesign(
            name=data.get("name", "Bersaglio"),
            width=data.get("width", 100),
            height=data.get("height", 100),
            silhouette_path=data.get("silhouette_path", ""),
            description=data.get("description", ""),
            num_targets=data.get("num_targets", 1),
            target_kinds=list(data.get("target_kinds", [])),
        )
        for zd in data.get("zones", []):
            design.zones.append(
                SvgZone(
                    label=zd.get("label", "A"),
                    color=zd.get("color", "#000000"),
                    points=zd.get("points", 5),
                    shape_type=zd.get("shape_type", "rect"),
                    x=zd.get("x", 0),
                    y=zd.get("y", 0),
                    width=zd.get("width", 30),
                    height=zd.get("height", 30),
                    path_data=zd.get("path_data", ""),
                )
            )
        return design


# ═══════════════════════════════════════════════════════════════════════════════
#  Utility
# ═══════════════════════════════════════════════════════════════════════════════

# Palette colori IPSC per zone di punteggio
ZONE_COLORS: dict[str, str] = {
    "A": "#16a34a",  # verde
    "B": "#2563eb",  # blu
    "C": "#ca8a04",  # giallo scuro
    "D": "#dc2626",  # rosso
}

# Cartella di default per i bersagli personalizzati
CUSTOM_TARGETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources",
    "targets",
    "custom",
)


def ensure_custom_dir():
    """Crea la cartella per i bersagli personalizzati se non esiste."""
    os.makedirs(CUSTOM_TARGETS_DIR, exist_ok=True)


def list_custom_targets() -> List[str]:
    """Restituisce la lista dei percorsi dei bersagli personalizzati."""
    ensure_custom_dir()
    svgs = []
    for f in sorted(os.listdir(CUSTOM_TARGETS_DIR)):
        if f.lower().endswith(".svg"):
            svgs.append(os.path.join(CUSTOM_TARGETS_DIR, f))
    return svgs


# ═══════════════════════════════════════════════════════════════════════════════
#  Metadati bersagli contenuti (numero + tipo)
# ═══════════════════════════════════════════════════════════════════════════════

# Tipi di bersaglio contenuti in un SVG custom (uno per sagoma disegnata)
KIND_PAPER = "paper"
KIND_STEEL = "steel"
KIND_POPPER = "popper"
KIND_PLATE = "plate"
KIND_NO_SHOOT = "no_shoot"

VALID_TARGET_KINDS: tuple[str, ...] = (
    KIND_PAPER,
    KIND_STEEL,
    KIND_POPPER,
    KIND_PLATE,
    KIND_NO_SHOOT,
)

# Tipi che contano come acciaio per le statistiche
STEEL_KINDS: frozenset[str] = frozenset({KIND_STEEL, KIND_POPPER, KIND_PLATE})

KIND_LABELS: dict[str, str] = {
    KIND_PAPER: "paper",
    KIND_STEEL: "steel",
    KIND_POPPER: "popper",
    KIND_PLATE: "plate",
    KIND_NO_SHOOT: "no-shoot",
}

# ID dell'elemento <metadata> usato per i metadati OpenTDS dentro l'SVG
META_ELEMENT_ID = "opentds"


@dataclass(frozen=True)
class CustomTargetMeta:
    """Metadati dei bersagli contenuti in un SVG custom.

    `kinds` è la lista dei tipi, uno per sagoma disegnata
    (es. ("paper", "paper", "no_shoot") per un doppio + ostaggio).
    """

    kinds: tuple[str, ...] = (KIND_PAPER,)

    @property
    def count(self) -> int:
        return len(self.kinds)

    @property
    def paper(self) -> int:
        return sum(1 for k in self.kinds if k == KIND_PAPER)

    @property
    def steel(self) -> int:
        return sum(1 for k in self.kinds if k in STEEL_KINDS)

    @property
    def no_shoots(self) -> int:
        return sum(1 for k in self.kinds if k == KIND_NO_SHOOT)

    @property
    def label(self) -> str:
        """Rappresentazione leggibile, es. '2 paper + 1 no-shoot'."""
        parts = []
        for kind in dict.fromkeys(self.kinds):  # conserva l'ordine, senza duplicati
            parts.append(f"{sum(1 for k in self.kinds if k == kind)} {KIND_LABELS.get(kind, kind)}")
        return " + ".join(parts) if parts else "1 paper"


def _metadata_xml(kinds: list[str]) -> str:
    """Genera l'elemento <metadata> con il payload JSON dei bersagli contenuti."""
    payload = json.dumps({"targets": [{"kind": k} for k in kinds]}, separators=(",", ":"))
    return f'  <metadata id="{META_ELEMENT_ID}">{payload}</metadata>'


def _read_metadata(root: ET.Element) -> tuple[str, ...] | None:
    """Estrae i tipi bersaglio dal <metadata> di un albero SVG."""
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] != "metadata":
            continue
        text = (elem.text or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except (ValueError, TypeError):
            continue
        kinds = tuple(
            k
            for t in payload.get("targets", [])
            if isinstance(t, dict) and (k := t.get("kind")) in VALID_TARGET_KINDS
        )
        if kinds:
            return kinds
    return None


def _project_resources_dir() -> str:
    """Cartella resources/ del progetto, indipendente dal cwd."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)  # core/ → progetto
    res = os.path.join(root, "resources")
    if os.path.isdir(res):
        return res
    return os.path.join(os.getcwd(), "resources")


def resolve_custom_svg_path(custom_path: str) -> str:
    """Risolve un percorso SVG custom in un percorso assoluto.

    Supporta:
    - Percorsi assoluti (es. /home/user/mio.svg)
    - Percorsi relativi a resources/ (es. targets/custom/ipsc_target.svg)
    - Nome file semplice (es. ipsc_target.svg) -> cerca in targets/custom/

    Ritorna "" se il file non esiste.
    """
    if not custom_path:
        return ""
    if os.path.isabs(custom_path) and os.path.isfile(custom_path):
        return custom_path
    resources_dir = _project_resources_dir()
    resolved = os.path.join(resources_dir, custom_path)
    if os.path.isfile(resolved):
        return resolved
    resolved = os.path.join(resources_dir, "targets", "custom", custom_path)
    if os.path.isfile(resolved):
        return resolved
    if os.path.isfile(custom_path):
        return custom_path
    return ""


def make_custom_path_portable(absolute_path: str) -> str:
    """Converte un percorso assoluto in relativo a resources/ se possibile."""
    if not absolute_path or not os.path.isabs(absolute_path):
        return absolute_path
    resources_dir = _project_resources_dir()
    try:
        rel = os.path.relpath(absolute_path, resources_dir)
        if not rel.startswith(".."):
            return rel
    except ValueError:
        pass
    return absolute_path


def parse_custom_target_meta(svg_path: str) -> CustomTargetMeta:
    """Legge i metadati dei bersagli contenuti da un file SVG.

    Ritorna il default (1 paper) se il file non esiste o non ha metadati.
    """
    resolved = resolve_custom_svg_path(svg_path)
    if not resolved or not os.path.isfile(resolved):
        return CustomTargetMeta()
    try:
        tree = ET.parse(resolved)
    except (ET.ParseError, OSError):
        return CustomTargetMeta()
    kinds = _read_metadata(tree.getroot())
    if kinds:
        return CustomTargetMeta(kinds=kinds)
    return CustomTargetMeta()


def make_ipsc_silhouette(w: float = 100, h: float = 100) -> str:
    """Genera il path per una silhouette IPSC classica adatta alle dimensioni."""
    cx = w / 2
    # Crea un path proporzionale
    r1 = w * 0.48  # larghezza spalle
    r2 = w * 0.33  # larghezza vita
    top = h * 0.05
    bot = h * 0.95
    shoulder_y = h * 0.15
    waist_y = h * 0.55
    hip_y = h * 0.70
    return (
        f"M {cx - r1} {shoulder_y} "
        f"C {cx - r1 - 5} {shoulder_y + 10}, {cx - r2 - 8} {waist_y}, "
        f"{cx - r2} {hip_y} "
        f"C {cx - r2} {hip_y + 10}, {cx - r2 + 5} {bot}, {cx - r2 + 15} {bot} "
        f"L {cx + r2 - 15} {bot} "
        f"C {cx + r2 - 5} {bot}, {cx + r2} {hip_y + 10}, {cx + r2} {hip_y} "
        f"C {cx + r2 + 8} {waist_y}, {cx + r1 + 5} {shoulder_y + 10}, "
        f"{cx + r1} {shoulder_y} "
        f"C {cx + r1} {top + 5}, {cx + 5} {top}, {cx} {top} "
        f"C {cx - 5} {top}, {cx - r1} {top + 5}, {cx - r1} {shoulder_y} Z"
    )
