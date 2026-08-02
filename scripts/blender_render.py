"""
Render headless dell'anteprima 3D di uno stage OpenTDS con Blender EEVEE.

Legge una descrizione di scena JSON prodotta da
``services.blender_exporter.py`` e costruisce geometria, materiali,
luci e camera, poi renderizza in PNG (e salva opzionalmente il .blend).

Quando viene salvato il .blend, lo script lo rende navigabile in
prima persona: telecamere bookmark alle posizioni di tiro (NAV_Start /
NAV_PosN), viewport iniziale alla partenza e parametri di Walk
Navigation configurati (Shift+~ nel viewport, WASD per muoversi).

Esecuzione (da root del progetto):
    blender -b -P scripts/blender_render.py -- scene.json out.png [out.blend]

Dipende solo dall'API bpy di Blender: nessun import dal venv del progetto.
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# ─── Config ───────────────────────────────────────────────────────────
CONFIG = {
    "engine": "BLENDER_EEVEE",  # fallback automatico a EEVEE_NEXT/EEVEE
    "resolution": (1920, 1080),
    "samples": 64,
    "solidify": 0.01,  # spessore silhouette SVG importate
}

# Parametri Principled BSDF per famiglia di materiale.
MATERIAL_PARAMS = {
    "concrete": {"roughness": 0.95, "metallic": 0.0},
    "gravel": {"roughness": 1.0, "metallic": 0.0},
    "stone": {"roughness": 0.9, "metallic": 0.0},
    "brick": {"roughness": 0.85, "metallic": 0.0},
    "wood": {"roughness": 0.55, "metallic": 0.0},
    "solid": {"roughness": 0.45, "metallic": 0.0},
    "fault": {"roughness": 0.4, "metallic": 0.0, "emission": 0.7},
    "metal": {"roughness": 0.35, "metallic": 0.8},
    "paper": {"roughness": 0.85, "metallic": 0.0},
}

_material_cache: dict[str, bpy.types.Material] = {}


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """#RRGGBB → tuple RGB 0..1."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def create_material(kind: str, hex_color: str) -> bpy.types.Material:
    """Materiale Principled BSDF per (famiglia, colore), con cache."""
    key = f"{kind}|{hex_color}"
    if key in _material_cache:
        return _material_cache[key]

    mat = bpy.data.materials.new(key)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF") or nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*hex_to_rgb(hex_color), 1.0)
    params = MATERIAL_PARAMS.get(kind, {"roughness": 0.5, "metallic": 0.0})
    bsdf.inputs["Roughness"].default_value = params.get("roughness", 0.5)
    bsdf.inputs["Metallic"].default_value = params.get("metallic", 0.0)
    if params.get("emission"):
        bsdf.inputs["Emission Color"].default_value = (*hex_to_rgb(hex_color), 1.0)
        bsdf.inputs["Emission Strength"].default_value = params["emission"]
    _material_cache[key] = mat
    return mat


def set_material(obj: bpy.types.Object, data: dict) -> None:
    """Assegna il materiale (famiglia, colore) all'oggetto."""
    mat = create_material(data.get("material", "solid"), data.get("color", "#808080"))
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


# ─── Scene setup ──────────────────────────────────────────────────────


def clean_scene() -> None:
    """Rimuove tutto dalla scena (oggetti, mesh, materiali, curve)."""
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in list(bpy.data.materials):
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in list(bpy.data.curves):
        if block.users == 0:
            bpy.data.curves.remove(block)


def setup_world() -> None:
    """Sfondo cielo chiaro per EEVEE (luce ambientale diffusa)."""
    world = bpy.data.worlds.new("StageWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.60, 0.76, 0.96, 1.0)
    bg.inputs["Strength"].default_value = 0.5
    bpy.context.scene.world = world


# ─── Object builders ──────────────────────────────────────────────────


def add_box(obj: dict) -> bpy.types.Object:
    """Scatola con rotazione solo attorno a Y (tutti gli oggetti dello stage)."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=obj["position"])
    me = bpy.context.active_object
    me.name = obj["id"]
    me.scale = tuple(obj["size"])
    me.rotation_euler = (0.0, math.radians(obj.get("rotation_y", 0.0)), 0.0)
    set_material(me, obj)
    return me


def add_cylinder_v(obj: dict) -> bpy.types.Object:
    """Cilindro con asse verticale (Y): stecche, pali, cerchi a terra."""
    bpy.ops.mesh.primitive_cylinder_add(
        radius=obj["radius"], depth=obj["height"], location=obj["position"]
    )
    me = bpy.context.active_object
    me.name = obj["id"]
    me.rotation_euler = (math.radians(90), 0.0, 0.0)  # asse Z → Y (verticale)
    set_material(me, obj)
    return me


def add_board_cylinder(obj: dict) -> bpy.types.Object:
    """Disco verticale (metallici): asse = direzione di faccia."""
    bpy.ops.mesh.primitive_cylinder_add(
        radius=obj["radius"], depth=obj["thickness"], location=obj["position"]
    )
    me = bpy.context.active_object
    me.name = obj["id"]
    me.rotation_euler = (0.0, math.radians(obj["rotation_y"]), 0.0)
    set_material(me, obj)
    return me


def add_polygon(obj: dict) -> bpy.types.Object:
    """Poligono piatto a terra (overlay area di tiro)."""
    verts = [(p[0], obj.get("height", 0.0), p[1]) for p in obj["points"]]
    # Assicura che la normale punti verso l'alto.
    if len(verts) >= 3:
        v0, v1, v2 = verts[0], verts[1], verts[2]
        n = (
            (v1[0] - v0[0]) * (v2[2] - v0[2]) - (v1[2] - v0[2]) * (v2[0] - v0[0]),
            0.0,
            (v1[2] - v0[2]) * (v2[1] - v0[1]) - (v1[1] - v0[1]) * (v2[2] - v0[2]),
        )
        if n[0] * n[0] + n[2] * n[2] > 0 and n[0] < 0:
            verts = verts[::-1]
    mesh = bpy.data.meshes.new(obj["id"])
    mesh.from_pydata(verts, [], [list(range(len(verts)))])
    mesh.update()
    me = bpy.data.objects.new(obj["id"], mesh)
    bpy.context.collection.objects.link(me)
    set_material(me, obj)
    return me


def _fit_svg_to_size(me: bpy.types.Object, target_w: float, target_h: float) -> None:
    """Centra l'oggetto, lo ruota piano e lo scala alle dimensioni bersaglio."""
    me.location = (0.0, 0.0, 0.0)
    me.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.objects.active = me
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    dims = me.dimensions
    if dims.y > 1e-6:
        s = target_h / dims.y
        me.scale = (s, s, s)  # scala uniforme: aspetto SVG preservato
    me.location = (0.0, -target_h / 2, 0.0)  # base del bersaglio a terra


def add_svg_board(obj: dict) -> bpy.types.Object:
    """Pannello bersaglio: importa la silhouette SVG realistica del target.

    Se l'import SVG non è disponibile o fallisce, ripiega su una scatola
    piatta con le dimensioni del pannello.
    """
    svg = obj.get("svg")
    if not svg or not Path(svg).exists():
        return _add_plain_board(obj)

    before = {o.name for o in bpy.data.objects}
    try:
        bpy.ops.import_curve.svg(filepath=svg)
    except Exception as exc:  # operatore non disponibile o SVG invalido
        print(f"⚠ import SVG fallito per {obj['id']}: {exc}")
        return _add_plain_board(obj)

    imported = [o for o in bpy.data.objects if o.name not in before]
    if not imported:
        return _add_plain_board(obj)

    bpy.ops.object.select_all(action="DESELECT")
    for o in imported:
        o.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    bpy.ops.object.convert(target="MESH")
    if len(imported) > 1:
        bpy.ops.object.join()
    me = bpy.context.active_object
    me.name = obj["id"]

    w, _, h = obj["size"]
    _fit_svg_to_size(me, w, h)
    me.rotation_euler = (0.0, math.radians(obj["rotation_y"]), 0.0)
    me.location = obj["position"]
    me.modifiers.new("Solidify", "SOLIDIFY").thickness = CONFIG["solidify"]
    # I materiali importati dall'SVG (silhouette + zone) restano invariati.
    return me


def _add_plain_board(obj: dict) -> bpy.types.Object:
    """Pannello piatto senza texture (fallback)."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=obj["position"])
    me = bpy.context.active_object
    me.name = obj["id"]
    me.scale = tuple(obj["size"])
    me.rotation_euler = (0.0, math.radians(obj["rotation_y"]), 0.0)
    set_material(me, obj)
    return me


def build_object(obj: dict) -> bpy.types.Object | None:
    """Dispatcher kind → builder."""
    kind = obj["kind"]
    if kind == "box":
        return add_box(obj)
    if kind == "cylinder_v":
        return add_cylinder_v(obj)
    if kind == "board_box":
        return add_svg_board(obj)
    if kind == "board_cylinder":
        return add_board_cylinder(obj)
    if kind == "polygon":
        return add_polygon(obj)
    print(f"⚠ kind sconosciuto: {kind} ({obj.get('id')})")
    return None


# ─── Lights, camera, render ───────────────────────────────────────────


def setup_lights(lights: list[dict]) -> None:
    """Sole direzionale + area light di fill."""
    for light in lights:
        kind = light["kind"]
        if kind == "sun":
            bpy.ops.object.light_add(type="SUN", location=(0.0, 20.0, 0.0))
            sun = bpy.context.active_object
            sun.data.energy = light["energy"]
            sun.data.color = hex_to_rgb(light["color"])
            direction = Vector(light["direction"]).normalized()
            sun.rotation_mode = "QUATERNION"
            sun.rotation_quaternion = direction.to_track_quat("-Z", "Y")
        elif kind == "area":
            bpy.ops.object.light_add(type="AREA", location=light["position"])
            area = bpy.context.active_object
            area.data.energy = light["energy"]
            area.data.size = light.get("size", 3.0)
            area.data.color = hex_to_rgb(light["color"])
            area.rotation_euler = (math.radians(90), 0.0, 0.0)  # punta verso il basso


def setup_camera(camera: dict) -> None:
    """Camera statica con TRACK_TO verso il centro dell'area di tiro."""
    cam_data = bpy.data.cameras.new("StageCamera")
    cam = bpy.data.objects.new("StageCamera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = camera["position"]
    cam.data.lens = camera["lens"]

    target = bpy.data.objects.new("CamTarget", None)
    bpy.context.collection.objects.link(target)
    target.location = camera["target"]

    track = cam.constraints.new(type="TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.context.scene.camera = cam


# ─── Navigazione interattiva (walk mode) ─────────────────────────────

EYE_HEIGHT = 1.6  # altezza occhi del tiratore (m)
WALK_SPEED = 4.0  # velocità di camminata (m/s)

NAV_HELP_TEXT = (
    "Walk: Shift+~ · WASD/frecce muovi · mouse guarda · scroll velocità\n"
    "Tab vola/cammina · seleziona NAV_Start / NAV_PosN e premi Ctrl+Numpad0"
)


def configure_walk_navigation(persist: bool) -> bool:
    """Configura la Walk Navigation del viewport.

    Blender 5.x espone i parametri in ``preferences.inputs.walk_navigation``,
    Blender 4.x in ``space.walk_navigation`` (per-aree). La gravità è
    disattivata: il walk mode non ha collisioni con le mesh e con gravità
    la camera attraverserebbe il pavimento. ``persist`` salva le
    preferenze globali (una tantum, sul PC dell'utente).
    """
    space = next((a.spaces[0] for a in bpy.context.screen.areas if a.type == "VIEW_3D"), None)
    settings = getattr(bpy.context.preferences.inputs, "walk_navigation", None)
    if settings is None and space is not None:
        settings = getattr(space, "walk_navigation", None)
    if settings is None:
        print("⚠ WalkNavigation non disponibile in questa versione di Blender")
        return False

    try:
        settings.walk_speed = WALK_SPEED
        settings.view_height = EYE_HEIGHT
        settings.mouse_speed = 1.0
        settings.use_gravity = False
    except AttributeError:
        print("⚠ Impostazioni walk navigation incomplete, applicate in parte")
        return False
    if persist:
        try:
            bpy.ops.wm.save_userpref()
        except RuntimeError:
            print("⚠ Salvataggio preferenze Blender non riuscito")
    return True


def _yaw_quaternion(angle_deg: float):
    """Quaternione che orienta una camera lungo la direzione di ingaggio.

    La direzione di ingaggio in coordinate stage (x, y) mappa su Blender
    (x, z): dir = (cos, 0, sin). ``to_track_quat`` allinea l'asse di vista
    (-Z) alla direzione, con Y in alto.
    """
    rad = math.radians(angle_deg)
    direction = Vector((math.cos(rad), 0.0, math.sin(rad))).normalized()
    return direction.to_track_quat("-Z", "Y")


def _aim_quaternion(origin: Vector, target: Vector):
    """Quaternione che punta una camera da ``origin`` verso ``target``."""
    direction = (target - origin).normalized()
    return direction.to_track_quat("-Z", "Y")


def create_nav_cameras(scene: dict) -> None:
    """Telecamere bookmark alle posizioni di tiro (NAV_Start / NAV_PosN).

    L'utente seleziona una camera e preme Ctrl+Numpad0 per saltare alla
    vista da quella posizione; il walk mode parte dalla ``NAV_Start``.
    """
    positions = scene.get("shooting_positions", [])
    if not positions:
        return
    target = Vector(scene["camera"]["target"])
    for sp in positions:
        name = "NAV_Start" if sp["is_start"] else f"NAV_Pos{sp['id']}"
        cam_data = bpy.data.cameras.new(name)
        cam_data.lens = 35.0  # lunghezza focale naturalistica per l'FPS
        cam = bpy.data.objects.new(name, cam_data)
        bpy.context.collection.objects.link(cam)
        cam.location = (sp["x"], EYE_HEIGHT, sp["z"])
        cam.rotation_mode = "QUATERNION"
        if sp.get("angle"):
            cam.rotation_quaternion = _yaw_quaternion(sp["angle"])
        else:
            cam.rotation_quaternion = _aim_quaternion(cam.location, target)


def setup_viewport_start(scene: dict) -> None:
    """Posiziona la vista del viewport alla posizione di partenza.

    All'apertura del .blend il viewport guarda lo stage da lì: premendo
    Shift+~ (walk mode) si parte esattamente in quel punto.
    """
    positions = scene.get("shooting_positions", [])
    start = next((sp for sp in positions if sp["is_start"]), positions[0] if positions else None)
    target = Vector(scene["camera"]["target"])

    for area in bpy.context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        r3d = area.spaces[0].region_3d
        r3d.view_perspective = "PERSP"
        r3d.view_location = target
        if start is not None:
            origin = Vector((start["x"], EYE_HEIGHT, start["z"]))
            r3d.view_rotation = _aim_quaternion(origin, target)
            r3d.view_distance = (target - origin).length
        break


def add_nav_help_text(scene: dict) -> None:
    """Cartello 3D con le istruzioni, visibile solo nel viewport.

    ``hide_render`` lo esclude dal render PNG ma resta visibile in
    viewport; è orientato verso lo stage dalla posizione di partenza.
    """
    positions = scene.get("shooting_positions", [])
    start = next((sp for sp in positions if sp["is_start"]), positions[0] if positions else None)
    if start is None:
        return
    rad = math.radians(start["angle"])
    direction = Vector((math.cos(rad), 0.0, math.sin(rad)))

    curve = bpy.data.curves.new("NAV_HelpText", type="FONT")
    curve.body = NAV_HELP_TEXT
    curve.size = 0.12
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    obj = bpy.data.objects.new("NAV_Help", curve)
    bpy.context.collection.objects.link(obj)
    obj.location = Vector((start["x"], 1.5, start["z"])) + direction * 0.4
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    obj.hide_render = True


def set_nav_metadata(scene: dict) -> None:
    """Custom property sulla scena con le istruzioni di navigazione."""
    nav_cameras = [
        o.name for o in bpy.data.objects if o.type == "CAMERA" and o.name.startswith("NAV_")
    ]
    bpy.context.scene["opentds_nav"] = {
        "help": NAV_HELP_TEXT,
        "cameras": nav_cameras,
        "walk_speed": WALK_SPEED,
        "eye_height": EYE_HEIGHT,
        "gravity": False,
    }


def setup_navigation(scene: dict, persist_prefs: bool) -> None:
    """Rende il .blend navigabile: walk prefs, telecamere, viewport, help.

    Non tocca il render PNG: la camera statica resta invariata.
    Un errore in questa fase non deve impedire il salvataggio del .blend.
    """
    try:
        configure_walk_navigation(persist=persist_prefs)
        create_nav_cameras(scene)
        setup_viewport_start(scene)
        add_nav_help_text(scene)
        set_nav_metadata(scene)
    except Exception as exc:
        print(f"⚠ Navigazione non configurata: {exc}")


def setup_render(out_png: str) -> None:
    """Engine EEVEE, risoluzione e formato PNG.

    Il view transform è "Standard" (non AgX/Filmic) per preservare i
    colori IPSC saturi (rosso fault line, ambra barriere, marrone bersagli).
    """
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = CONFIG["resolution"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = out_png
    scene.view_settings.view_transform = "Standard"
    for candidate in (CONFIG["engine"], "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = candidate
            break
        except TypeError:
            continue


# ─── Main ─────────────────────────────────────────────────────────────


def main() -> int:
    """Esegue il render dello stage descritto da scene.json."""
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    if len(argv) < 2:
        print("Uso: blender -b -P scripts/blender_render.py -- scene.json out.png [out.blend]")
        return 1

    scene_path, out_png = argv[0], argv[1]
    out_blend = argv[2] if len(argv) > 2 else None
    no_nav = len(argv) > 3 and argv[3] == "no-nav"

    with open(scene_path, encoding="utf-8") as f:
        scene = json.load(f)

    print(f"🎬 Render stage: {scene.get('name', '?')} ({len(scene['objects'])} oggetti)")
    bpy.context.preferences.edit.use_global_undo = False
    clean_scene()
    setup_world()

    for obj in scene["objects"]:
        try:
            build_object(obj)
        except Exception as exc:
            print(f"⚠ {obj.get('id')}: {exc}")

    setup_lights(scene["lights"])
    setup_camera(scene["camera"])
    setup_render(out_png)

    bpy.ops.render.render(write_still=True)
    if out_blend and not no_nav:
        # La navigazione è utile solo nel .blend: il PNG usa la camera statica.
        setup_navigation(scene, persist_prefs=True)
        bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    print(f"✅ Render completato: {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
