"""Crown-mask refinement.

Box-prompted segmentation turns each detection into a crown mask. This stage is
optional by design: when it is unavailable the pipeline falls back to bounding-box
area and labels that area a proxy everywhere it is reported.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

DEFAULT_CHECKPOINT = "facebook/sam2-hiera-small"


class SegmenterUnavailable(RuntimeError):
    """Raised when no segmentation model can be loaded."""


def available() -> bool:
    try:
        import sam2  # noqa: F401
    except ImportError:
        return False
    return True


def describe_backend() -> dict:
    info = {"backend": "sam2", "available": available(), "checkpoint": DEFAULT_CHECKPOINT}
    if info["available"]:
        import sam2

        info["version"] = getattr(sam2, "__version__", "unknown")
    return info


def available_devices() -> list[str]:
    """Devices to try, best first. SAM 2 defaults to CUDA, which we do not have."""
    import torch

    devices = []
    if torch.backends.mps.is_available():
        devices.append("mps")
    devices.append("cpu")
    return devices


@lru_cache(maxsize=1)
def load_predictor(checkpoint: str = DEFAULT_CHECKPOINT):
    try:
        from sam2.sam2_image_predictor import SAM2ImagePredictor
    except ImportError as exc:
        raise SegmenterUnavailable(
            "SAM 2 is not installed; crown areas will fall back to a bounding-box proxy."
        ) from exc

    errors = []
    for device in available_devices():
        try:
            return SAM2ImagePredictor.from_pretrained(checkpoint, device=device)
        except Exception as exc:  # pragma: no cover - device/weights dependent
            errors.append(f"{device}: {exc}")
    raise SegmenterUnavailable(
        f"Could not load SAM 2 weights ({checkpoint}). Tried " + "; ".join(errors)
    )


def refine(
    image: np.ndarray,
    detections,
    checkpoint: str = DEFAULT_CHECKPOINT,
    min_fill: float = 0.05,
) -> dict[int, tuple[np.ndarray, int, int]]:
    """Return {detection id: (bool mask crop, x offset, y offset)}.

    Masks are stored cropped to their detection box so memory stays bounded on
    large scenes. A mask that fills almost none of its box is rejected, and that
    crown keeps the box proxy instead.
    """
    predictor = load_predictor(checkpoint)
    predictor.set_image(image)

    masks: dict[int, tuple[np.ndarray, int, int]] = {}
    height, width = image.shape[:2]

    for detection in detections:
        x1, y1, x2, y2 = detection.box
        box = np.array([x1, y1, x2, y2], dtype=np.float32)
        try:
            result, scores, _ = predictor.predict(box=box[None, :], multimask_output=False)
        except Exception:
            continue

        mask = np.asarray(result).squeeze().astype(bool)
        if mask.ndim != 2 or mask.shape != (height, width):
            continue

        cx1, cy1 = int(max(np.floor(x1), 0)), int(max(np.floor(y1), 0))
        cx2, cy2 = int(min(np.ceil(x2), width)), int(min(np.ceil(y2), height))
        crop = mask[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            continue

        fill = crop.sum() / crop.size
        if fill < min_fill:
            detection.flags.append("mask_rejected_low_fill")
            continue

        masks[detection.id] = (crop, cx1, cy1)

    return masks
