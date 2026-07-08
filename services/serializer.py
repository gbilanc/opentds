# services/serializer.py
"""Serializzazione e deserializzazione stage in JSON."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

from core.models import Stage, StageItem, ItemType


def stage_to_dict(stage: Stage) -> dict:
    """Converte uno Stage in dizionario JSON-serializzabile."""
    return {
        "version": 1,
        "name": stage.name,
        "width": stage.width,
        "depth": stage.depth,
        "items": [
            {
                "id": it.id,
                "type": it.item_type.name,
                "x": it.x,
                "y": it.y,
                "width": it.width,
                "height": it.height,
                "rotation": it.rotation,
                "color": it.color,
                "label": it.label,
                "properties": it.properties,
            }
            for it in stage.items
        ],
    }


def dict_to_stage(data: dict) -> Stage:
    """Ricostruisce uno Stage da un dizionario."""
    stage = Stage(
        name=data.get("name", "Stage importato"),
        width=data.get("width", 20.0),
        depth=data.get("depth", 15.0),
    )
    max_id = 0
    for it_data in data.get("items", []):
        it = StageItem(
            id=it_data.get("id", 0),
            item_type=ItemType[it_data["type"]],
            x=it_data.get("x", 0.0),
            y=it_data.get("y", 0.0),
            width=it_data.get("width", 1.0),
            height=it_data.get("height", 2.0),
            rotation=it_data.get("rotation", 0.0),
            color=it_data.get("color", "#808080"),
            label=it_data.get("label", ""),
            properties=it_data.get("properties", {}),
        )
        stage.items.append(it)
        if it.id > max_id:
            max_id = it.id
    stage._next_id = max_id + 1
    return stage


def save_stage(stage: Stage, path: Path) -> None:
    """Salva uno Stage su file JSON."""
    data = stage_to_dict(stage)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_stage(path: Path) -> Stage:
    """Carica uno Stage da file JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return dict_to_stage(data)
