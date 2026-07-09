"""
Serializzazione e deserializzazione stage in JSON (schema v2 con shooting positions).
"""
from __future__ import annotations
import json
from pathlib import Path

from core.models import Stage, StageItem, ShootingPosition, ItemType


def stage_to_dict(stage: Stage) -> dict:
    """Converte uno Stage in dizionario JSON-serializzabile."""
    return {
        "version": 2,
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
        "shooting_positions": [
            {
                "id": sp.id,
                "x": sp.x,
                "y": sp.y,
                "label": sp.label,
                "is_start": sp.is_start,
                "angle": sp.angle,
                "properties": sp.properties,
            }
            for sp in stage.shooting_positions
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
    # Shooting positions
    max_sp_id = 0
    for sp_data in data.get("shooting_positions", []):
        sp = ShootingPosition(
            id=sp_data.get("id", 0),
            x=sp_data.get("x", 0.0),
            y=sp_data.get("y", 0.0),
            label=sp_data.get("label", ""),
            is_start=sp_data.get("is_start", False),
            angle=sp_data.get("angle", 0.0),
            properties=sp_data.get("properties", {}),
        )
        stage.shooting_positions.append(sp)
        if sp.id > max_sp_id:
            max_sp_id = sp.id
    stage._next_id = max(max_id, max_sp_id) + 1
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
