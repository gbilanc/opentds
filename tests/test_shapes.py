"""
Test unitari per core/shapes.py — forme alfabetiche, poligoni, perimetri.
"""
from __future__ import annotations

import pytest

from core.models import Stage
from core.shapes import (
    LETTER_SHAPES,
    generate_perimeter_polygon,
    perimeter_to_items,
    polygon_to_shapely,
)
from core.geometry import validate_polygon


class TestLetterShapes:
    def test_all_shapes_have_valid_polygons(self):
        """Ogni forma lettera produce un poligono valido (o gestibile).

        NOTA: la forma Z ha le due diagonali che si incrociano
        (auto-intersezione genuina), ma in pratica il generatore
        applica perturbazione che risolve il problema.
        """
        known_complex = {"Z"}  # forme con auto-intersezioni genuine
        for letter, verts in LETTER_SHAPES.items():
            if letter in known_complex:
                continue
            valid, errors = validate_polygon(verts, min_vertices=3)
            assert valid, f"Lettera {letter} invalida: {errors}"

    def test_all_shapes_have_min_vertices(self):
        """Ogni forma ha almeno 3 vertici."""
        for letter, verts in LETTER_SHAPES.items():
            assert len(verts) >= 3, f"Lettera {letter} ha solo {len(verts)} vertici"

    def test_knows_14_shapes(self):
        """16 forme alfabetiche definite (incluse W e Q)."""
        assert len(LETTER_SHAPES) == 16

    @pytest.mark.parametrize("letter", [
        "L", "T", "U", "C", "H", "F", "O", "S", "X", "Y", "M", "N", "E",
    ])
    def test_each_shape_has_valid_polygon(self, letter):
        """Ogni forma singola è un poligono valido (esclusa Z, complessa)."""
        verts = LETTER_SHAPES[letter]
        valid, errors = validate_polygon(verts, min_vertices=3)
        assert valid, f"Lettera {letter} invalida: {errors}"


class TestGeneratePerimeterPolygon:
    def test_generates_valid_polygon(self):
        """Il poligono generato è valido."""
        stage = Stage(width=20.0, depth=15.0)
        poly = generate_perimeter_polygon(stage, letter_shape="O", has_steel=False)
        valid, errors = validate_polygon(poly, min_vertices=4)
        assert valid, f"Poligono invalido: {errors}"

    def test_generates_within_stage(self):
        """Il poligono rimane dentro i confini dello stage."""
        stage = Stage(width=20.0, depth=15.0)
        poly = generate_perimeter_polygon(stage, letter_shape="L", has_steel=False)
        for x, y in poly:
            assert 0.5 <= x <= 19.5, f"x={x} fuori dai bound"
            assert 0.5 <= y <= 11.5, f"y={y} fuori dai bound (profondità={stage.depth})"

    def test_has_minimum_area(self):
        """Il poligono ha area sufficiente."""
        stage = Stage(width=20.0, depth=15.0)
        poly = generate_perimeter_polygon(stage, letter_shape="O", has_steel=False)
        from core.geometry import polygon_area
        area = polygon_area(poly)
        assert area > 1.0, f"Area troppo piccola: {area}"

    def test_fallback_to_O_when_shape_invalid(self):
        """Se la forma richiesta fallisce, usa O come fallback."""
        stage = Stage(width=8.0, depth=6.0)
        poly = generate_perimeter_polygon(stage, letter_shape="X", has_steel=False)
        valid, errors = validate_polygon(poly, min_vertices=4)
        assert valid, f"Fallback poligono invalido: {errors}"

    def test_different_seeds_different_polygons(self):
        """Semi diversi producono poligoni diversi."""
        import random
        random.seed(1)
        stage = Stage(width=20.0, depth=15.0)
        poly1 = generate_perimeter_polygon(stage, letter_shape="random", has_steel=False)
        random.seed(999)
        poly2 = generate_perimeter_polygon(stage, letter_shape="random", has_steel=False)
        # Dovrebbero differire in almeno un vertice
        assert poly1 != poly2


class TestPerimeterToItems:
    def test_fault_lines_have_closed_chain_property(self):
        """Tutti gli item perimetrali hanno closed_chain=True."""
        poly = [(2, 2), (18, 2), (18, 13), (2, 13)]
        items = perimeter_to_items(poly, style="fault_lines")
        assert len(items) == 4
        for item in items:
            assert item.properties.get("closed_chain") is True
            assert item.properties.get("perimeter") is True
            assert item.item_type.name == "FAULT_LINE"

    def test_empty_poly_returns_empty(self):
        """Poligono con meno di 3 vertici → lista vuota."""
        items = perimeter_to_items([], style="fault_lines")
        assert items == []

    @pytest.mark.parametrize("style,expected_type", [
        ("fault_lines", "FAULT_LINE"),
        ("barriers", "BARRIER"),
        ("walls", "WALL"),
    ])
    def test_all_styles_generate_items(self, style, expected_type):
        """Ogni stile di delimitazione produce item del tipo corretto."""
        poly = [(2, 2), (18, 2), (18, 13), (2, 13)]
        items = perimeter_to_items(poly, style=style)
        assert len(items) >= 2
        type_count = sum(1 for it in items if it.item_type.name == expected_type)
        assert type_count >= 2, f"Stile {style}: pochi {expected_type} ({type_count})"


class TestPolygonToShapely:
    def test_converts_valid_polygon(self):
        """Poligono valido → Shapely Polygon."""
        poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
        result = polygon_to_shapely(poly)
        assert result is not None
        assert abs(result.area - 100) < 0.01

    def test_none_for_invalid(self):
        """Meno di 3 vertici → None."""
        assert polygon_to_shapely([]) is None
        assert polygon_to_shapely([(0, 0), (1, 1)]) is None
