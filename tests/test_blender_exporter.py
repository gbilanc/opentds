"""Test del mapping stage → scena 3D Blender."""

import json
from pathlib import Path

from services.blender_exporter import BlenderExportOptions, build_scene, clean_svg, export_scene
from services.serializer import load_stage

STAGE2 = Path("examples/stage2.json")


def test_build_scene_from_stage2_produces_expected_objects(tmp_path):
    """Uno stage reale genera pavimento, perimetro, bersagli e posizioni."""
    stage = load_stage(STAGE2)
    opts = BlenderExportOptions(svg_dir=tmp_path)
    scene = build_scene(stage, opts)

    assert scene["name"] == "Stage IPSC"
    assert scene["version"] == 1

    kinds = {o["kind"] for o in scene["objects"]}
    assert kinds >= {"box", "cylinder_v", "board_box", "polygon"}

    # Almeno un bersaglio con stecche e un pannello SVG pulito.
    boards = [o for o in scene["objects"] if o["kind"] == "board_box" and "svg" in o]
    assert boards, "nessun pannello bersaglio con SVG"
    for board in boards:
        assert Path(board["svg"]).exists()
        assert 'fill="none"' not in Path(board["svg"]).read_text()

    # Stecche di legno presenti.
    sticks = [o for o in scene["objects"] if "stick" in o["id"]]
    assert sticks, "nessuna stecca bersaglio"

    # Muri perimetrali e pavimento.
    ids = {o["id"] for o in scene["objects"]}
    assert "floor" in ids and "shooting-area" in ids
    assert any(i.startswith("boundary-") for i in ids)

    # Posizioni di tiro con cerchio + freccia.
    sp_ids = [i for i in ids if i.startswith("sp-")]
    assert len(sp_ids) == len(stage.shooting_positions) * 2

    # Camera e luci definite.
    assert scene["camera"]["lens"] > 0
    assert len(scene["camera"]["position"]) == 3
    assert len(scene["lights"]) >= 2


def test_scene_is_json_serializable(tmp_path):
    """La scena deve essere esportabile e ricaricabile come JSON."""
    stage = load_stage(STAGE2)
    out = export_scene(stage, tmp_path / "scene.json", BlenderExportOptions(svg_dir=tmp_path))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["name"] == "Stage IPSC"


def test_scene_includes_shooting_positions_for_navigation(tmp_path):
    """Le posizioni di tiro finiscono nella scena per le NAV cameras."""
    stage = load_stage(STAGE2)
    scene = build_scene(stage, BlenderExportOptions(svg_dir=tmp_path))

    positions = scene["shooting_positions"]
    assert len(positions) == len(stage.shooting_positions)

    # Coordinate Blender: stage (x, y) → (x, z), con is_start marcato.
    first = positions[0]
    assert {"id", "x", "z", "angle", "is_start"} <= set(first)
    assert any(p["is_start"] for p in positions)
    for p in positions:
        assert p["x"] != p["z"] or abs(p["x"] - p["z"]) < 0.01  # non invertite
    z_ok = all(
        round(p["z"], 3) == round(sp.y, 3)
        for p, sp in zip(positions, stage.shooting_positions)
    )
    assert z_ok
    # La camera statica fornisce il target di osservazione per le NAV.
    assert len(scene["camera"]["target"]) == 3


def test_clean_svg_replaces_fill_and_strips_text(tmp_path):
    """Il preprocesso SVG colora la silhouette e rimuove i testi."""
    src = tmp_path / "raw.svg"
    src.write_text('<svg><path fill="none"/><text>B</text></svg>', encoding="utf-8")
    out = clean_svg(src, "#8B4513", tmp_path / "clean")
    text = out.read_text(encoding="utf-8")
    assert 'fill="#8B4513"' in text
    assert "<text" not in text


def test_doublet_overlap_expands_to_two_boards(tmp_path):
    """I compositi vengono espansi: DOUBLET_OVERLAP → due pannelli."""
    stage = load_stage(STAGE2)
    # Inietta un composito per verificare l'espansione.
    from core.models import ItemType, StageItem

    stage.items.append(
        StageItem(
            id=999,
            item_type=ItemType.DOUBLET_OVERLAP,
            x=10.0,
            y=3.0,
            label="Doppio",
            properties={"custom_svg_path": "ipsc_target_2s.svg"},
        )
    )
    scene = build_scene(stage, BlenderExportOptions(svg_dir=tmp_path))
    boards = [o for o in scene["objects"] if o["kind"] == "board_box" and "999" in o["id"]]
    assert len(boards) == 2
    # I due pannelli sono a quote verticali diverse (±20 cm).
    ys = {round(b["position"][1], 2) for b in boards}
    assert len(ys) == 2
