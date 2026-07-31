"""Helper per caricare icone SVG come QIcon.

Tutte le icone sono in resources/icons/ come file SVG con viewBox 24×24
e fill="currentColor" per supportare il tema chiaro/scuro.

Uso:
    from ui.icons import load_icon
    btn = QPushButton(load_icon("delete"), "Elimina")
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources",
    "icons",
)
_CACHE: dict[str, QIcon] = {}


def _find_icon_file(name: str) -> str | None:
    """Cerca il file SVG per l'icona name."""
    # Prova nome esatto
    path = os.path.join(_ICONS_DIR, f"{name}.svg")
    if os.path.isfile(path):
        return path
    # Prova con underscore
    path = os.path.join(_ICONS_DIR, f"{name.replace('-', '_')}.svg")
    if os.path.isfile(path):
        return path
    return None


def load_icon(name: str, color: str | None = None) -> QIcon:
    """Carica un'icona SVG come QIcon.

    Args:
        name: Nome del file SVG (senza estensione).
              Usa trattini o underscore (es. "target_paper" o "target-paper").
        color: Se specificato, sostituisce currentColor con un colore fisso
               (es. "#16a34a" per verde). Utile per icone che devono avere
               un colore specifico indipendentemente dal tema.

    Returns:
        QIcon con l'icona caricata, o QIcon vuota se non trovata.
    """
    cache_key = f"{name}:{color or ''}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    filepath = _find_icon_file(name)
    if not filepath:
        from PySide6.QtWidgets import QApplication

        qapp = QApplication.instance()
        if qapp:
            from PySide6.QtWidgets import QStyle

            standard = qapp.style().standardIcon
            # Fallback per icone comuni
            fallbacks = {
                "delete": QStyle.StandardPixmap.SP_TrashIcon,
                "open": QStyle.StandardPixmap.SP_DialogOpenButton,
                "save": QStyle.StandardPixmap.SP_DialogSaveButton,
                "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
                "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
                "close": QStyle.StandardPixmap.SP_DialogCloseButton,
                "search": QStyle.StandardPixmap.SP_FileDialogContentsView,
            }
            if name in fallbacks:
                icon = standard(fallbacks[name])
                _CACHE[cache_key] = icon
                return icon

        return QIcon()

    if color:
        # Applica tinta al SVG via QSvgRenderer
        renderer = QSvgRenderer(filepath)
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        # Applica tinta SourceIn
        tint_painter = QPainter(pixmap)
        tint_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        tint_painter.fillRect(pixmap.rect(), QColor(color))
        tint_painter.end()

        icon = QIcon(pixmap)
    else:
        icon = QIcon(filepath)

    _CACHE[cache_key] = icon
    return icon


def invalidate_cache():
    """Svuota la cache delle icone (utile dopo cambio tema)."""
    _CACHE.clear()
