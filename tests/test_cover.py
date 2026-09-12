"""Canopy-cover bracketing.

Summing crown boxes underestimates cover in closed canopy, so cover is reported as
a bracket. These tests pin the arithmetic and the honesty rules around it.
"""

import numpy as np
import pytest

from src import cover, metrics
from src.detection import Detection


def rgb(r, g, b, size=100):
    a = np.zeros((size, size, 3), dtype=np.uint8)
    a[..., 0], a[..., 1], a[..., 2] = r, g, b
    return a


def test_excess_green_is_positive_for_green_pixels():
    assert cover.excess_green(rgb(50, 150, 50))[0, 0] == 200.0
    assert cover.excess_green(rgb(150, 50, 150))[0, 0] == -200.0


def test_all_green_image_reads_as_fully_vegetated():
    result = cover.green_vegetation_cover(rgb(50, 150, 50))
    assert result["fraction"] == 1.0
    assert result["method"] == cover.VEGETATION_RULE


def test_bare_ground_reads_as_unvegetated():
    assert cover.green_vegetation_cover(rgb(160, 140, 120))["fraction"] == 0.0


def test_half_green_image_reads_as_half_vegetated():
    a = rgb(160, 140, 120)
    a[:50] = [50, 150, 50]
    assert cover.green_vegetation_cover(a)["fraction"] == pytest.approx(0.5)


def test_otsu_separates_two_clear_classes():
    values = np.concatenate([np.full(500, -100.0), np.full(500, 100.0)])
    assert -100 < cover.otsu_threshold(values) < 100


def test_otsu_on_empty_input_does_not_crash():
    assert cover.otsu_threshold(np.array([])) == 0.0


def test_crown_union_counts_overlapping_boxes_once():
    """Two boxes overlapping by half must not be double counted."""
    crowns = metrics.build_crowns([
        Detection(id=1, box=(0, 0, 50, 50), score=0.9),
        Detection(id=2, box=(25, 0, 75, 50), score=0.9),
    ])
    fraction, _ = cover.crown_union_fraction(crowns, 100, 100)
    # Union spans x 0..75, y 0..50 = 3750 px of 10000, whereas the sum would be 5000.
    assert fraction == pytest.approx(0.375)
    summed = sum(c.pixel_area for c in crowns)
    assert summed == 5000.0  # the sum really does over-count


def test_crown_union_clips_boxes_at_image_edges():
    crowns = metrics.build_crowns([Detection(id=1, box=(-10, -10, 50, 50), score=0.9)])
    fraction, _ = cover.crown_union_fraction(crowns, 100, 100)
    assert fraction == pytest.approx(0.25)


def test_union_uses_mask_when_one_exists():
    mask = np.zeros((50, 50), dtype=bool)
    mask[:25] = True
    crowns = metrics.build_crowns(
        [Detection(id=1, box=(0, 0, 50, 50), score=0.9)], {1: (mask, 0, 0)}
    )
    fraction, _ = cover.crown_union_fraction(crowns, 100, 100)
    assert fraction == pytest.approx(0.125)


def test_bracket_orders_lower_below_upper_in_the_normal_case():
    a = rgb(50, 150, 50)
    crowns = metrics.build_crowns([Detection(id=1, box=(0, 0, 20, 20), score=0.9)])
    result = cover.bracket(crowns, a)
    assert result["lower_bound_pct"] == pytest.approx(4.0)
    assert result["upper_bound_pct"] == pytest.approx(100.0)
    assert not result["inverted"]


def test_bracket_flags_the_inverted_case():
    """Boxes covering bare ground cover more than the vegetation index does."""
    crowns = metrics.build_crowns([Detection(id=1, box=(0, 0, 100, 100), score=0.9)])
    result = cover.bracket(crowns, rgb(160, 140, 120))
    assert result["inverted"]
    assert "unreliable" in result["note"]


def test_wide_bracket_refuses_to_report_a_single_figure():
    warnings = metrics.cover_warnings(
        {"lower_bound_pct": 17.0, "upper_bound_pct": 93.0, "bracket_width_pct": 76.0,
         "inverted": False, "vegetation_caveat": "caveat text"}
    )
    assert any("No single cover figure is reported" in w for w in warnings)
    assert any("17.0%" in w and "93.0%" in w for w in warnings)


def test_narrow_bracket_does_not_trigger_the_refusal():
    warnings = metrics.cover_warnings(
        {"lower_bound_pct": 60.0, "upper_bound_pct": 70.0, "bracket_width_pct": 10.0,
         "inverted": False, "vegetation_caveat": "caveat text"}
    )
    assert not any("No single cover figure" in w for w in warnings)
