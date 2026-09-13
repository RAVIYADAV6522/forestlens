"""The detector's network scale, and why suppression cannot fix crown fragmentation.

DeepForest 2.1.0 leaves torchvision's GeneralizedRCNNTransform at its defaults, so every
window is rescaled to an 800 px short side before the network sees it. The scale the
weights operate at is therefore `patch_size × gsd / 800`, which means the tile-size
control silently changed the detector's scale — measured at 3.4× on the count and 2.0× on
median crown width — until `resample_for_detection` began dividing it back out.

These tests pin three things:

* the correction is a strict no-op at the shipped default, which is what protects every
  published figure;
* crowns land at the same *network* pixel size whatever the tile size;
* and the fragments the correction prevents were never reachable by IoU suppression, so
  no future "duplicate fix" is tempted to lower a threshold instead.

The fixture-backed tests are the anti-deletion guard: a change aggressive enough to start
deleting legitimate adjacent trees moves one of their numbers.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np
import pytest

from src import detection, io_utils, pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "bc_open_canopy_boxes.csv"
SLOW = os.environ.get("FORESTLENS_SLOW_TESTS") == "1"


def scene(gsd=None, size=512):
    source = io_utils.from_array(np.zeros((size, size, 3), dtype=np.uint8), name="s.png")
    return pipeline.apply_gsd(source, gsd) if gsd else source


@pytest.fixture(scope="module")
def validated_boxes():
    """The 695 accepted boxes from bc_open_canopy at the documented settings."""
    with FIXTURE.open() as handle:
        rows = list(csv.DictReader(handle))
    return [
        detection.Detection(
            id=int(r["id"]),
            box=(float(r["x1"]), float(r["y1"]), float(r["x2"]), float(r["y2"])),
            score=float(r["score"]),
        )
        for r in rows
    ]


def intersection_over_smaller(a, b):
    inter_w = min(a[2], b[2]) - max(a[0], b[0])
    inter_h = min(a[3], b[3]) - max(a[1], b[1])
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return inter_w * inter_h / max(smaller, 1e-9)


# --------------------------------------------------------------------------- #
# The correction itself
# --------------------------------------------------------------------------- #

def test_shipped_default_is_unchanged_by_the_network_correction():
    """At the default tile size the factor is 1.0, so every published figure holds.

    This is the test that makes the correction safe to ship.
    """
    _, gsd_scale, _ = io_utils.resample_for_detection(
        scene(gsd=0.30517578125), 0.10, patch_size=800
    )
    assert gsd_scale == pytest.approx(3.0517578125)

    _, crown_scale, _ = io_utils.resample_for_detection(
        scene(), 0.10, apparent_crown_px=150.0, patch_size=800
    )
    assert crown_scale == pytest.approx(io_utils.MODEL_CROWN_PX / 150.0)


@pytest.mark.parametrize("patch", [400, 600, 800, 1000, 1200])
def test_gsd_scale_divides_out_the_network_resize(patch):
    source = scene(gsd=0.30517578125)
    _, scale, _ = io_utils.resample_for_detection(source, 0.10, patch_size=patch)
    assert scale == pytest.approx(source.gsd / 0.10 * patch / io_utils.NETWORK_MIN_SIZE)


@pytest.mark.parametrize("patch", [400, 600, 800, 1000, 1200])
def test_crowns_land_at_one_network_size_whatever_the_tile_size(patch):
    """The invariant the correction restores, and the reason it is not a threshold tune."""
    apparent = 170.0
    _, scale, _ = io_utils.resample_for_detection(
        scene(), 0.10, apparent_crown_px=apparent, patch_size=patch
    )
    network_px = apparent * scale * io_utils.NETWORK_MIN_SIZE / patch
    assert network_px == pytest.approx(io_utils.MODEL_CROWN_PX)


def test_the_note_names_the_tile_size_when_the_network_resize_applies():
    _, _, note = io_utils.resample_for_detection(scene(gsd=0.30517578125), 0.10, patch_size=600)
    assert "600 px tile" in note and "800 px" in note


def test_network_gsd_is_reported_separately_from_detection_gsd(monkeypatch):
    """The array handed to the detector and the scale the weights see are different
    numbers; the run metadata now carries both."""
    monkeypatch.setattr(detection, "detect", lambda image, **k: [])
    monkeypatch.setattr(detection, "describe_backend", lambda: {"backend": "stub"})
    result = pipeline.analyse(
        scene(gsd=0.30517578125),
        pipeline.Options(use_segmentation=False, patch_size=600),
    )
    assert result.summary["network_gsd_m_per_px"] == pytest.approx(0.10, abs=1e-9)
    assert result.summary["detection_gsd_m_per_px"] != pytest.approx(0.10)


def test_whole_image_branch_warns_that_the_correction_does_not_apply(monkeypatch):
    """detect() resizes min(h, w) to 800 on that branch, not patch_size, so the scale
    match is off and the user has to be told rather than left with a silent error."""
    monkeypatch.setattr(detection, "detect", lambda image, **k: [])
    monkeypatch.setattr(detection, "describe_backend", lambda: {"backend": "stub"})
    result = pipeline.analyse(
        scene(gsd=0.10, size=300), pipeline.Options(use_segmentation=False, patch_size=800)
    )
    assert any("smaller than the 800 px tile size" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Why suppression is the wrong tool — pinned so nobody retries it
# --------------------------------------------------------------------------- #

def test_over_split_fragments_are_unreachable_by_usable_iou_thresholds():
    """Fragments tile a crown side by side, so their pairwise IoU is tiny — below even
    the IoU of genuinely adjacent crowns. No threshold separates the two cases."""
    left = (0.0, 0.0, 45.0, 85.0)
    right = (40.0, 0.0, 85.0, 85.0)
    fragment_iou = detection.iou(left, right)
    assert fragment_iou == pytest.approx(0.0588, abs=0.001)

    dets = [detection.Detection(id=1, box=left, score=0.9),
            detection.Detection(id=2, box=right, score=0.8)]
    for threshold in (0.10, 0.15, 0.25, 0.40):
        assert len(detection.suppress_duplicates(list(dets), threshold)) == 2

    # Only a threshold below the fragment IoU reaches them...
    assert len(detection.suppress_duplicates(list(dets), 0.05)) == 1


def test_no_iou_threshold_separates_fragments_from_real_neighbours(validated_boxes):
    """...and that threshold is far below where real adjacent crowns sit, so reaching
    the fragments necessarily merges legitimate trees first. This is the geometric
    reason the reported problem cannot be fixed in post-processing."""
    fragment_iou = detection.iou((0.0, 0.0, 45.0, 85.0), (40.0, 0.0, 85.0, 85.0))

    boxes = [d.box for d in validated_boxes]
    real_pair_ious = [
        detection.iou(a, b)
        for i, a in enumerate(boxes) for b in boxes[i + 1:]
        if detection.iou(a, b) > 0
    ]
    tightest_real = max(real_pair_ious)

    # Fragments overlap LESS than real neighbours do, so the orderings conflict: any
    # threshold low enough to merge fragments merges every real neighbour above it.
    assert fragment_iou < tightest_real


def test_a_fully_nested_fragment_also_survives_iou_suppression():
    """IoU is blind to containment: a box wholly inside another can have IoU 0.04."""
    outer = (0.0, 0.0, 100.0, 100.0)
    inner = (40.0, 40.0, 60.0, 60.0)
    assert detection.iou(outer, inner) == pytest.approx(0.04, abs=0.005)
    assert intersection_over_smaller(outer, inner) == pytest.approx(1.0)
    dets = [detection.Detection(id=1, box=outer, score=0.9),
            detection.Detection(id=2, box=inner, score=0.8)]
    assert len(detection.suppress_duplicates(dets, 0.40)) == 2


# --------------------------------------------------------------------------- #
# Anti-deletion guard, on the validated scene
# --------------------------------------------------------------------------- #

def test_shipped_suppression_removes_nothing_from_the_validated_scene(validated_boxes):
    """695 in, 695 out. The stage the docs once credited with 993 -> 695 removes zero
    boxes; that reduction is entirely the confidence filter."""
    assert len(validated_boxes) == 695
    kept = detection.suppress_duplicates(list(validated_boxes), detection.DEFAULT_IOU)
    assert len(kept) == 695


def test_validated_scene_geometry_is_frozen(validated_boxes):
    """Three numbers that any over-aggressive suppression would move."""
    boxes = [d.box for d in validated_boxes]
    ious = [detection.iou(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:]]
    assert max(ious) == pytest.approx(0.1499, abs=0.001)   # under DeepForest's own 0.15

    contained = sum(
        1 for i, a in enumerate(boxes) for b in boxes[i + 1:]
        if intersection_over_smaller(a, b) >= 0.70
    )
    assert contained == 1        # so containment suppression has nothing to remove either


def test_measured_real_neighbours_are_never_merged(validated_boxes):
    """The false-merge guard, built from real adjacent crowns rather than a synthetic pair.

    The closest genuine neighbours on this scene sit at IoU ~0.14. Any threshold at or
    below that starts merging real trees, which is the failure mode the constraints
    forbid — so this pins that the shipped threshold keeps them both.
    """
    boxes = [d.box for d in validated_boxes]
    pairs = [
        (detection.iou(a, b), i, j)
        for i, a in enumerate(boxes) for j, b in enumerate(boxes[i + 1:], i + 1)
        if detection.iou(a, b) > 0
    ]
    tightest_iou, i, j = max(pairs)
    assert tightest_iou < 0.15          # every real pair is below DeepForest's own NMS

    pair = [validated_boxes[i], validated_boxes[j]]
    for threshold in (0.15, 0.25, 0.40, 0.90):
        assert len(detection.suppress_duplicates(list(pair), threshold)) == 2, (
            f"real neighbours at IoU {tightest_iou:.4f} merged at threshold {threshold}"
        )


# --------------------------------------------------------------------------- #
# The direct regression test for the reported symptom
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not SLOW, reason="needs model weights; set FORESTLENS_SLOW_TESTS=1")
@pytest.mark.skipif(not detection.available(), reason="no detector installed")
def test_detected_crown_size_does_not_depend_on_tile_size():
    """Crown fragmentation shows up as a collapse in median box width, which a count
    assertion alone would not catch. Measured before the fix: 6.9 / 10.3 / 13.8 px at
    tile 400 / 600 / 800 (a 2.0x swing). After: 13.8 / 13.8 / 13.8.
    """
    widths = []
    for patch in (400, 600, 800):
        source = io_utils.load_image(
            Path(__file__).parents[1] / "data" / "sample" / "bc_open_canopy.tif"
        )
        result = pipeline.analyse(
            source, pipeline.Options(use_segmentation=False, patch_size=patch)
        )
        widths.append(float(np.median([np.sqrt(c.pixel_area) for c in result.crowns])))

    assert max(widths) / min(widths) < 1.2, f"median box width varies with tile size: {widths}"


def test_run_metadata_records_who_removed_what(monkeypatch):
    """The attribution that four documents once got backwards is now in every run.

    Without this, discovering that suppression is inert needs a measurement session.
    """
    raw = [
        detection.Detection(id=1, box=(0.0, 0.0, 40.0, 40.0), score=0.90),
        detection.Detection(id=2, box=(60.0, 60.0, 100.0, 100.0), score=0.80),
        detection.Detection(id=3, box=(200.0, 200.0, 240.0, 240.0), score=0.11),  # dropped
    ]

    def fake_detect(image, **kwargs):
        stats = kwargs.get("stats")
        scored = [d for d in raw if d.score >= kwargs.get("min_score", 0.25)]
        kept = detection.suppress_duplicates(list(scored), kwargs.get("iou_threshold", 0.4))
        if stats is not None:
            stats.update(raw=len(raw), after_confidence=len(scored),
                         after_suppression=len(kept),
                         removed_by_suppression=len(scored) - len(kept))
        return kept

    monkeypatch.setattr(detection, "detect", fake_detect)
    monkeypatch.setattr(detection, "describe_backend", lambda: {"backend": "stub"})
    result = pipeline.analyse(scene(gsd=0.10), pipeline.Options(use_segmentation=False))

    stage = next(s for s in result.run["stages"] if s.startswith("detection:"))
    assert "3 raw" in stage
    assert "2 after confidence" in stage
    assert "0 removed" in stage
