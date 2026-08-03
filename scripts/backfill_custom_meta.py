"""Backfill dei metadati (numero + tipo bersagli contenuti) negli SVG custom.

Inietta un elemento <metadata id="opentds"> in ogni SVG di
resources/targets/custom/ secondo una mappatura esplicita per nome file.

Idempotente: se un SVG ha già i metadati, viene saltato.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.target_designer import (  # noqa: E402
    CUSTOM_TARGETS_DIR,
    KIND_NO_SHOOT,
    KIND_PAPER,
    KIND_PLATE,
    KIND_POPPER,
    _metadata_xml,
)

# Mappatura esplicita: stem del filename -> tipi bersaglio contenuti
BACKFILL_MAP: dict[str, list[str]] = {
    "ipsc_target": [KIND_PAPER],
    "ipsc_mini_target": [KIND_PAPER],
    "ipsc_target_2a": [KIND_PAPER, KIND_PAPER],
    "ipsc_target_2s": [KIND_PAPER, KIND_PAPER],
    "ipsc_target_2a+ns": [KIND_PAPER, KIND_PAPER, KIND_NO_SHOOT],
    "ipsc_target_2s+ns": [KIND_PAPER, KIND_PAPER, KIND_NO_SHOOT],
    "ipsc_popper": [KIND_POPPER],
    "ipsc_mini_popper": [KIND_POPPER],
    "ipsc_metal_plate": [KIND_PLATE],
    "ipsc_no_shoot": [KIND_NO_SHOOT],
}

META_TAG = 'metadata id="opentds"'


def backfill_file(filepath: str, kinds: list[str]) -> bool:
    """Inietta i metadati in un SVG. Ritorna True se modificato."""
    with open(filepath, encoding="utf-8") as f:
        text = f.read()

    if META_TAG in text:
        return False  # già dotato di metadati

    # Inserisce dopo </desc> se presente, altrimenti dopo il tag <svg …>
    desc_end = text.find("</desc>")
    if desc_end >= 0:
        insert_at = desc_end + len("</desc>")
    else:
        insert_at = text.find(">", text.find("<svg")) + 1

    meta_xml = _metadata_xml(kinds)
    new_text = text[:insert_at] + "\n" + meta_xml + text[insert_at:]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_text)
    return True


def main() -> int:
    if not os.path.isdir(CUSTOM_TARGETS_DIR):
        print(f"Cartella non trovata: {CUSTOM_TARGETS_DIR}")
        return 1

    updated: list[str] = []
    skipped: list[str] = []
    for fname in sorted(os.listdir(CUSTOM_TARGETS_DIR)):
        if not fname.lower().endswith(".svg"):
            continue
        stem = os.path.splitext(fname)[0]
        kinds = BACKFILL_MAP.get(stem)
        filepath = os.path.join(CUSTOM_TARGETS_DIR, fname)
        if kinds is None:
            print(f"  ?  {fname}: nessuna mappatura, saltato")
            skipped.append(fname)
            continue
        if backfill_file(filepath, kinds):
            updated.append(fname)
        else:
            skipped.append(fname)

    print(f"\nAggiornati ({len(updated)}): {', '.join(updated) or '—'}")
    print(f"Saltati   ({len(skipped)}): {', '.join(skipped) or '—'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
