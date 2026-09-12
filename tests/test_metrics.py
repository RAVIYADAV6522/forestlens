import numpy as np
import pytest

from src import metrics
from src.detection import Detection


def box(x1, y1, x2, y2, score=0.9, id=1):
    return Detection(id=id, box=(x1, y1, x2, y2), score=score)


def test_pixel_area_scales_by_gsd_squared():
    assert metrics.to_physical_area(100, 0.5) == 25.0
    assert metrics.to_physical_area(4, 2.0) == 16.0


def test_unknown_gsd_yields_no_physical_area():
    assert metrics.to_physical_area(100, None) is None


def test_non_positive_gsd_is_rejected():
    with pytest.raises(ValueError):
        metrics.to_physical_area(100, 0)


def test_box_only_detection_is_labelled_proxy():
    crowns = metrics.build_crowns([box(0, 0, 10, 10)])
    assert crowns[0].pixel_area == 100
    assert crowns[0].area_basis == metrics.AREA_FROM_BOX


def test_mask_overrides_box_area():
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:8, 2:8] = True
    crowns = metrics.build_crowns([box(0, 0, 10, 10)], {1: (mask, 0, 0)})
    assert crowns[0].pixel_area == 36
    assert crowns[0].area_basis == metrics.AREA_FROM_MASK


def test_summary_without_gsd_reports_pixels_only():
    summary = metrics.summarise(metrics.build_crowns([box(0, 0, 10, 10)]), gsd=None)
    assert summary["tree_count"] == 1
    assert summary["total_canopy_pixels"] == 100
    assert summary["total_canopy_area_m2"] is None
    assert summary["canopy_coverage_pct"] is None
    assert any("Ground sampling distance is unknown" in w for w in metrics.quality_warnings(summary))


def test_summary_with_gsd_and_ground_area():
    crowns = metrics.build_crowns([box(0, 0, 10, 10, id=1), box(20, 20, 30, 30, id=2)])
    summary = metrics.summarise(crowns, gsd=0.5, ground_area_m2=1000.0)
    assert summary["tree_count"] == 2
    assert summary["total_canopy_area_m2"] == 50.0
    assert summary["canopy_coverage_pct"] == 5.0
    assert summary["mean_crown_area_m2"] == 25.0


def test_impossible_coverage_is_called_invalid():
    crowns = metrics.build_crowns([box(0, 0, 100, 100)])
    summary = metrics.summarise(crowns, gsd=1.0, ground_area_m2=100.0)
    assert any("exceeds 100%" in w for w in metrics.quality_warnings(summary))


def test_confidence_is_never_presented_as_accuracy():
    summary = metrics.summarise(metrics.build_crowns([box(0, 0, 4, 4)]), gsd=1.0)
    assert any("not measurement accuracy" in w for w in metrics.quality_warnings(summary))


def test_proxy_crowns_are_flagged_in_warnings():
    summary = metrics.summarise(metrics.build_crowns([box(0, 0, 4, 4)]), gsd=1.0)
    assert any("PROXY" in w for w in metrics.quality_warnings(summary))
