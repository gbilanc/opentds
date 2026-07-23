"""
Scoring, metadati di briefing e risoluzione conteggi per stage IPSC.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional

from core.constants import (
    COURSE_TARGET_DISTRIBUTION,
    MAX_ACTIVATOR_DISTANCE,
    MAX_ACTIVATOR_MOVING_DISTANCE,
    MAX_ACTIVATED_PER_ACTIVATOR,
    ACTIVATOR_SECTOR_ANGLE_DEG,
)
from core.models import Stage, StageItem, ItemType
from core.geometry import euclidean_distance


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers per classificazione tipi
# ═══════════════════════════════════════════════════════════════════════════════

def is_paper_like(t: ItemType) -> bool:
    """True per tipi bersaglio cartaceo."""
    return t in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET, ItemType.MICRO_TARGET)


def is_steel_like(t: ItemType) -> bool:
    """True per tipi bersaglio metallico."""
    return t in (ItemType.STEEL_TARGET, ItemType.POPPER, ItemType.METAL_PLATE)


def is_scoring_target(t: ItemType) -> bool:
    """True per tutti i bersagli che assegnano punti."""
    return is_paper_like(t) or is_steel_like(t) or t in (
        ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)


def is_obstacle(t: ItemType) -> bool:
    """True per ostacoli/barriere/muri/coperture."""
    return t in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR,
                  ItemType.HARD_COVER, ItemType.SOFT_COVER)


def is_blocking_wall(t: ItemType) -> bool:
    """True per item che bloccano la visuale."""
    return t in (ItemType.WALL, ItemType.BARRIER, ItemType.DOOR, ItemType.HARD_COVER)


# ═══════════════════════════════════════════════════════════════════════════════
#  Risoluzione conteggi bersagli
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_target_counts(
    num_targets: int,
    num_steel: int,
    num_poppers: int,
    num_plates: int,
    num_mini: int,
    num_moving: int,
    auto_distribution: bool,
    course_type: str,
) -> dict:
    """Calcola i conteggi bersagli in base al course_type e ai parametri.

    Se auto_distribution è True e course_type è impostato, usa le
    distribuzioni tipiche (Short=5+1+1, Medium=11+1+2, Long=15+2+2).
    Altrimenti usa i valori letterali della configurazione.
    """
    if not auto_distribution or not course_type:
        if num_poppers > 0 or num_plates > 0:
            poppers = num_poppers
            plates = num_plates
        else:
            poppers = max(1, round(num_steel * 0.6)) if num_steel > 0 else 1
            plates = max(0, num_steel - poppers) if num_steel > 0 else 1
        if num_steel == 0 and num_poppers == 0 and num_plates == 0:
            poppers = 0
            plates = 0
        return {
            "paper": num_targets,
            "poppers": poppers,
            "plates": plates,
            "mini": num_mini,
            "moving": num_moving,
        }

    base = COURSE_TARGET_DISTRIBUTION.get(course_type, {}).copy()
    if not base:
        base = {"paper": 8, "poppers": 1, "plates": 1, "mini": 0, "moving": 1}

    if num_targets > 0:
        base["paper"] = num_targets
    has_explicit_steel = num_poppers > 0 or num_plates > 0
    if num_poppers > 0:
        base["poppers"] = num_poppers
    elif num_steel > 0 and not has_explicit_steel:
        base["poppers"] = max(1, round(num_steel * 0.6))
    if num_plates > 0:
        base["plates"] = num_plates
    elif num_steel > 0 and not has_explicit_steel:
        base["plates"] = max(0, num_steel - base["poppers"])
    if num_mini > 0:
        base["mini"] = num_mini
    if num_moving > 0:
        base["moving"] = num_moving

    return base


# ═══════════════════════════════════════════════════════════════════════════════
#  Relazioni attivatore-attivato
# ═══════════════════════════════════════════════════════════════════════════════

def create_activator_relationships(
    stage: Stage,
    items: List[StageItem],
    activators: List[StageItem],
    perimeter_poly: List[tuple[float, float]] | None,
) -> None:
    """Collega poppers/plates a bersagli attivati (mobili o paper).

    Priorità: bersagli MOBILI (swinger, drop_turner, mover) > paper target.

    I bersagli mobili devono essere attivati da bersagli metallici
    posti nelle immediate vicinanze (distanza < MAX_ACTIVATOR_MOVING_DISTANCE).
    """
    if not activators or not perimeter_poly:
        return

    cx = sum(p[0] for p in perimeter_poly) / len(perimeter_poly)
    cy = sum(p[1] for p in perimeter_poly) / len(perimeter_poly)

    moving_targets = [it for it in items
                      if it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER)
                      and "activated_by" not in it.properties]
    papers = [it for it in items
              if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET)
              and "activated_by" not in it.properties]

    if not moving_targets and not papers:
        return

    activators.sort(key=lambda a: euclidean_distance(a.x, a.y, cx, cy))
    used_targets: set = set()
    descs: list[str] = []

    # --- Passata 1: attiva bersagli MOBILI (distanza ravvicinata) ---
    for act_idx, activator in enumerate(activators):
        if not moving_targets:
            break

        act_angle = math.atan2(activator.y - cy, activator.x - cx)
        nearby = []
        for mt in moving_targets:
            if mt.id in used_targets:
                continue
            mt_angle = math.atan2(mt.y - cy, mt.x - cx)
            angle_diff = abs(act_angle - mt_angle)
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff
            dist = euclidean_distance(activator.x, activator.y, mt.x, mt.y)
            if angle_diff < math.radians(ACTIVATOR_SECTOR_ANGLE_DEG) and dist < MAX_ACTIVATOR_MOVING_DISTANCE:
                nearby.append((dist, mt))

        if not nearby:
            continue

        nearby.sort(key=lambda x: x[0])
        selected = [mt for _, mt in nearby[:MAX_ACTIVATED_PER_ACTIVATOR]]
        sel_ids = [s.id for s in selected]

        activator.properties["activates"] = sel_ids
        activator.properties["is_activator"] = True
        label_prefix = "P" if activator.item_type == ItemType.POPPER else "MP"
        activator.label = f"{label_prefix}{act_idx + 1}"

        type_labels = {
            ItemType.SWINGER: "Swinger",
            ItemType.DROP_TURNER: "Drop Turner",
            ItemType.MOVER: "Mover",
        }
        for s in selected:
            s.properties["activated_by"] = [activator.id]
            s.properties["activation_visible"] = True
            used_targets.add(s.id)

        label = activator.label
        target_strs = []
        for sid in sel_ids:
            s_item = next((x for x in items if x.id == sid), None)
            if s_item:
                tlabel = type_labels.get(s_item.item_type, "")
                if not s_item.label or s_item.label in ("Paper", "Mini", "Popper", "Plate"):
                    s_item.label = f"S{sid}"
                target_strs.append(f"{s_item.label} ({tlabel})" if tlabel else s_item.label)
            else:
                target_strs.append(f"S{sid}")
        congiunzione = " e " if len(target_strs) > 1 else ""
        vis = "resteranno visibili" if len(target_strs) > 1 else "resterà visibile"
        desc = f"{label} attiva {congiunzione.join(target_strs)} che {vis} al termine del movimento"
        descs.append(desc)

    # --- Passata 2: attiva PAPER TARGET (fallback) ---
    for act_idx, activator in enumerate(activators):
        if "is_activator" in activator.properties:
            continue
        if not papers:
            continue

        act_angle = math.atan2(activator.y - cy, activator.x - cx)
        nearby = []
        for p in papers:
            if p.id in used_targets:
                continue
            p_angle = math.atan2(p.y - cy, p.x - cx)
            angle_diff = abs(act_angle - p_angle)
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff
            dist = euclidean_distance(activator.x, activator.y, p.x, p.y)
            if angle_diff < math.radians(ACTIVATOR_SECTOR_ANGLE_DEG) and dist < MAX_ACTIVATOR_DISTANCE:
                nearby.append((dist, p))

        if not nearby:
            continue

        nearby.sort(key=lambda x: x[0])
        selected = [p for _, p in nearby[:MAX_ACTIVATED_PER_ACTIVATOR]]
        sel_ids = [s.id for s in selected]

        existing_activates = activator.properties.get("activates", [])
        sel_ids = existing_activates + [sid for sid in sel_ids if sid not in existing_activates]

        activator.properties["activates"] = sel_ids
        activator.properties["is_activator"] = True
        if not activator.properties.get("_labeled"):
            label_prefix = "P" if activator.item_type == ItemType.POPPER else "MP"
            activator.label = f"{label_prefix}{act_idx + 1}"
            activator.properties["_labeled"] = True

        for s in selected:
            s.properties["activated_by"] = s.properties.get("activated_by", []) + [activator.id]
            s.properties["activation_visible"] = True
            used_targets.add(s.id)

        label = activator.label or f"{activator.item_type.name}#{activator.id}"
        target_strs = []
        for sid in sel_ids:
            s_item = next((x for x in items if x.id == sid), None)
            if s_item:
                if not s_item.label or s_item.label in ("Paper", "Mini", "Popper", "Plate"):
                    s_item.label = f"T{sid}"
                target_strs.append(s_item.label)
            else:
                target_strs.append(f"T{sid}")
        congiunzione = " e " if len(target_strs) > 1 else ""
        vis = "resteranno visibili" if len(target_strs) > 1 else "resterà visibile"
        desc = f"{label} attiva {congiunzione.join(target_strs)} che {vis} al termine del movimento"
        descs.append(desc)

    if descs:
        stage.properties["activator_descs"] = descs
        stage.properties["procedure"] = (
            "Al segnale di partenza ingaggiare tutti i bersagli. "
            + " ".join(descs) + "."
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Metadati di briefing
# ═══════════════════════════════════════════════════════════════════════════════

def populate_stage_metadata(
    stage: Stage,
    difficulty: str,
    num_poppers: int,
    num_plates: int,
    num_moving: int,
) -> None:
    """Popola i metadati di briefing nello stage."""
    if stage.properties.get("start_signal"):
        return

    stage.properties["start_signal"] = "Acustico"

    if difficulty == "hard":
        stage.properties["start_position"] = "Talloni che toccano i segni come mostrato"
    elif difficulty == "easy":
        stage.properties["start_position"] = "Ovunque nella shooting area"
    else:
        stage.properties["start_position"] = "In piedi nella shooting area"

    stage.properties["ready_condition_handgun"] = (
        "In piedi come da regolamento IPSC Handgun punto 8.2.2 (Appendice E2), come mostrato"
    )
    stage.properties["ready_condition_pcc"] = (
        "In piedi come da regolamento IPSC PCC punto 8.2.2 (Appendice E1), come mostrato"
    )
    if difficulty == "hard":
        stage.properties["handgun_condition"] = "Arma scarica in fondina"
        stage.properties["pcc_condition"] = "Scarico Option 3"
    else:
        stage.properties["handgun_condition"] = "Arma in fondina caricatore inserito colpo non camerato"
        stage.properties["pcc_condition"] = "Carico Option 1"

    if "procedure" not in stage.properties:
        stage.properties["procedure"] = "Al segnale di partenza ingaggiare tutti i bersagli."

    paper_count = sum(1 for it in stage.items
                      if it.item_type in (ItemType.PAPER_TARGET, ItemType.MINI_TARGET))
    steel_count = sum(1 for it in stage.items
                      if it.item_type in (ItemType.POPPER, ItemType.METAL_PLATE))
    stage.properties["max_points"] = paper_count * 10 + steel_count * 5

    stage.properties["angoli_sicurezza"] = "90° laterali e parapalle in verticale"
    stage.properties["hard_cover"] = "Le strutture sono hard cover"
    stage.properties["note"] = (
        "Il punteggio verrà conteggiato durante l'esecuzione dell'esercizio. "
        "Il tiratore potrà delegare un altro tiratore alla verifica del punteggio."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Scoring qualità stage
# ═══════════════════════════════════════════════════════════════════════════════

def score_stage(
    stage: Stage,
    items: List[StageItem],
    perimeter_poly: List[tuple[float, float]] | None,
    interior_samples: List[tuple[float, float]],
    get_blocking_walls_fn,
    is_target_visible_fn,
    config_difficulty: str,
) -> float:
    """Valuta la qualità dello stage (più alto = migliore)."""
    score = 0.0
    targets = [it for it in items if is_scoring_target(it.item_type)]
    walls = [it for it in items if is_blocking_wall(it.item_type)]

    score += len(targets) * 10

    steel = [it for it in targets if is_steel_like(it.item_type)]
    score += len(steel) * 5

    moving = [it for it in items if it.item_type in (ItemType.SWINGER, ItemType.MOVER, ItemType.DROP_TURNER)]
    score += len(moving) * 15

    if len(targets) >= 2:
        total_dist = 0.0
        count = 0
        for i, a in enumerate(targets):
            for b in targets[i + 1:]:
                total_dist += euclidean_distance(a.x, a.y, b.x, b.y)
                count += 1
        if count > 0:
            avg_dist = total_dist / count
            score += max(0, 20 - abs(avg_dist - 3.5) * 5)

    if len(walls) > 0:
        score += len(walls) * 3

    perim_items = [it for it in items if it.item_type in (ItemType.FAULT_LINE, ItemType.WALL, ItemType.BARRIER)]
    score += len(perim_items) * 2
    if perimeter_poly and len(perimeter_poly) >= 5:
        score += 5
    if perimeter_poly and len(perimeter_poly) >= 6:
        score += 5

    visible_count = 0
    blockers = get_blocking_walls_fn()
    for t in targets:
        if is_target_visible_fn(t, blockers):
            visible_count += 1
    if targets:
        visibility_pct = visible_count / len(targets)
        if visibility_pct >= 0.9:
            score += 15
        elif visibility_pct >= 0.7:
            score += 8

    if config_difficulty == "hard":
        score *= 1.2

    return round(score, 2)
