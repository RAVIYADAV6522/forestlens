"""End-to-end pipeline test with a stubbed detector.

The detector is stubbed because model weights must not be a prerequisite for
verifying the measurement and export logic. Nothing here stands in for a real
count: the stub returns fixed boxes so the arithmetic can be checked exactly.
"""

import numpy as np
import pytest

from src import detection, io_utils, metrics, pipeline

STUB_BOXES = [
    (10.0, 10.0, 30.0, 30.0, 0.90),
    (50.0, 50.0, 66.0, 66.0, 0.75),
    (0.0, 80.0, 18.0, 98.0, 0.60),
]


@pytest.fixture
def stub_detector(monkeypatch):
    def fake_detect(image, **kwargs):
        min_score = kwargs.get("min_score", 0.0)
        return [
            detection.Detection(id=i, box=b[:4], score=b[4])
            for i, b in enumerate((b for b in STUB_BOXES if b[4] >= min_score), start=1)
        ]

    monkeypatch.setattr(detection, "detect", fake_detect)
    monkeypatch.setattr(detection, "describe_backend", lambda: {"backend": "stub", "available": True})


@pytest.fixture
def scene():
    rng = np.random.default_rng(0)
    array = rng.integers(0, 255, size=(100, 100, 3), dtype=np.uint8)
    return io_utils.from_array(array, name="stub_scene.png")


def test_pipeline_without_gsd_reports_pixels_and_withholds_area(stub_detector, scene):
    result = pipeline.analyse(scene, pipeline.Options(use_segmentation=False))
    assert result.tree_count == 3
    assert result.summary["total_canopy_pixels"] == 400 + 256 + 324
    assert result.summary["total_canopy_area_m2"] is None
    assert all(row["area_m2"] == "" for row in result.rows())


def test_pipeline_with_gsd_computes_area_and_coverage(stub_detector, scene):
    # match_model_gsd off: this test pins the area arithmetic, not the resampling path.
    pipeline.apply_gsd(scene, 0.5)
    result = pipeline.analyse(
        scene, pipeline.Options(use_segmentation=False, match_model_gsd=False)
    )
    assert result.summary["total_canopy_area_m2"] == pytest.approx(245.0)
    assert result.summary["analysed_ground_area_m2"] == pytest.approx(2500.0)
    assert result.summary["canopy_coverage_pct"] == pytest.approx(9.8)


def test_edge_crown_is_flagged_and_proxy_is_declared(stub_detector, scene):
    result = pipeline.analyse(scene, pipeline.Options(use_segmentation=False))
    flagged = [c for c in result.crowns if "clipped_at_image_edge" in c.flags]
    assert len(flagged) == 1
    assert result.summary["area_basis"] == [metrics.AREA_FROM_BOX]
    assert result.summary["proxy_crowns"] == 3


def test_confidence_threshold_changes_the_count(stub_detector, scene):
    result = pipeline.analyse(scene, pipeline.Options(min_score=0.8, use_segmentation=False))
    assert result.tree_count == 1


def test_run_metadata_records_the_assumptions(stub_detector, scene):
    pipeline.apply_gsd(scene, 0.5)
    result = pipeline.analyse(
        scene, pipeline.Options(use_segmentation=False, match_model_gsd=False)
    )
    meta = result.metadata()
    assert meta["image"]["gsd_origin"] == io_utils.GSD_USER
    assert meta["run"]["options"]["min_score"] == detection.DEFAULT_SCORE
    assert meta["run"]["timestamp_utc"]
    assert meta["warnings"]


def test_exports_are_written(stub_detector, scene, tmp_path):
    result = pipeline.analyse(scene, pipeline.Options(use_segmentation=False))
    written = pipeline.export_all(result, tmp_path, stem="scene")
    assert written["png"].exists() and written["csv"].exists()
    assert "geojson" not in written
    assert '"gsd_origin"' in written["metadata"].read_text()
