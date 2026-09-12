#!/usr/bin/env python
"""Regenerate the report and deck figures from the bundled scenes.

The figures are generated rather than screenshotted so their captions cannot drift
from the runs that produced them: each panel prints the count it contains, and
those are the counts quoted in docs/report and in the deck.

    python scripts/build_figures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import io_utils, pipeline  # noqa: E402

OUT = ROOT / "docs" / "report" / "figures"
WIDTH = 620

PANELS = (
    # key, scene, match_model_gsd
    ("native", "bc_open_canopy", False),
    ("resampled", "bc_open_canopy", True),
    ("closed", "ch_closed_canopy", True),
)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, scene, match in PANELS:
        source = io_utils.load_image(ROOT / "data" / "sample" / f"{scene}.tif")
        result = pipeline.analyse(
            source, pipeline.Options(use_segmentation=False, match_model_gsd=match)
        )
        image = io_utils.annotate(source, result.crowns)
        image = image.resize(
            (WIDTH, round(WIDTH * image.height / image.width)), Image.LANCZOS
        )
        path = OUT / f"fig_{key}.jpg"
        image.save(path, format="JPEG", quality=82, optimize=True)
        print(
            f"{path.name}: {result.tree_count} crowns, "
            f"scale {result.summary['detection_scale']:.2f}x, "
            f"{path.stat().st_size / 1024:.0f} KB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
