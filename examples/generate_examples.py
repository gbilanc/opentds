#!/usr/bin/env python3
"""Genera stage di esempio precaricati per OpenTDS.

Crea file JSON nella directory examples/ usando il generatore con
configurazioni predefinite per Short, Medium e Long.
"""
from __future__ import annotations
import json
import sys
import os
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.generator import StageGenerator, GeneratorConfig


def generate_and_save(name: str, filename: str, **kwargs):
    """Genera uno stage e lo salva come JSON."""
    cfg = GeneratorConfig(seed=42, max_attempts=200, **kwargs)
    result = StageGenerator(cfg).generate()
    stage = result.stage

    data = {
        "version": 3,
        "name": stage.name,
        "width": stage.width,
        "depth": stage.depth,
        "course_type": stage.course_type.value if stage.course_type else None,
        "properties": stage.properties,
        "items": [
            {
                "id": it.id,
                "type": it.item_type.name,
                "x": round(it.x, 2),
                "y": round(it.y, 2),
                "width": round(it.width, 2),
                "height": round(it.height, 2),
                "rotation": round(it.rotation, 2),
                "color": it.color,
                "label": it.label,
                "properties": it.properties,
            }
            for it in stage.items
        ],
        "shooting_positions": [
            {
                "id": sp.id,
                "x": round(sp.x, 2),
                "y": round(sp.y, 2),
                "label": sp.label,
                "is_start": sp.is_start,
                "angle": round(sp.angle, 2),
                "properties": sp.properties,
            }
            for sp in stage.shooting_positions
        ],
        "_generator_score": result.score,
        "_generator_attempts": result.attempts,
    }

    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✅ {filename}: score={result.score}, items={len(stage.items)}, "
          f"attempts={result.attempts}")
    return result


if __name__ == "__main__":
    print("Generazione stage di esempio OpenTDS...")
    print()

    # Short course: ≤12 colpi, pochi bersagli, easy per generazione rapida
    generate_and_save(
        "Stage Short (fault lines)",
        "stage_short.json",
        stage_width=20.0,
        stage_depth=18.0,
        num_targets=5,
        num_steel=0,
        num_poppers=1,
        num_plates=0,
        num_moving=0,
        num_mini=0,
        num_walls=1,
        num_barriers=2,
        course_type="short",
        auto_distribution=False,
        delimitation="fault_lines",
        difficulty="easy",
        letter_shape="O",
    )

    # Medium course: ≤24 colpi
    generate_and_save(
        "Stage Medium (fault lines)",
        "stage_medium.json",
        stage_width=25.0,
        stage_depth=20.0,
        num_targets=8,
        num_steel=0,
        num_poppers=1,
        num_plates=1,
        num_moving=1,
        num_mini=0,
        num_walls=2,
        num_barriers=3,
        course_type="medium",
        auto_distribution=False,
        delimitation="fault_lines",
        difficulty="medium",
        letter_shape="L",
    )

    # Long course: ≤32 colpi
    generate_and_save(
        "Stage Long (fault lines)",
        "stage_long.json",
        stage_width=30.0,
        stage_depth=25.0,
        num_targets=12,
        num_steel=0,
        num_poppers=2,
        num_plates=1,
        num_moving=1,
        num_mini=0,
        num_walls=3,
        num_barriers=4,
        course_type="long",
        auto_distribution=False,
        delimitation="fault_lines",
        difficulty="medium",
        letter_shape="T",
    )

    print()
    print("✅ Tutti gli esempi generati con successo.")
