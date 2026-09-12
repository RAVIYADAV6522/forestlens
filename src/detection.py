"""Individual-tree detection.

The only real backend is a pretrained detector (DeepForest). There is deliberately
no synthetic fallback: if no detector is installed the pipeline reports that it
cannot count trees rather than producing numbers nobody can defend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

DEFAULT_PATCH = 800
DEFAULT_OVERLAP = 0.15
DEFAULT_SCORE = 0.25
DEFAULT_IOU = 0.4


class DetectorUnavailable(RuntimeError):
    """Raised when no pretrained tree detector can be loaded."""


@dataclass
class Detection:
    id: int
    box: tuple[float, float, float, float]
    score: float
    flags: list[str] = field(default_factory=list)

    @property
    def box_pixel_area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(x2 - x1, 0) * max(y2 - y1, 0)


def available() -> bool:
    try:
        import deepforest  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def load_detector():
    """Load the pretrained DeepForest tree model once per process."""
    try:
        from deepforest import main as deepforest_main
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise DetectorUnavailable(
            "DeepForest is not installed. Install the project requirements to enable detection."
        ) from exc

    model = deepforest_main.deepforest()
    for loader in (
        lambda: model.load_model("weecology/deepforest-tree"),
        lambda: model.use_release(),
    ):
        try:
            loader()
            break
        except Exception:  # pragma: no cover - API differs across versions
            continue
    else:
        raise DetectorUnavailable("Could not load pretrained DeepForest weights.")

    model.eval()
    return model


def describe_backend() -> dict:
    info = {"backend": "deepforest", "available": available(), "version": None}
    if info["available"]:
        import deepforest

        info["version"] = getattr(deepforest, "__version__", "unknown")
    return info


def detect(
    image: np.ndarray,
    patch_size: int = DEFAULT_PATCH,
    patch_overlap: float = DEFAULT_OVERLAP,
    min_score: float = DEFAULT_SCORE,
    iou_threshold: float = DEFAULT_IOU,
) -> list[Detection]:
    """Run tiled detection over an RGB array and return accepted detections."""
    model = load_detector()
    height, width = image.shape[:2]

    if max(height, width) <= patch_size:
        frame = model.predict_image(image=image.astype("float32"))
    else:
        frame = model.predict_tile(
            image=image.astype("float32"),
            patch_size=patch_size,
            patch_overlap=patch_overlap,
        )

    if frame is None or len(frame) == 0:
        return []

    raw = [
        Detection(
            id=0,
            box=(
                float(row["xmin"]),
                float(row["ymin"]),
                float(row["xmax"]),
                float(row["ymax"]),
            ),
            score=float(row.get("score", 0.0)),
        )
        for _, row in frame.iterrows()
    ]

    kept = suppress_duplicates([d for d in raw if d.score >= min_score], iou_threshold)
    for index, detection in enumerate(kept, start=1):
        detection.id = index
    return kept


def iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_w = min(ax2, bx2) - max(ax1, bx1)
    inter_h = min(ay2, by2) - max(ay1, by1)
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    intersection = inter_w * inter_h
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection
    return intersection / union if union > 0 else 0.0


def suppress_duplicates(detections: list[Detection], iou_threshold: float) -> list[Detection]:
    """Greedy NMS so overlapping tiles do not count the same tree twice."""
    kept: list[Detection] = []
    for detection in sorted(detections, key=lambda d: d.score, reverse=True):
        if all(iou(detection.box, other.box) < iou_threshold for other in kept):
            kept.append(detection)
    return kept


def flag_edge_detections(
    detections: list[Detection], width: int, height: int, margin: float = 2.0
) -> list[Detection]:
    """Mark detections touching the image border: their crowns are cut off."""
    for detection in detections:
        x1, y1, x2, y2 = detection.box
        if x1 <= margin or y1 <= margin or x2 >= width - margin or y2 >= height - margin:
            if "clipped_at_image_edge" not in detection.flags:
                detection.flags.append("clipped_at_image_edge")
    return detections
