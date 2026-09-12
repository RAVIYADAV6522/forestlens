"""Resampling coarse imagery to the detector's training resolution.

DeepForest's pretrained tree model was trained on ~0.10 m/px airborne RGB. On 0.5 m
satellite imagery it under-detects badly, so the pipeline upsamples the detection
input. These tests pin the contract: boxes come back in source-raster pixels, the
user is told resampling happened, and memory is bounded.
"""

import numpy as np
import pytest

from src import detection, io_utils, pipeline


def scene(gsd, size=100):
    src = io_utils.from_array(np.zeros((size, size, 3), dtype=np.uint8), name="s.png")
    return pipeline.apply_gsd(src, gsd)


def test_fine_imagery_is_not_resampled():
    array, scale, note = io_utils.resample_for_detection(scene(0.10), 0.10)
    assert scale == 1.0 and note is None
    assert array.shape[0] == 100


def test_slightly_coarse_imagery_is_left_alone():
    _, scale, note = io_utils.resample_for_detection(scene(0.12), 0.10)
    assert scale == 1.0 and note is None


def test_coarse_imagery_is_upsampled_to_training_gsd():
    array, scale, note = io_utils.resample_for_detection(scene(0.30), 0.10)
    assert scale == pytest.approx(3.0)
    assert array.shape[:2] == (300, 300)
    assert "adds no detail" in note


def test_unknown_gsd_cannot_be_resampled():
    src = io_utils.from_array(np.zeros((100, 100, 3), dtype=np.uint8))
    _, scale, note = io_utils.resample_for_detection(src, 0.10)
    assert scale == 1.0 and note is None


def test_scale_is_capped_by_the_memory_limit():
    array, scale, note = io_utils.resample_for_detection(
        scene(0.50, size=2000), 0.10, max_pixels=16_000_000
    )
    assert scale < 5.0
    assert array.shape[0] * array.shape[1] <= 16_000_000
    assert "capped" in note


def test_huge_image_falls_back_to_native_scale_with_a_warning():
    _, scale, note = io_utils.resample_for_detection(
        scene(0.50, size=6000), 0.10, max_pixels=16_000_000
    )
    assert scale == 1.0
    assert "too large to resample" in note
    assert "miss smaller crowns" in note


def test_boxes_are_mapped_back_into_source_pixels():
    dets = [detection.Detection(id=1, box=(30.0, 30.0, 60.0, 60.0), score=0.9)]
    pipeline.rescale_detections(dets, 3.0)
    assert dets[0].box == (10.0, 10.0, 20.0, 20.0)
    assert dets[0].box_pixel_area == 100.0


def test_resampled_run_reports_scale_and_effective_gsd(monkeypatch):
    """A detection made at 3x must yield the same physical area as at 1x."""
    def fake_detect(image, **kwargs):
        # One box spanning 30x30 resampled px == 10x10 source px at scale 3.
        return [detection.Detection(id=1, box=(0.0, 0.0, 30.0, 30.0), score=0.9)]

    monkeypatch.setattr(detection, "detect", fake_detect)
    monkeypatch.setattr(detection, "describe_backend", lambda: {"backend": "stub"})

    result = pipeline.analyse(scene(0.30), pipeline.Options(use_segmentation=False))
    assert result.summary["detection_scale"] == pytest.approx(3.0)
    assert result.summary["detection_gsd_m_per_px"] == pytest.approx(0.10)
    # 10x10 source px at 0.30 m/px -> 100 * 0.09 = 9.0 m2
    assert result.summary["total_canopy_area_m2"] == pytest.approx(9.0)
    assert any("resampled" in w for w in result.warnings)


def test_coarse_scene_warns_about_the_training_domain(monkeypatch):
    monkeypatch.setattr(detection, "detect", lambda image, **k: [])
    monkeypatch.setattr(detection, "describe_backend", lambda: {"backend": "stub"})
    result = pipeline.analyse(scene(0.50), pipeline.Options(use_segmentation=False))
    assert any("outside its training domain" in w for w in result.warnings)
    assert any("lower bound" in w for w in result.warnings)


def test_segmentation_is_skipped_on_very_large_scenes(monkeypatch):
    """Masks cost too much on a CPU host past a few hundred crowns; degrade to boxes."""
    from src import metrics, segmentation

    many = [
        detection.Detection(id=i, box=(i, 0.0, i + 5.0, 5.0), score=0.9)
        for i in range(1, 12)
    ]
    monkeypatch.setattr(detection, "detect", lambda image, **k: list(many))
    monkeypatch.setattr(detection, "describe_backend", lambda: {"backend": "stub"})

    def should_not_run(*args, **kwargs):
        raise AssertionError("segmentation must not run above the crown limit")

    monkeypatch.setattr(segmentation, "refine", should_not_run)

    result = pipeline.analyse(
        scene(0.10), pipeline.Options(use_segmentation=True, max_segmentation_crowns=10)
    )
    assert result.summary["proxy_crowns"] == 11
    assert result.summary["area_basis"] == [metrics.AREA_FROM_BOX]
    assert any("skipped because this scene has 11" in w for w in result.warnings)
    assert any("12-22%" in w for w in result.warnings)
