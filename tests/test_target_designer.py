"""Test per core/target_designer.py — metadati bersagli contenuti (numero + tipo)."""

from __future__ import annotations

import os

from core.target_designer import (
    CUSTOM_TARGETS_DIR,
    KIND_NO_SHOOT,
    KIND_PAPER,
    KIND_POPPER,
    CustomTargetMeta,
    SvgTargetDesign,
    list_custom_targets,
    parse_custom_target_meta,
    resolve_custom_svg_path,
)


class TestCustomTargetMeta:
    def test_default_single_paper(self):
        meta = CustomTargetMeta()
        assert meta.count == 1
        assert meta.paper == 1
        assert meta.steel == 0
        assert meta.no_shoots == 0

    def test_label_single_paper(self):
        assert CustomTargetMeta().label == "1 paper"

    def test_counts_mixed(self):
        meta = CustomTargetMeta(kinds=(KIND_PAPER, KIND_PAPER, KIND_NO_SHOOT))
        assert meta.count == 3
        assert meta.paper == 2
        assert meta.steel == 0
        assert meta.no_shoots == 1

    def test_label_mixed(self):
        meta = CustomTargetMeta(kinds=(KIND_PAPER, KIND_PAPER, KIND_NO_SHOOT))
        assert meta.label == "2 paper + 1 no-shoot"

    def test_label_steel(self):
        meta = CustomTargetMeta(kinds=(KIND_POPPER,))
        assert meta.steel == 1
        assert meta.label == "1 popper"


class TestSvgMetadataRoundtrip:
    def test_roundtrip_preserves_kinds(self, tmp_path):
        design = SvgTargetDesign(
            name="Doppio + NS",
            target_kinds=[KIND_PAPER, KIND_PAPER, KIND_NO_SHOOT],
        )
        filepath = tmp_path / "doppio_ns.svg"
        filepath.write_text(design.to_svg(), encoding="utf-8")

        parsed = SvgTargetDesign.from_svg(str(filepath))
        assert parsed.target_kinds == [KIND_PAPER, KIND_PAPER, KIND_NO_SHOOT]
        assert parsed.num_targets == 3

    def test_roundtrip_default_single(self, tmp_path):
        design = SvgTargetDesign(name="Semplice")
        filepath = tmp_path / "semplice.svg"
        filepath.write_text(design.to_svg(), encoding="utf-8")

        parsed = SvgTargetDesign.from_svg(str(filepath))
        assert parsed.num_targets == 1
        assert parsed.effective_kinds() == [KIND_PAPER]

    def test_parse_inexistent_file_returns_default(self):
        meta = parse_custom_target_meta("/nonexistent/file.svg")
        assert meta.count == 1
        assert meta.paper == 1

    def test_to_dict_from_dict_roundtrip(self):
        design = SvgTargetDesign(name="X", target_kinds=[KIND_PAPER, KIND_NO_SHOOT])
        restored = SvgTargetDesign.from_dict(design.to_dict())
        assert restored.target_kinds == [KIND_PAPER, KIND_NO_SHOOT]
        assert restored.num_targets == 2


class TestBackfilledResources:
    def test_all_backfilled_files_parse(self):
        for path in list_custom_targets():
            meta = parse_custom_target_meta(path)
            assert meta.count >= 1

    def test_expected_mapping(self):
        expected = {
            "ipsc_target.svg": "1 paper",
            "ipsc_mini_target.svg": "1 paper",
            "ipsc_target_2a.svg": "2 paper",
            "ipsc_target_2s.svg": "2 paper",
            "ipsc_target_2a+ns.svg": "2 paper + 1 no-shoot",
            "ipsc_target_2s+ns.svg": "2 paper + 1 no-shoot",
            "ipsc_popper.svg": "1 popper",
            "ipsc_mini_popper.svg": "1 popper",
            "ipsc_metal_plate.svg": "1 plate",
            "ipsc_no_shoot.svg": "1 no-shoot",
        }
        for fname, label in expected.items():
            path = os.path.join(CUSTOM_TARGETS_DIR, fname)
            assert parse_custom_target_meta(path).label == label, fname


class TestResolveCustomSvgPath:
    def test_relative_to_resources(self):
        path = resolve_custom_svg_path("targets/custom/ipsc_target.svg")
        assert path.endswith("targets/custom/ipsc_target.svg")
        assert os.path.isfile(path)

    def test_plain_filename(self):
        path = resolve_custom_svg_path("ipsc_target.svg")
        assert path.endswith("ipsc_target.svg")
        assert os.path.isfile(path)

    def test_absolute_path(self):
        path = resolve_custom_svg_path(os.path.join(CUSTOM_TARGETS_DIR, "ipsc_target.svg"))
        assert path.endswith("ipsc_target.svg")

    def test_inexistent_returns_empty(self):
        assert resolve_custom_svg_path("non_esiste.svg") == ""
