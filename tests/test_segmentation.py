"""Crown-mask refinement.

SAM 2 defaults to CUDA, which this project never has, so device selection is pinned
here. The mask-acceptance rules are pinned too: a mask that barely fills its box is
rejected and that crown keeps a labelled box proxy rather than a bad outline.
"""

import numpy as np
import pytest

from src import metrics, segmentation
from src.detection import Detection


def test_device_preference_never_includes_cuda():
    devices = segmentation.available_devices()
    assert "cuda" not in devices
    assert devices[-1] == "cpu"  # cpu is always the final fallback


def test_describe_backend_reports_availability():
    info = segmentation.describe_backend()
    assert info["backend"] == "sam2"
    assert isinstance(info["available"], bool)


def test_missing_segmenter_raises_a_clear_error(monkeypatch):
    def boom(*args, **kwargs):
        raise segmentation.SegmenterUnavailable("SAM 2 is not installed; falling back to proxy.")

    monkeypatch.setattr(segmentation, "load_predictor", boom)
    with pytest.raises(segmentation.SegmenterUnavailable, match="proxy"):
        segmentation.refine(np.zeros((10, 10, 3), dtype=np.uint8), [])


def test_low_fill_mask_is_rejected_and_flagged(monkeypatch):
    """A mask filling 1% of its box is not a crown outline; keep the proxy instead."""
    class Predictor:
        def set_image(self, image):
            self.shape = image.shape[:2]

        def predict(self, box, multimask_output=False):
            mask = np.zeros(self.shape, dtype=bool)
            mask[0:5, 0:5] = True  # 25 px inside a 50x50 box
            return mask[None, ...], np.array([0.9]), None

    monkeypatch.setattr(segmentation, "load_predictor", lambda *a, **k: Predictor())
    detection = Detection(id=1, box=(0.0, 0.0, 50.0, 50.0), score=0.9)
    masks = segmentation.refine(np.zeros((50, 50, 3), dtype=np.uint8), [detection])

    assert masks == {}
    assert "mask_rejected_low_fill" in detection.flags
    crown = metrics.build_crowns([detection])[0]
    assert crown.area_basis == metrics.AREA_FROM_BOX
    assert crown.pixel_area == 2500.0


def test_accepted_mask_replaces_box_area(monkeypatch):
    class Predictor:
        def set_image(self, image):
            self.shape = image.shape[:2]

        def predict(self, box, multimask_output=False):
            mask = np.zeros(self.shape, dtype=bool)
            mask[5:45, 5:45] = True  # 1600 px inside a 2500 px box -> 0.64x
            return mask[None, ...], np.array([0.9]), None

    monkeypatch.setattr(segmentation, "load_predictor", lambda *a, **k: Predictor())
    detection = Detection(id=1, box=(0.0, 0.0, 50.0, 50.0), score=0.9)
    masks = segmentation.refine(np.zeros((50, 50, 3), dtype=np.uint8), [detection])

    crown = metrics.build_crowns([detection], masks)[0]
    assert crown.area_basis == metrics.AREA_FROM_MASK
    assert crown.pixel_area == 1600.0
    assert crown.pixel_area < detection.box_pixel_area  # masks pull inside boxes
