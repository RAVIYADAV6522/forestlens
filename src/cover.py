"""Canopy cover, measured two independent ways so the uncertainty is visible.

Summing detected crown boxes badly underestimates cover in closed canopy: the
detector fires on separable crown apexes, so its boxes never tile interlocking
canopy (see docs/VALIDATION.md F3/F4). A single number from that method would be
wrong and confidently so.

Instead this module brackets the answer:

* **Lower bound** — the *union* of detected crown footprints. A union, not a sum,
  because overlapping boxes must not be double counted. It is a lower bound
  because undetected crowns contribute nothing.
* **Approximate upper bound** — green vegetation cover from a plain Excess Green
  index with a fixed threshold. It runs high relative to tree canopy because
  grass, shrubs and crops are green too and the index cannot tell them from
  trees. It is *approximate*, not a guaranteed bound: deeply shadowed canopy can
  fall below the threshold and be missed.

True tree canopy cover lies near or between the two. When the bracket is wide,
that width is the finding — not something to average away.

Otsu's method was tried first for the threshold and rejected: it assumes a
bimodal histogram with two real classes, so on a near-uniformly vegetated image
it splits *within* the vegetation distribution (sunlit against shaded crown) and
reported 62% cover on a visibly ~100% closed canopy. A fixed, stated threshold is
less clever and more honest. Otsu is still computed and reported as a diagnostic.
"""

from __future__ import annotations

import numpy as np

#: Vegetation rule: ExG = 2G - R - B > 0, i.e. green exceeds the mean of red and blue.
#: Fixed and stated rather than fitted, so the number is reproducible and explainable.
VEGETATION_RULE = "excess_green_positive"
VEGETATION_THRESHOLD = 0.0
SENSITIVITY_THRESHOLDS = (0.0, 5.0, 10.0, 20.0)


def excess_green(array: np.ndarray) -> np.ndarray:
    """ExG = 2G - R - B on 0-255 RGB. Positive where green dominates."""
    rgb = array.astype(np.float32)
    return 2.0 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]


def otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    """Otsu's method: the threshold maximising between-class variance.

    Implemented here rather than pulled from scikit-image to keep the deployed
    dependency set small, and because the whole point of this cross-check is that
    it is simple enough to explain in one paragraph.
    """
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    counts, edges = np.histogram(finite, bins=bins)
    counts = counts.astype(np.float64)
    total = counts.sum()
    if total == 0:
        return float(edges[0])

    centres = (edges[:-1] + edges[1:]) / 2
    weight_bg = np.cumsum(counts)
    weight_fg = total - weight_bg
    valid = (weight_bg > 0) & (weight_fg > 0)
    if not valid.any():
        return float(np.median(finite))

    cumulative = np.cumsum(counts * centres)
    mean_bg = np.where(weight_bg > 0, cumulative / np.maximum(weight_bg, 1), 0.0)
    total_mean = cumulative[-1]
    mean_fg = np.where(
        weight_fg > 0, (total_mean - cumulative) / np.maximum(weight_fg, 1), 0.0
    )
    between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
    between[~valid] = -np.inf
    return float(centres[int(np.argmax(between))])


def local_std(gray: np.ndarray, window: int = 5) -> np.ndarray:
    """Local standard deviation via integral images: sqrt(E[x^2] - E[x]^2).

    Canopy is strongly textured; water and roofs are smooth. Used to *flag* when the
    vegetation index may be counting smooth green surfaces — not to filter them out,
    for the reason documented in `texture_report`.
    """
    g = gray.astype(np.float64)
    pad = window // 2
    padded = np.pad(g, pad, mode="reflect")
    sum1 = np.pad(np.cumsum(np.cumsum(padded, 0), 1), ((1, 0), (1, 0)))
    sum2 = np.pad(np.cumsum(np.cumsum(padded**2, 0), 1), ((1, 0), (1, 0)))
    height, width = g.shape

    def box(integral):
        return (
            integral[window : window + height, window : window + width]
            - integral[0:height, window : window + width]
            - integral[window : window + height, 0:width]
            + integral[0:height, 0:width]
        )

    count = window * window
    mean = box(sum1) / count
    variance = np.maximum(box(sum2) / count - mean**2, 0.0)
    return np.sqrt(variance)


#: Below this median local standard deviation, vegetation-classified pixels are smooth
#: enough that water or painted surfaces are a live possibility. Calibrated by measuring
#: our own scenes (open water 4.9, closed canopy 19.5) — a flag, not a classifier.
SMOOTH_VEGETATION_STD = 6.0


def texture_report(array: np.ndarray, vegetation_mask: np.ndarray) -> dict:
    """Texture of the pixels called vegetation, to flag smooth false positives.

    Texture is deliberately *not* used to filter the vegetation mask. Measured on our
    scenes, open water has a median local sigma of 4.9 while the open Okanagan pine
    stand has 6.1 — overlapping ranges. Any threshold that removed the lake would also
    delete most of a legitimate forest scene, so this reports a risk instead of
    applying a correction that only looks right on one image.
    """
    sigma = local_std(array.mean(axis=2))
    selected = sigma[vegetation_mask]
    median = float(np.median(selected)) if selected.size else 0.0
    return {
        "median_vegetation_std": median,
        "smooth": median < SMOOTH_VEGETATION_STD,
        "threshold": SMOOTH_VEGETATION_STD,
    }


def green_vegetation_cover(
    array: np.ndarray, threshold: float = VEGETATION_THRESHOLD
) -> dict:
    """Fraction of pixels that read as green vegetation of any kind."""
    index = excess_green(array)
    mask = index > threshold
    sensitivity = {
        f"exg_gt_{t:g}": float((index > t).mean()) for t in SENSITIVITY_THRESHOLDS
    }
    return {
        "method": VEGETATION_RULE,
        "threshold": threshold,
        "fraction": float(mask.mean()),
        "mask": mask,
        "texture": texture_report(array, mask),
        "sensitivity": sensitivity,
        "otsu_threshold_diagnostic": otsu_threshold(index),
        "caveat": (
            "Green vegetation of any kind, including grass, shrubs and crops, so it runs "
            "high relative to tree canopy. It also counts any other green surface: measured "
            "on open lake water in our own imagery it reported 94.3% vegetation, because "
            "turbid water really is green-dominant in RGB. Deeply shadowed canopy can fall "
            "below the threshold and be missed. This is an approximation, not a guaranteed "
            "upper bound, and the threshold matters: see the sensitivity figures."
        ),
    }


def crown_union_fraction(crowns, height: int, width: int) -> tuple[float, np.ndarray]:
    """Fraction of the image covered by the union of crown footprints.

    Uses each crown's mask where one exists and its box otherwise, and unions them
    so overlapping detections are counted once.
    """
    canvas = np.zeros((height, width), dtype=bool)
    for crown in crowns:
        if crown.mask is not None:
            crop, x_off, y_off = crown.mask
            y_end = min(y_off + crop.shape[0], height)
            x_end = min(x_off + crop.shape[1], width)
            if y_end > y_off and x_end > x_off:
                canvas[y_off:y_end, x_off:x_end] |= crop[: y_end - y_off, : x_end - x_off]
            continue
        x1, y1, x2, y2 = crown.box
        cx1, cy1 = max(int(np.floor(x1)), 0), max(int(np.floor(y1)), 0)
        cx2, cy2 = min(int(np.ceil(x2)), width), min(int(np.ceil(y2)), height)
        if cx2 > cx1 and cy2 > cy1:
            canvas[cy1:cy2, cx1:cx2] = True
    return float(canvas.mean()), canvas


def bracket(crowns, array: np.ndarray) -> dict:
    """Bracket canopy cover between the detection union and green vegetation cover."""
    height, width = array.shape[:2]
    lower, _ = crown_union_fraction(crowns, height, width)
    vegetation = green_vegetation_cover(array)
    upper = vegetation["fraction"]

    result = {
        "lower_bound_pct": lower * 100,
        "upper_bound_pct": upper * 100,
        "vegetation_method": vegetation["method"],
        "vegetation_threshold": vegetation["threshold"],
        "vegetation_sensitivity": vegetation["sensitivity"],
        "vegetation_texture": vegetation["texture"],
        "vegetation_caveat": vegetation["caveat"],
        "otsu_threshold_diagnostic": vegetation["otsu_threshold_diagnostic"],
        "bracket_width_pct": abs(upper - lower) * 100,
        "inverted": upper < lower,
    }
    if result["inverted"]:
        result["note"] = (
            "Detected crowns cover more of the image than the green-vegetation index does. "
            "That inverts the expected ordering and usually means boxes are landing on "
            "non-vegetated ground, so both numbers should be treated as unreliable here."
        )
    return result
