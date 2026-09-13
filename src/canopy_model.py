"""Semantic canopy cover from a segmentation model, as an alternative upper bound.

`cover.py` bounds canopy cover above with an Excess Green index. That index is cheap,
scale-free and explainable, but it is fooled by anything green: measured on our own
imagery it reported **94.3% vegetation on open lake water**, because turbid water really
is green-dominant in RGB.

This module offers a semantic alternative — a SegFormer trained on ADE20K, whose label
set contains `tree` and `plant` — and it is a genuine improvement on exactly the cases
that defeat the index:

    scene                 expected              ExG      SegFormer
    closed mixed canopy   ~95-100%             93.9%       93.0%
    open pine over grass  well under 90%       92.6%       86.2%
    open water (control)  0%                  *94.3%*      29.3%
    urban (control)       street trees only    31.0%        1.7%

It is **not** a solution, and it is not the default. Two reasons, both measured:

1. It is badly scale-dependent on nadir imagery. The same open-canopy scene reads 86.2%
   whole-image and **1.6%** when tiled at 512 px — a 54x swing from the feeding strategy
   alone. ADE20K is ground-level photography, so the model has no stable prior for what
   a forest looks like from directly above. Whole-image inference is what the table above
   measures and what this module does; the tiled figure is recorded here so nobody
   "improves" it by tiling without knowing.
2. It still reports 25-29% tree on open water. Better than 94.3%, still wrong.

So the honest position is that this estimator narrows the upper bound on the cases that
embarrassed the index, while introducing a scale sensitivity the index does not have.
Both are offered, whichever is used is recorded in the run metadata, and neither is
presented as a measurement of canopy cover.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

#: SegFormer-B0 fine-tuned on ADE20K. ~15 MB, and `transformers` already ships as a
#: DeepForest dependency, so this adds no new heavy requirement.
DEFAULT_CHECKPOINT = "nvidia/segformer-b0-finetuned-ade-512-512"

#: ADE20K labels counted as canopy. `tree` is the one that matters; `plant` is included
#: because on nadir imagery the two are frequently confused with each other, and
#: excluding it would bias the *upper* bound downwards — the wrong direction for a bound.
CANOPY_LABELS = ("tree", "plant", "palm, palm tree")

#: Measured on `bc_open_canopy`: 86.2% whole-image against 1.6% tiled at 512 px. Recorded
#: so the sensitivity is discoverable from the code, not only from the validation doc.
TILED_SENSITIVITY_NOTE = (
    "Whole-image inference. Tiling this model at 512 px moved the same scene from 86.2% "
    "to 1.6%, so the feeding strategy is load-bearing and is fixed here deliberately."
)


class CanopyModelUnavailable(RuntimeError):
    """Raised when the semantic canopy model cannot be loaded."""


def available() -> bool:
    try:
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def describe_backend() -> dict:
    info = {
        "backend": "segformer",
        "checkpoint": DEFAULT_CHECKPOINT,
        "available": available(),
        "version": None,
    }
    if info["available"]:
        import transformers

        info["version"] = getattr(transformers, "__version__", "unknown")
    return info


@lru_cache(maxsize=1)
def load_model(checkpoint: str = DEFAULT_CHECKPOINT):
    """Load the processor and network once per process."""
    try:
        from transformers import SegformerForSemanticSegmentation, SegformerImageProcessor
    except ImportError as exc:
        raise CanopyModelUnavailable(
            "transformers is not installed, so the semantic canopy bound is unavailable; "
            "the vegetation index is used instead."
        ) from exc

    try:
        processor = SegformerImageProcessor.from_pretrained(checkpoint)
        model = SegformerForSemanticSegmentation.from_pretrained(checkpoint)
    except Exception as exc:  # pragma: no cover - network/weights dependent
        raise CanopyModelUnavailable(
            f"Could not load the semantic canopy model ({checkpoint}): {exc}"
        ) from exc

    model.eval()
    labels = {
        index: name
        for index, name in model.config.id2label.items()
        if name.strip().lower() in CANOPY_LABELS
    }
    if not labels:
        raise CanopyModelUnavailable(
            f"{checkpoint} has no canopy-like class in its label set; refusing to guess "
            "which of its classes means 'tree'."
        )
    return processor, model, labels


def semantic_canopy_cover(array: np.ndarray, checkpoint: str = DEFAULT_CHECKPOINT) -> dict:
    """Fraction of pixels a segmentation model calls canopy.

    Whole-image inference at the model's own input size — see the module docstring for
    why the feeding strategy is not a free choice.
    """
    import torch
    from PIL import Image

    processor, model, labels = load_model(checkpoint)
    height, width = array.shape[:2]

    image = Image.fromarray(array)
    with torch.no_grad():
        logits = model(**processor(images=image, return_tensors="pt")).logits
        upsampled = torch.nn.functional.interpolate(
            logits, size=(height, width), mode="bilinear", align_corners=False
        )
    prediction = upsampled.argmax(1)[0].cpu().numpy()
    mask = np.isin(prediction, list(labels))

    return {
        "method": "segformer_ade20k",
        "checkpoint": checkpoint,
        "labels_used": sorted(labels.values()),
        "fraction": float(mask.mean()),
        "mask": mask,
        "caveat": (
            "Semantic canopy from a SegFormer trained on ADE20K, which is ground-level "
            "photography rather than overhead imagery. Measured against the vegetation "
            "index it is far better on negative controls (open water 29.3% against 94.3%, "
            "urban 1.7% against 31.0%) and comparable on closed canopy — but it still "
            "calls a quarter of open water 'tree', and it is scale-sensitive: the same "
            "scene reads 86.2% whole-image and 1.6% tiled. Treat it as a narrowed upper "
            "bound, not a measurement."
        ),
        "scale_note": TILED_SENSITIVITY_NOTE,
    }
