#!/usr/bin/env python
"""Mechanical QA against the acceptance criteria in docs/SPEC.md §10.

Checks what a machine can check: reproducibility, that the area basis reaches every
export, that an unknown GSD really does withhold physical area, that the run metadata
carries the assumptions, and that no document has quietly acquired an accuracy claim.
The rest of the gate (a stranger can use it, the writeup is consistent) needs a human.

    python scripts/qa_check.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import io_utils, pipeline

ROOT = Path(__file__).resolve().parents[1]
ACCURACY_PHRASES = ("accuracy of", "% accurate", "precision of", "recall of", "f1 score")


def main() -> int:
    out = Path(tempfile.mkdtemp(prefix="forestlens-qa-"))
    checks: list[tuple[str, bool, str]] = []

    counts = []
    for _ in range(2):
        source = io_utils.load_image(ROOT / "data/sample/bc_open_canopy.tif")
        counts.append(
            pipeline.analyse(source, pipeline.Options(use_segmentation=False)).tree_count
        )
    checks.append(("A2 count reproducible", counts[0] == counts[1], f"{counts[0]} == {counts[1]}"))

    source = io_utils.load_image(ROOT / "data/sample/ch_closed_canopy.tif")
    result = pipeline.analyse(source)
    written = pipeline.export_all(result, out, stem="qa")
    csv_text = written["csv"].read_text()
    metadata = json.loads(written["metadata"].read_text())
    geojson = json.loads(written["geojson"].read_text())
    basis = result.summary["area_basis"][0]

    checks += [
        ("A1 detector runs", result.tree_count > 0, f"{result.tree_count} trees"),
        ("A4 basis in CSV", basis in csv_text, basis),
        ("A4 basis in GeoJSON", geojson["features"][0]["properties"]["area_basis"] == basis, "ok"),
        ("A4 basis in metadata", metadata["summary"]["area_basis"] == [basis], basis),
        (
            "A6 all exports written",
            all(p.exists() and p.stat().st_size > 0 for p in written.values()),
            ", ".join(written),
        ),
        ("A6 GeoJSON carries CRS", bool(geojson["crs"]["properties"]["name"]), geojson["crs"]["properties"]["name"]),
    ]

    joined = " ".join(result.warnings)
    checks += [
        ("A7 cover bracket stated", "No single cover figure is reported" in joined, ""),
        ("A7 confidence is not accuracy", "not measurement accuracy" in joined, ""),
        (
            "A7 metadata complete",
            {"detector", "segmenter", "options", "detection_scale", "timestamp_utc"}
            <= set(metadata["run"]),
            "",
        ),
    ]

    bare = io_utils.from_array(source.array[:256, :256], name="bare.png")
    no_gsd = pipeline.analyse(bare, pipeline.Options(use_segmentation=False))
    checks += [
        ("A3 unknown GSD withholds area", no_gsd.summary["total_canopy_area_m2"] is None, ""),
        ("A3 CSV area column blank", all(r["area_m2"] == "" for r in no_gsd.rows()), ""),
    ]

    offenders = [
        f"{doc.name}:{phrase}"
        for doc in (ROOT / "docs").glob("*.md")
        for phrase in ACCURACY_PHRASES
        if phrase in doc.read_text().lower()
    ]
    checks.append(("A9 no accuracy claim in docs", not offenders, ", ".join(offenders) or "clean"))

    shutil.rmtree(out, ignore_errors=True)

    width = max(len(name) for name, _, _ in checks)
    for name, ok, note in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:<{width}}  {note}")
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{passed}/{len(checks)} checks pass")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
