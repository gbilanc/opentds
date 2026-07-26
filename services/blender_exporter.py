"""
Esportazione stage IPSC in scena Blender 3D navigabile.

Genera un file .blend con:
  - Geometria 3D di tutti gli oggetti stage (muri, bersagli, barriere, etc.)
  - Materiali PBR con colori IPSC-conformi
  - Pavimento con griglia metrica e parapalle (backstop)
  - Telecamere a ogni shooting position (pronte per NumPad 0)
  - Walkthrough animato lungo le posizioni di tiro
  - Illuminazione professionale a 3 punti
  - Freece direzionali UP-RANGE / DOWN-RANGE

Utilizzo:
    from services.blender_exporter import export_stage_to_blend
    export_stage_to_blend(stage, Path("stage.blend"))

Esecuzione headless:
    blender -b -P script.py

Dipende da: bpy (Blender built-in), mathutils.
Richiede Blender 4.0+ (testato su 5.2 LTS).
"""
from __future__ import annotations

import math
import subprocess
import shutil
import sys as _sys
from pathlib import Path
from typing import Optional

# Assicura che il progetto sia nel path (utile quando eseguito da Blender)
_script_dir = Path(__file__).resolve().parent.parent
if str(_script_dir) not in _sys.path:
    _sys.path.insert(0, str(_script_dir))

from core.models import Stage, StageItem, ItemType, ShootingPosition
from services.openscad_exporter import TYPE_GEOM, ITEM_COLORS, ItemGeom3D


# ═══════════════════════════════════════════════════════════════════════════
#  Costanti di export
# ═══════════════════════════════════════════════════════════════════════════

EXPORT_COLLECTION = "Stage"
SHOOTING_POS_COLLECTION = "Shooting Positions"
WALKTHROUGH_EMPTY = "WalkthroughCam"
WALKTHROUGH_CURVE = "WalkthroughPath"
CAMERA_EYE_HEIGHT = 1.6  # altezza occhio tiratore (metri)
BACKSTOP_HEIGHT = 2.5     # altezza parapalle
BACKSTOP_THICKNESS = 0.3  # spessore parapalle
WALL_HEIGHT = 2.0         # altezza predefinita muri
GRID_LINE_Z = 0.005       # quota linee griglia


def _color_hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple:
    """Converte #RRGGBB in tupla (R, G, B, A) per Blender."""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b, alpha)


def _item_label(it: StageItem) -> str:
    """Etichetta descrittiva per l'item."""
    if it.label:
        return it.label
    return it.item_type.name.replace("_", " ").title()


# ═══════════════════════════════════════════════════════════════════════════
#  Helper Blender
# ═══════════════════════════════════════════════════════════════════════════

def _clean_scene() -> None:
    """Rimuove tutto dalla scena Blender."""
    import bpy
    # Seleziona e cancella tutto
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    # Pulisci data-blocks orfani
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in list(bpy.data.curves):
        if block.users == 0:
            bpy.data.curves.remove(block)
    for block in list(bpy.data.cameras):
        if block.users == 0:
            bpy.data.cameras.remove(block)
    for block in list(bpy.data.lights):
        if block.users == 0:
            bpy.data.lights.remove(block)


def _setup_units() -> None:
    """Configura unità metriche e scene scale."""
    import bpy
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'
    scene.frame_start = 1
    scene.frame_end = 120
    scene.render.fps = 30


def _create_collection(name: str, parent: Optional = None) -> "bpy.types.Collection":
    """Crea o recupera una collezione."""
    import bpy
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    if parent:
        parent.children.link(coll)
    else:
        bpy.context.scene.collection.children.link(coll)
    return coll


def _link_object(obj: "bpy.types.Object", collection: "bpy.types.Collection") -> None:
    """Linka un oggetto a una collezione, rimuovendolo dalla default."""
    import bpy
    # Rimuovi da tutte le collezioni
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    collection.objects.link(obj)


def _create_pbr_material(
    name: str,
    color_rgba: tuple = (0.8, 0.2, 0.2, 1.0),
    roughness: float = 0.5,
    metallic: float = 0.0,
    alpha: float = 1.0,
) -> "bpy.types.Material":
    """Crea materiale PBR con Principled BSDF.

    Args:
        name: Nome del materiale.
        color_rgba: Colore base (R, G, B, A).
        roughness: Rugosità superficiale (0=liscio, 1=ruvido).
        metallic: Metallic (0=non metallico, 1=metallico).

    Returns:
        Il materiale Blender creato.
    """
    import bpy
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Pulisci nodi default
    for node in list(nodes):
        nodes.remove(node)

    # Principled BSDF
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    bsdf.inputs['Base Color'].default_value = color_rgba
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Alpha'].default_value = alpha

    # Output
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    # Se alpha < 1, abilita trasparenza
    if alpha < 1.0:
        mat.blend_method = 'BLEND'
        mat.show_transparent_back = True

    return mat


def _create_primitive(
    primitive_type: str,
    name: str,
    location: tuple = (0, 0, 0),
    rotation: tuple = (0, 0, 0),
    scale: tuple = (1, 1, 1),
    material: Optional["bpy.types.Material"] = None,
    collection: Optional["bpy.types.Collection"] = None,
) -> "bpy.types.Object":
    """Crea un primitiva mesh in Blender.

    Args:
        primitive_type: 'cube', 'cylinder', 'cone', 'plane', 'circle'.
        name: Nome dell'oggetto.
        location: Posizione (x, y, z) in metri.
        rotation: Rotazione eulero (rx, ry, rz) in radianti.
        scale: Scala (sx, sy, sz).
        material: Materiale da applicare (opzionale).
        collection: Collezione di destinazione.

    Returns:
        L'oggetto Blender creato.
    """
    import bpy

    # Parametri di creazione specifici per primitiva
    prim_params = {
        'cube': {'size': 1},
        'cylinder': {'radius': 1, 'depth': 2},
        'cone': {'radius1': 1, 'depth': 2},
        'plane': {'size': 1},
        'circle': {'radius': 1, 'vertices': 32},
        'uv_sphere': {'radius': 1},
        'ico_sphere': {'radius': 1},
    }

    ops_map = {
        'cube': bpy.ops.mesh.primitive_cube_add,
        'cylinder': bpy.ops.mesh.primitive_cylinder_add,
        'cone': bpy.ops.mesh.primitive_cone_add,
        'plane': bpy.ops.mesh.primitive_plane_add,
        'circle': bpy.ops.mesh.primitive_circle_add,
        'uv_sphere': bpy.ops.mesh.primitive_uv_sphere_add,
        'ico_sphere': bpy.ops.mesh.primitive_ico_sphere_add,
    }

    op = ops_map.get(primitive_type)
    if op is None:
        raise ValueError(f"Primitiva sconosciuta: {primitive_type}")

    params = prim_params.get(primitive_type, {'size': 1}).copy()
    params['location'] = location
    params['rotation'] = rotation
    op(**params)

    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale

    if material:
        obj.data.materials.append(material)

    if collection:
        _link_object(obj, collection)

    return obj


# ═══════════════════════════════════════════════════════════════════════════
#  Generatori scena
# ═══════════════════════════════════════════════════════════════════════════

def _create_ground_and_grid(stage: Stage, collection: "bpy.types.Collection") -> None:
    """Crea pavimento e griglia metrica."""
    import bpy
    w, d = stage.width, stage.depth

    # Pavimento
    floor_mat = _create_pbr_material(
        "Floor", color_rgba=(0.55, 0.55, 0.55, 0.9),
        roughness=0.9, metallic=0.0,
    )
    _create_primitive(
        'plane', "Ground",
        location=(w / 2, d / 2, -0.05),
        scale=(w / 2, d / 2, 1),
        material=floor_mat,
        collection=collection,
    )

    # Griglia metrica (linee sottili)
    grid_mat = _create_pbr_material(
        "GridLine", color_rgba=(0.28, 0.33, 0.41, 0.5),
        roughness=0.5, metallic=0.0,
    )
    # Linee X (lungo larghezza)
    for i in range(int(d) + 1):
        y = i
        _create_primitive(
            'cube', f"GridX_{i}",
            location=(w / 2, y, GRID_LINE_Z),
            scale=(w / 2, 0.005, 0.002),
            material=grid_mat,
            collection=collection,
        )
    # Linee Y (lungo profondità)
    for i in range(int(w) + 1):
        x = i
        _create_primitive(
            'cube', f"GridY_{i}",
            location=(x, d / 2, GRID_LINE_Z),
            scale=(0.005, d / 2, 0.002),
            material=grid_mat,
            collection=collection,
        )


def _create_backstop(stage: Stage, collection: "bpy.types.Collection") -> None:
    """Crea parapalle (backstop) su tre lati."""
    w, d = stage.width, stage.depth
    bh = BACKSTOP_HEIGHT
    bt = BACKSTOP_THICKNESS
    h = bh / 2

    backstop_mat = _create_pbr_material(
        "Backstop", color_rgba=(0.36, 0.23, 0.12, 0.8),
        roughness=0.8, metallic=0.0,
    )

    # Fondo (down-range)
    _create_primitive(
        'cube', "Backstop_Rear",
        location=(w / 2, d + bt / 2, h),
        scale=((w + 2) / 2, bt / 2, h),
        material=backstop_mat,
        collection=collection,
    )
    # Sinistra
    _create_primitive(
        'cube', "Backstop_Left",
       location=(-bt / 2, d / 2, h),
        scale=(bt / 2, d / 2, h),
        material=backstop_mat,
        collection=collection,
    )
    # Destra
    _create_primitive(
        'cube', "Backstop_Right",
        location=(w + bt / 2, d / 2, h),
        scale=(bt / 2, d / 2, h),
        material=backstop_mat,
        collection=collection,
    )


def _create_direction_arrows(stage: Stage, collection: "bpy.types.Collection") -> None:
    """Crea frecce direzionali UP-RANGE e DOWN-RANGE."""
    w, d = stage.width, stage.depth

    # UP-RANGE (ingresso tiratore, verde)
    up_mat = _create_pbr_material(
        "Arrow_UpRange", color_rgba=(0.13, 0.77, 0.37, 1.0),
        roughness=0.4, metallic=0.0,
    )
    _create_primitive(
        'cone', "Arrow_UpRange",
        location=(w / 2, 0.8, 0.1),
        rotation=(math.radians(90), 0, 0),
        scale=(0.2, 0.4, 0.2),
        material=up_mat,
        collection=collection,
    )
    # Cono più piccolo per maggiore visibilità
    _create_primitive(
        'cone', "Arrow_UpRange_Small",
        location=(w / 2, 1.5, 0.1),
        rotation=(math.radians(90), 0, 0),
        scale=(0.12, 0.25, 0.12),
        material=up_mat,
        collection=collection,
    )

    # DOWN-RANGE (verso backstop, rosso)
    down_mat = _create_pbr_material(
        "Arrow_DownRange", color_rgba=(0.94, 0.27, 0.27, 1.0),
        roughness=0.4, metallic=0.0,
    )
    _create_primitive(
        'cone', "Arrow_DownRange",
        location=(w / 2, d - 0.8, 0.1),
        rotation=(math.radians(-90), 0, 0),
        scale=(0.2, 0.4, 0.2),
        material=down_mat,
        collection=collection,
    )
    _create_primitive(
        'cone', "Arrow_DownRange_Small",
        location=(w / 2, d - 1.5, 0.1),
        rotation=(math.radians(-90), 0, 0),
        scale=(0.12, 0.25, 0.12),
        material=down_mat,
        collection=collection,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Generatore item stage
# ═══════════════════════════════════════════════════════════════════════════

# Mapping ItemType → parametri costruzione Blender
# (primitive, material_override_fn, special_decorator_fn)
_ITEM_BUILDERS: dict[ItemType, dict] = {}


def _build_stage_item(
    it: StageItem,
    collection: "bpy.types.Collection",
) -> Optional["bpy.types.Object"]:
    """Costruisce un oggetto 3D per un StageItem."""
    import bpy
    geom = TYPE_GEOM.get(it.item_type, ItemGeom3D())
    color_hex = ITEM_COLORS.get(it.item_type, "#808080")
    color_rgba = _color_hex_to_rgba(color_hex)
    label = _item_label(it)
    name = f"{label}_{it.id}"

    # Dimensioni 3D:
    #   X = it.width (orizzontale, es. lunghezza muro)
    #   Y = geom.sy   (spessore/profondità, dal tipo)
    #   Z = geom.sz   (altezza verticale, dal tipo)
    sx = it.width if it.width > 0 else geom.sx
    sy = geom.sy
    sz = geom.sz

    # Posizione: stage (x,y) → Blender (x, y, z)
    # Stage: x=right, y=down-range, z=up
    px = it.x
    py = it.y
    pz = sz / 2.0  # base a terra, centro geometrico a metà altezza

    # Rotazione: stage rotation è intorno all'asse Z (gradi → radianti)
    rot_z_rad = math.radians(it.rotation)

    # Crea materiale
    roughness = 0.5
    metallic = 0.0
    alpha = 1.0

    # Regola aspetto per tipo
    if it.item_type in (ItemType.WALL, ItemType.HARD_COVER):
        roughness = 0.7
    elif it.item_type in (ItemType.POPPER, ItemType.STEEL_TARGET, ItemType.METAL_PLATE):
        roughness = 0.3
        metallic = 0.8
    elif it.item_type in (ItemType.BARRIER, ItemType.SOFT_COVER):
        alpha = 0.4
    elif it.item_type in (ItemType.SWINGER, ItemType.DROP_TURNER, ItemType.MOVER):
        roughness = 0.6

    mat_name = f"Mat_{name}"
    material = _create_pbr_material(
        mat_name, color_rgba=color_rgba,
        roughness=roughness, metallic=metallic, alpha=alpha,
    )

    # ── Crea geometria ──────────────────────────────────────────

    if it.item_type == ItemType.FAULT_LINE:
        # Fault line: striscia rossa molto bassa sul pavimento
        fl_sx = it.width if it.width > 0 else 1.0
        obj = _create_primitive(
            'cube', name,
            location=(px, py, 0.03),
            rotation=(0, 0, rot_z_rad),
            scale=(fl_sx / 2, 0.01, 0.03),
            material=material,
            collection=collection,
        )

    elif geom.shape == "cylinder":
        # Cilindro verticale: per popper e piatti metallici
        r = sx / 2 if sx > 0 else 0.15
        obj = _create_primitive(
            'cylinder', name,
            location=(px, py, r),
            rotation=(0, 0, rot_z_rad),
            scale=(r, r, sy / 2),
            material=material,
            collection=collection,
        )

    else:
        # Cubo standard: muri, bersagli, barriere, porte, coperture
        obj = _create_primitive(
            'cube', name,
            location=(px, py, pz),
            rotation=(0, 0, rot_z_rad),
            scale=(sx / 2, sy / 2, sz / 2),
            material=material,
            collection=collection,
        )

    # ── Proprietà custom ────────────────────────────────────────
    obj["item_id"] = it.id
    obj["item_type"] = it.item_type.name
    obj["item_label"] = label

    # ── Decorazioni speciali ────────────────────────────────────
    if it.item_type == ItemType.NO_SHOOT:
        _add_no_shoot_cross(px, py, pz, sx, sy, collection)

    elif it.item_type == ItemType.SWINGER:
        amp = it.properties.get("amplitude", 45)
        _add_swinger_arc(px, py, pz, sx, amp, rot_z_rad, collection)

    elif it.item_type == ItemType.MOVER:
        dist = it.properties.get("distance", 3.0)
        _add_mover_track(px, py, pz, dist, rot_z_rad, collection)

    elif it.item_type == ItemType.DROP_TURNER:
        _add_drop_turner_indicator(px, py, pz, sx, collection)

    return obj


def _add_no_shoot_cross(
    cx: float, cy: float, cz: float,
    size_x: float, size_y: float,
    collection: "bpy.types.Collection",
) -> None:
    """Aggiunge una X rossa sul bersaglio no-shoot."""
    cross_mat = _create_pbr_material(
        "NoShoot_Cross", color_rgba=(0.86, 0.15, 0.15, 1.0),
        roughness=0.5, metallic=0.0,
    )
    half = size_x * 0.35
    thick = 0.02

    # Prima diagonale (\)
    _create_primitive(
        'cube', "NoShoot_X1",
        location=(cx, cy, cz + 0.01),
        scale=(half / 2, thick / 2, thick / 2),
        rotation=(0, 0, math.radians(45)),
        material=cross_mat,
        collection=collection,
    )
    # Seconda diagonale (/)
    _create_primitive(
        'cube', "NoShoot_X2",
        location=(cx, cy, cz + 0.01),
        scale=(half / 2, thick / 2, thick / 2),
        rotation=(0, 0, math.radians(-45)),
        material=cross_mat,
        collection=collection,
    )


def _add_swinger_arc(
    cx: float, cy: float, cz: float,
    size: float, amplitude: float,
    base_rot: float,
    collection: "bpy.types.Collection",
) -> None:
    """Aggiunge indicatore di oscillazione per swinger (arco viola)."""
    import bpy
    arc_mat = _create_pbr_material(
        "Swinger_Arc", color_rgba=(0.66, 0.33, 0.97, 0.6),
        roughness=0.3, metallic=0.3,
    )

    # Crea un arco usando un cilindro segmentato a mezzaluna
    # Usiamo una sfera schiacciata come arco approssimato
    arc_radius = size * 0.8
    _create_primitive(
        'cylinder', "Swinger_Arc",
        location=(cx, cy, cz + 0.01),
        rotation=(math.radians(90), 0, base_rot),
        scale=(arc_radius, 0.005, arc_radius * 0.3),
        material=arc_mat,
        collection=collection,
    )


def _add_mover_track(
    cx: float, cy: float, cz: float,
    distance: float, base_rot: float,
    collection: "bpy.types.Collection",
) -> None:
    """Aggiunge linea di traiettoria per mover."""
    track_mat = _create_pbr_material(
        "Mover_Track", color_rgba=(0.97, 0.45, 0.09, 0.6),
        roughness=0.5, metallic=0.0,
    )
    half_dist = distance / 2
    _create_primitive(
        'cube', "Mover_Track",
        location=(cx, cy, cz + 0.01),
        rotation=(0, 0, base_rot),
        scale=(half_dist, 0.01, 0.005),
        material=track_mat,
        collection=collection,
    )


def _add_drop_turner_indicator(
    cx: float, cy: float, cz: float,
    size: float,
    collection: "bpy.types.Collection",
) -> None:
    """Aggiunge indicatore di caduta per drop turner."""
    ind_mat = _create_pbr_material(
        "DropTurner_Ind", color_rgba=(0.3, 0.3, 0.3, 1.0),
        roughness=0.5, metallic=0.0,
    )
    # Piccola freccia verso il basso
    _create_primitive(
        'cone', "DropTurner_Arrow",
        location=(cx, cy - size * 0.3, cz + 0.02),
        rotation=(math.radians(-90), 0, 0),
        scale=(0.04, 0.08, 0.04),
        material=ind_mat,
        collection=collection,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Shooting positions
# ═══════════════════════════════════════════════════════════════════════════

def _create_shooting_positions(
    stage: Stage,
    stage_collection: "bpy.types.Collection",
    sp_collection: "bpy.types.Collection",
) -> tuple[list, Optional["bpy.types.Object"]]:
    """Crea telecamere e marcatori per ogni shooting position.

    Returns:
        (lista telecamere, camera principale/path empty)
    """
    import bpy
    cameras = []

    if not stage.shooting_positions:
        # Nessuna shooting position definita — crea una camera default
        cam = _create_default_camera(stage, sp_collection)
        return [cam], None

    # Calcola il centro dell'area di tiro
    cx = stage.width / 2
    cy = stage.depth / 2
    poly = stage.properties.get("perimeter_poly")
    if poly:
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)

    for i, sp in enumerate(stage.shooting_positions):
        is_start = sp.is_start
        sp_label = sp.label or ("Start" if is_start else f"Pos {i + 1}")
        cam_name = f"Cam_{sp_label}"

        # Telecamera a occhio del tiratore
        bpy.ops.object.camera_add(
            location=(sp.x, sp.y, CAMERA_EYE_HEIGHT),
        )
        cam = bpy.context.active_object
        cam.name = cam_name
        cam.data.lens = 35  # grandangolo per visione periferica
        cam.data.type = 'PERSP'
        cam.data.clip_end = 100.0

        # Track To constraint verso centro area tiro
        # Crea un target empty
        target_name = f"Target_{sp_label}"
        target = bpy.data.objects.new(target_name, None)
        target.location = (cx, cy, CAMERA_EYE_HEIGHT * 0.5)
        sp_collection.objects.link(target)

        track = cam.constraints.new(type='TRACK_TO')
        track.target = target
        track.track_axis = 'TRACK_NEGATIVE_Z'
        track.up_axis = 'UP_Y'

        _link_object(cam, sp_collection)

        # Marker a terra (disco colorato)
        marker_mat = _create_pbr_material(
            f"Marker_{sp_label}",
            color_rgba=(0.09, 0.75, 0.34, 0.7) if is_start else (0.23, 0.49, 0.96, 0.7),
            roughness=0.5, metallic=0.0,
        )
        _create_primitive(
            'cylinder', f"Marker_{sp_label}",
            location=(sp.x, sp.y, 0.02),
            scale=(0.3, 0.3, 0.02),
            material=marker_mat,
            collection=sp_collection,
        )

        # Testo etichetta (opzionale)
        cameras.append(cam)

    # Imposta la prima camera come attiva
    if cameras:
        bpy.context.scene.camera = cameras[0]

    return cameras, None


def _create_default_camera(
    stage: Stage,
    collection: "bpy.types.Collection",
) -> "bpy.types.Object":
    """Crea una camera isometrica di default."""
    import bpy
    w, d = stage.width, stage.depth
    cx, cy = w / 2, d / 2

    # Camera dall'alto in posizione isometrica
    cam_dist = max(w, d) * 1.5
    bpy.ops.object.camera_add(
        location=(cx - cam_dist * 0.5, cy - cam_dist * 0.5, cam_dist * 0.7),
    )
    cam = bpy.context.active_object
    cam.name = "Cam_Default"
    cam.data.lens = 50
    cam.data.type = 'PERSP'
    cam.data.clip_end = 200.0

    # Track al centro
    target = bpy.data.objects.new("Target_Default", None)
    target.location = (cx, cy, 0)
    collection.objects.link(target)

    track = cam.constraints.new(type='TRACK_TO')
    track.target = target
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    _link_object(cam, collection)
    bpy.context.scene.camera = cam
    return cam


# ═══════════════════════════════════════════════════════════════════════════
#  Walkthrough animation
# ═══════════════════════════════════════════════════════════════════════════

def _create_walkthrough(
    stage: Stage,
    cameras: list["bpy.types.Object"],
    collection: "bpy.types.Collection",
) -> None:
    """Crea animazione walkthrough lungo le shooting position.

    Anima la camera principale (o un empty genitore) lungo un percorso
    che collega tutte le shooting position in sequenza. Ogni posizione
    ha una pausa di 2 secondi, con 1 secondo di transizione.
    """
    import bpy
    if len(stage.shooting_positions) < 2:
        return

    fps = bpy.context.scene.render.fps
    positions = stage.shooting_positions

    # Crea una curva di percorso
    curve_data = bpy.data.curves.new(name=WALKTHROUGH_CURVE, type='CURVE')
    curve_data.dimensions = '3D'
    spline = curve_data.splines.new('POLY')
    point_count = len(positions)
    spline.points.add(point_count - 1)

    for i, sp in enumerate(positions):
        spline.points[i].co = (sp.x, sp.y, CAMERA_EYE_HEIGHT, 1)
        spline.points[i].radius = 1.0

    curve_obj = bpy.data.objects.new(WALKTHROUGH_CURVE, curve_data)
    collection.objects.link(curve_obj)

    # Crea un empty che segue il percorso
    import bpy
    empty_data = bpy.data.objects.new(WALKTHROUGH_EMPTY, None)
    empty_data.empty_display_type = 'SPHERE'
    empty_data.location = (positions[0].x, positions[0].y, CAMERA_EYE_HEIGHT)
    collection.objects.link(empty_data)

    # Follow Path constraint
    follow = empty_data.constraints.new(type='FOLLOW_PATH')
    follow.target = curve_obj
    follow.forward_axis = 'FORWARD_Y'
    follow.up_axis = 'UP_Z'
    follow.use_fixed_location = True

    # Anima il factor offset lungo il percorso
    total_frames = (len(positions) - 1) * 3 * fps  # 3 secondi per segmento
    bpy.context.scene.frame_end = max(bpy.context.scene.frame_end, total_frames + 10)

    empty_data.location = (positions[0].x, positions[0].y, CAMERA_EYE_HEIGHT)
    empty_data.keyframe_insert(data_path='location', frame=1)

    follow.offset_factor = 0.0
    follow.keyframe_insert(data_path='offset_factor', frame=1)
    follow.offset_factor = 1.0
    follow.keyframe_insert(data_path='offset_factor', frame=total_frames)

    # L'utente potrà selezionare manualmente le camere nella collezione
    # "Shooting Positions" e premere NumPad 0 per la vista da quella camera.
    # Il walkthrough segue il percorso delle posizioni di tiro in ordine.


# ═══════════════════════════════════════════════════════════════════════════
#  Luci e ambiente
# ═══════════════════════════════════════════════════════════════════════════

def _setup_lights(stage: Stage) -> None:
    """Configura illuminazione a 3 punti e ambiente."""
    import bpy
    w, d = stage.width, stage.depth
    cx, cy = w / 2, d / 2
    max_dim = max(w, d)

    # Key light (area, dall'alto a destra)
    bpy.ops.object.light_add(
        type='AREA',
        location=(cx + max_dim * 0.5, cy - max_dim * 0.3, max_dim * 0.8),
    )
    key = bpy.context.active_object
    key.name = "Light_Key"
    key.data.energy = 200
    key.data.size = 5
    key.rotation_euler = (math.radians(50), 0, math.radians(45))

    # Fill light (area, da sinistra)
    bpy.ops.object.light_add(
        type='AREA',
        location=(cx - max_dim * 0.4, cy + max_dim * 0.2, max_dim * 0.4),
    )
    fill = bpy.context.active_object
    fill.name = "Light_Fill"
    fill.data.energy = 80
    fill.data.size = 3
    fill.rotation_euler = (math.radians(30), 0, math.radians(-30))

    # Rim light (retro, per silhouette)
    bpy.ops.object.light_add(
        type='AREA',
        location=(cx, cy + max_dim * 0.6, max_dim * 0.5),
    )
    rim = bpy.context.active_object
    rim.name = "Light_Rim"
    rim.data.energy = 120
    rim.data.size = 4
    rim.rotation_euler = (math.radians(20), 0, math.radians(180))

    # Ambiente leggero (world)
    world = bpy.context.scene.world
    world.use_nodes = True
    bg = world.node_tree.nodes.get('Background')
    if bg:
        bg.inputs['Strength'].default_value = 0.3


def _setup_viewport() -> None:
    """Configura viewport per navigazione ottimale."""
    import bpy
    # Imposta la vista 3D in modalità solid (non in background)
    # Le impostazioni viewport non sono disponibili in background mode
    pass


# ═══════════════════════════════════════════════════════════════════════════
#  API pubblica
# ═══════════════════════════════════════════════════════════════════════════

def export_stage_to_blend(
    stage: Stage,
    output_path: Path,
    include_backstop: bool = True,
    include_grid: bool = True,
    include_arrows: bool = True,
    include_lights: bool = True,
    include_walkthrough: bool = True,
    overwrite: bool = True,
) -> Path:
    """Genera un file .blend navigabile dello stage IPSC.

    Crea una scena Blender completa con:
    - Geometria 3D di tutti gli oggetti (muri, bersagli, barriere, etc.)
    - Materiali PBR con colori IPSC-conformi
    - Pavimento con griglia metrica
    - Parapalle (backstop) su tre lati
    - Freece direzionali UP-RANGE / DOWN-RANGE
    - Telecamere a ogni shooting position
    - Walkthrough animato lungo le posizioni di tiro
    - Illuminazione professionale a 3 punti

    Args:
        stage: Lo stage IPSC da esportare.
        output_path: Percorso del file .blend da creare.
        include_backstop: Includi parapalle.
        include_grid: Includi griglia a terra.
        include_arrows: Includi frecce direzionali.
        include_lights: Includi illuminazione.
        include_walkthrough: Includi walkthrough animato.
        overwrite: Sovrascrivi se il file esiste.

    Returns:
        Il percorso del file .blend creato.

    Raises:
        FileExistsError: Se il file esiste e overwrite=False.
        ImportError: Se bpy non è disponibile (Blender non installato).
    """
    try:
        import bpy
    except ImportError:
        raise ImportError(
            "bpy (Blender Python API) non trovato. "
            "Questo modulo richiede Blender con bpy installato."
        )

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"File già esistente: {output_path}")

    # ─── Setup ────────────────────────────────────────────────
    _clean_scene()
    _setup_units()

    # Collezioni
    stage_coll = _create_collection(EXPORT_COLLECTION)
    sp_coll = _create_collection(SHOOTING_POS_COLLECTION)

    # ─── Ambiente ─────────────────────────────────────────────
    if include_grid:
        _create_ground_and_grid(stage, stage_coll)
    if include_backstop:
        _create_backstop(stage, stage_coll)
    if include_arrows:
        _create_direction_arrows(stage, stage_coll)

    # ─── Oggetti stage ────────────────────────────────────────
    for it in stage.items:
        _build_stage_item(it, stage_coll)

    # ─── Shooting positions e telecamere ──────────────────────
    cameras, _ = _create_shooting_positions(stage, stage_coll, sp_coll)

    # ─── Walkthrough ─────────────────────────────────────────
    if include_walkthrough and cameras:
        _create_walkthrough(stage, cameras, sp_coll)

    # ─── Luci ────────────────────────────────────────────────
    if include_lights:
        _setup_lights(stage)

    # ─── Salva ────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    return output_path


def export_stage_to_blend_and_open(
    stage: Stage,
    output_path: Optional[Path] = None,
    blender_path: Optional[str] = None,
    **kwargs,
) -> Path:
    """Esporta lo stage in .blend e lo apre in Blender.

    Args:
        stage: Lo stage IPSC da esportare.
        output_path: Percorso del file .blend (default: stage_export.blend in CWD).
        blender_path: Percorso dell'eseguibile Blender (default: cerca in PATH).
        **kwargs: Opzioni aggiuntive per export_stage_to_blend.

    Returns:
        Il percorso del file .blend creato.

    Raises:
        FileNotFoundError: Se Blender non è trovato.
    """
    if output_path is None:
        output_path = Path.cwd() / "stage_export.blend"

    # Esporta
    export_stage_to_blend(stage, output_path, **kwargs)

    # Trova Blender
    if blender_path is None:
        blender_path = shutil.which("blender")
        if blender_path is None:
            # Prova percorsi comuni
            for candidate in [
                "/usr/bin/blender",
                "/usr/local/bin/blender",
                "/snap/bin/blender",
                "C:\\Program Files\\Blender Foundation\\Blender\\blender.exe",
            ]:
                if Path(candidate).exists():
                    blender_path = candidate
                    break

    if blender_path is None:
        raise FileNotFoundError(
            "Blender non trovato. Installa Blender o specifica il percorso."
        )

    # Apri Blender con il file
    subprocess.Popen([blender_path, str(output_path)])

    return output_path


def blender_available() -> bool:
    """Verifica se Blender è installato e accessibile."""
    try:
        import bpy
        return True
    except ImportError:
        return shutil.which("blender") is not None


def get_blender_path() -> Optional[str]:
    """Restituisce il percorso di Blender, se trovato."""
    path = shutil.which("blender")
    if path:
        return path
    for candidate in [
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/snap/bin/blender",
    ]:
        if Path(candidate).exists():
            return candidate
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  CLI entry point (invocato da subprocess da main app)
# ═══════════════════════════════════════════════════════════════════════════

def _write_stage_json(stage, path: Path) -> None:
    """Serializza uno stage in JSON per passaggio a subprocess."""
    import json
    from services.serializer import stage_to_dict
    data = stage_to_dict(stage)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_stage_json(path: Path):
    """Deserializza uno stage da JSON (lato bpy/subprocess).

    Non può usare il serializer perché richiede PySide6.
    Ricostruisce manualmente Stage, StageItem, ShootingPosition.
    """
    import json
    from core.models import Stage, StageItem, ItemType, ShootingPosition, CourseType, Division

    data = json.loads(path.read_text(encoding="utf-8"))
    stage = Stage(
        name=data.get("name", "Stage"),
        width=data.get("width", 20.0),
        depth=data.get("depth", 15.0),
    )

    ct = data.get("course_type")
    if ct:
        try:
            stage.course_type = CourseType(ct)
        except ValueError:
            pass

    dv = data.get("division")
    if dv:
        try:
            stage.division = Division(dv)
        except ValueError:
            pass

    stage.properties = dict(data.get("properties", {}))

    for item_data in data.get("items", []):
        try:
            it_type = ItemType[item_data["type"]]
        except (KeyError, ValueError):
            continue
        item = StageItem(
            id=item_data.get("id", 0),
            item_type=it_type,
            x=item_data.get("x", 0.0),
            y=item_data.get("y", 0.0),
            width=item_data.get("width", 1.0),
            height=item_data.get("height", 1.0),
            rotation=item_data.get("rotation", 0.0),
            color=item_data.get("color", "#808080"),
            label=item_data.get("label", ""),
            properties=dict(item_data.get("properties", {})),
        )
        stage.items.append(item)

    if stage.items:
        stage._next_id = max(it.id for it in stage.items) + 1

    for sp_data in data.get("shooting_positions", []):
        sp = ShootingPosition(
            id=sp_data.get("id", 0),
            x=sp_data.get("x", 0.0),
            y=sp_data.get("y", 0.0),
            label=sp_data.get("label", ""),
            is_start=sp_data.get("is_start", False),
            angle=sp_data.get("angle", 90.0),
            properties=dict(sp_data.get("properties", {})),
        )
        stage.shooting_positions.append(sp)

    return stage


def _find_blender_python() -> Optional[str]:
    """Trova l'eseguibile Blender per esecuzione headless."""
    blender = get_blender_path()
    if blender:
        return blender
    return None


def export_via_subprocess(
    stage,
    output_path: Path,
    json_path: Optional[Path] = None,
    blender_python: Optional[str] = None,
    **kwargs,
) -> Path:
    """Esporta stage in .blend via subprocess usando Blender headless.

    Questa funzione è chiamabile dall'app principale (che NON ha bpy).
    Salva lo stage in JSON, lancia Blender in background che esegue
    questo stesso modulo come script per generare il .blend.

    Args:
        stage: Lo stage IPSC da esportare.
        output_path: Percorso del file .blend.
        json_path: Percorso per il JSON temporaneo (default: auto).
        blender_python: Eseguibile Blender (default: cerca in PATH).
        **kwargs: Opzioni (include_backstop, include_grid, etc.).

    Returns:
        Il percorso del file .blend creato.
    """
    import subprocess

    if json_path is None:
        json_path = output_path.with_suffix(".json")
    if blender_python is None:
        blender_python = _find_blender_python()

    if blender_python is None:
        raise FileNotFoundError(
            "Blender non trovato. Installa Blender o specifica il percorso."
        )

    # Serializza stage in JSON
    _write_stage_json(stage, json_path)

    # Prepara argomenti opzioni
    opt_args = []
    for key, default in [
        ("include_backstop", True),
        ("include_grid", True),
        ("include_arrows", True),
        ("include_lights", True),
        ("include_walkthrough", True),
    ]:
        val = kwargs.get(key, default)
        if not val:
            opt_args.append(f"--no-{key.replace('_', '-')}")

    # Trova il path di questo script
    script_path = Path(__file__).resolve()

    # Costruisci comando: blender -b -P exporter.py -- --input stage.json --output stage.blend
    cmd = [
        blender_python,
        "-b",  # background mode
        "-P", str(script_path),  # esegui questo script
        "--",
        "--input", str(json_path),
        "--output", str(output_path),
    ] + opt_args

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Export Blender fallito (exit={result.returncode}):\n"
            f"{result.stderr.strip()}"
        )

    # Pulisci JSON temporaneo
    if json_path.exists():
        json_path.unlink()

    if not output_path.exists():
        raise RuntimeError(
            f"Export Blender fallito: file non creato.\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )

    return output_path


def export_via_subprocess_and_open(
    stage,
    output_path: Optional[Path] = None,
    **kwargs,
) -> Path:
    """Esporta stage in .blend e lo apre in Blender GUI."""
    if output_path is None:
        output_path = Path.cwd() / "stage_export.blend"

    export_via_subprocess(stage, output_path, **kwargs)

    blender_path = get_blender_path()
    if blender_path:
        subprocess.Popen([blender_path, str(output_path)])

    return output_path


# ═══════════════════════════════════════════════════════════════════════════
#  CLI: eseguito da blender -b -P blender_exporter.py -- --input ... --output ...
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """Entry point per esecuzione headless da subprocess.

    Uso:
        blender -b -P services/blender_exporter.py -- \\
            --input stage.json --output stage.blend
    """
    import sys

    # Parsing argomenti
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]

    input_path = None
    output_path = None
    opts = {
        "include_backstop": True,
        "include_grid": True,
        "include_arrows": True,
        "include_lights": True,
        "include_walkthrough": True,
    }

    i = 0
    while i < len(args):
        if args[i] == "--input" and i + 1 < len(args):
            input_path = Path(args[i + 1])
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_path = Path(args[i + 1])
            i += 2
        elif args[i].startswith("--no-"):
            key = args[i][5:].replace("-", "_")
            if key in opts:
                opts[key] = False
            i += 1
        else:
            i += 1

    if not input_path or not output_path:
        print("Uso: blender -b -P blender_exporter.py -- --input stage.json --output stage.blend",
              file=sys.stderr)
        sys.exit(1)

    print(f"Import stage da: {input_path}")
    stage = _read_stage_json(input_path)
    print(f"  Stage: {stage.name} ({stage.width}m x {stage.depth}m), "
          f"{len(stage.items)} items, {len(stage.shooting_positions)} posizioni")

    print(f"Export in: {output_path}")
    export_stage_to_blend(stage, output_path, **opts)
    print(f"Esportato: {output_path}")
