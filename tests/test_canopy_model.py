"""The semantic canopy upper bound, and the exact geometric lower bound.

The vegetation index is fooled by anything green — measured at 94.3% "vegetation" on
open lake water. A SegFormer alternative is far better on that control (29.3%) but it is
trained on ground-level photography and is scale-sensitive (86.2% whole-image against
1.6% tiled on the same scene), so it is offered rather than defaulted to, and whichever
was used is recorded.

Weights-free: the model is stubbed, because what needs pinning is the contract — the
fallback, the recorded provenance, and the refusal rule — not the network's output.
"""

from __future__ import annotations

import numpy as np
import pytest

from src import canopy_model, cover, metrics, pipeline
from src.detection import Detection


def rgb(r, g, b, size=64):
    a = np.zeros((size, size, 3), dtype=np.uint8)
    a[..., 0], a[..., 1], a[..., 2] = r, g, b
    return a


# --------------------------------------------------------------------------- #
# Exact geometric lower bound (shapely.ops.unary_union)
# --------------------------------------------------------------------------- #

def test_exact_union_counts_overlaps_once():
    crowns = metrics.build_crowns([
        Detection(id=1, box=(0.0, 0.0, 50.0, 50.0), score=0.9),
        Detection(id=2, box=(25.0, 0.0, 75.0, 50.0), score=0.9),
    ])
    fraction, method = cover.crown_union_fraction_exact(crowns, 100, 100)
    # Union spans x 0..75, y 0..50 = 3750 of 10000. The sum would be 5000.
    assert fraction == pytest.approx(0.375)
    assert method == "shapely_unary_union"


def test_exact_union_clips_to_the_image():
    crowns = metrics.build_crowns([Detection(id=1, box=(-20.0, -20.0, 50.0, 50.0), score=0.9)])
    fraction, _ = cover.crown_union_fraction_exact(crowns, 100, 100)
    assert fraction == pytest.approx(0.25)


def test_exact_union_is_not_inflated_by_fractional_coordinates():
    """Why this replaced the raster union: rasterising a fractional box with floor/ceil
    counts any touched pixel, which inflates a bound that is supposed to be a floor.
    Measured on bc_open_canopy: 17.03% raster against 15.07% exact."""
    crowns = metrics.build_crowns([Detection(id=1, box=(0.5, 0.5, 10.5, 10.5), score=0.9)])
    exact, _ = cover.crown_union_fraction_exact(crowns, 100, 100)
    raster, _ = cover.crown_union_fraction(crowns, 100, 100)
    assert exact == pytest.approx(0.01)      # exactly 10x10
    assert raster > exact                     # floor/ceil touches 11x11


def test_exact_union_falls_back_when_shapely_is_absent(monkeypatch):
    """The bound must always be available, so an absent shapely degrades rather than
    raising — and says which path produced the number."""
    import builtins

    real_import = builtins.__import__

    def no_shapely(name, *args, **kwargs):
        if name.startswith("shapely"):
            raise ImportError("no shapely")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_shapely)
    crowns = metrics.build_crowns([Detection(id=1, box=(0.0, 0.0, 50.0, 50.0), score=0.9)])
    fraction, method = cover.crown_union_fraction_exact(crowns, 100, 100)
    assert fraction == pytest.approx(0.25)
    assert method == "raster_union_shapely_unavailable"


# --------------------------------------------------------------------------- #
# Semantic upper bound
# --------------------------------------------------------------------------- #

def test_backend_description_is_honest_about_availability():
    info = canopy_model.describe_backend()
    assert info["backend"] == "segformer"
    assert "segformer" in info["checkpoint"]
    assert isinstance(info["available"], bool)


def test_canopy_labels_include_tree():
    assert "tree" in canopy_model.CANOPY_LABELS


def test_bracket_records_which_estimator_produced_the_upper_bound(monkeypatch):
    monkeypatch.setattr(
        canopy_model, "semantic_canopy_cover",
        lambda array, **k: {
            "method": "segformer_ade20k", "fraction": 0.80, "mask": None,
            "labels_used": ["plant", "tree"], "caveat": "stub", "checkpoint": "stub",
        },
    )
    crowns = metrics.build_crowns([Detection(id=1, box=(0.0, 0.0, 20.0, 20.0), score=0.9)])
    result = cover.bracket(crowns, rgb(50, 150, 50), upper_estimator="segformer")

    assert result["vegetation_method"] == "segformer_ade20k"
    assert result["upper_bound_pct"] == pytest.approx(80.0)
    assert result["upper_bound_labels"] == ["plant", "tree"]
    assert result["lower_bound_method"] == "shapely_unary_union"


def test_vegetation_index_remains_the_default(monkeypatch):
    crowns = metrics.build_crowns([Detection(id=1, box=(0.0, 0.0, 20.0, 20.0), score=0.9)])
    result = cover.bracket(crowns, rgb(50, 150, 50))
    assert result["vegetation_method"] == cover.VEGETATION_RULE


def test_unavailable_semantic_model_falls_back_with_a_warning(monkeypatch):
    """A missing optional model must not take the cover interval down with it."""
    def unavailable(array, **kwargs):
        raise canopy_model.CanopyModelUnavailable("transformers is not installed.")

    monkeypatch.setattr(canopy_model, "semantic_canopy_cover", unavailable)
    from src import detection as det

    monkeypatch.setattr(det, "detect", lambda image, **k: [])
    monkeypatch.setattr(det, "describe_backend", lambda: {"backend": "stub"})

    from src import io_utils

    source = io_utils.from_array(rgb(50, 150, 50, size=128))
    result = pipeline.analyse(
        source, pipeline.Options(use_segmentation=False, upper_bound="segformer")
    )
    assert result.summary["upper_bound_estimator"] == "vegetation_index"
    assert any("Falling back to the vegetation index" in w for w in result.warnings)


def test_refusal_rule_applies_whichever_estimator_is_used():
    """The 25-point rule is about the evidence, not about which model produced it."""
    warnings = metrics.cover_warnings({
        "lower_bound_pct": 21.0, "upper_bound_pct": 93.2, "bracket_width_pct": 72.2,
        "inverted": False, "vegetation_caveat": "semantic caveat",
    })
    assert any("No single cover figure is reported" in w for w in warnings)
