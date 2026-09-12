"""Orchestration: imagery in, auditable result out."""

from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import detection, io_utils, metrics, segmentation
from .io_utils import GSD_METADATA, GSD_USER, ImageSource
from .metrics import Crown


@dataclass
class Options:
    min_score: float = detection.DEFAULT_SCORE
    iou_threshold: float = detection.DEFAULT_IOU
    patch_size: int = detection.DEFAULT_PATCH
    patch_overlap: float = detection.DEFAULT_OVERLAP
    use_segmentation: bool = True
    segmentation_checkpoint: str = segmentation.DEFAULT_CHECKPOINT


@dataclass
class Result:
    source: ImageSource
    crowns: list[Crown]
    summary: dict
    warnings: list[str]
    run: dict = field(default_factory=dict)

    @property
    def tree_count(self) -> int:
        return self.summary["tree_count"]

    def rows(self) -> list[dict]:
        return io_utils.crowns_to_rows(self.crowns, self.source.gsd)

    def metadata(self) -> dict:
        """Everything needed to reproduce or audit this run."""
        return {
            "run": self.run,
            "image": {
                "name": self.source.name,
                "width": self.source.width,
                "height": self.source.height,
                "gsd_m_per_px": self.source.gsd,
                "gsd_origin": self.source.gsd_origin,
                "crs": self.source.crs,
                "georeferenced": self.source.georeferenced,
                "notes": self.source.notes,
            },
            "summary": self.summary,
            "warnings": self.warnings,
        }


def apply_gsd(source: ImageSource, gsd: float | None) -> ImageSource:
    """Attach a user-supplied GSD without overwriting one read from metadata."""
    if gsd is None or gsd <= 0:
        return source
    if source.gsd_origin == GSD_METADATA:
        if abs(source.gsd - gsd) / max(source.gsd, 1e-9) > 0.05:
            source.notes.append(
                f"User supplied GSD {gsd} m/px but raster metadata says "
                f"{source.gsd:.4f} m/px; metadata was kept."
            )
        return source
    source.gsd = float(gsd)
    source.gsd_origin = GSD_USER
    return source


def analyse(source: ImageSource, options: Options | None = None) -> Result:
    options = options or Options()
    started = time.perf_counter()
    stages: list[str] = []

    detections = detection.detect(
        source.array,
        patch_size=options.patch_size,
        patch_overlap=options.patch_overlap,
        min_score=options.min_score,
        iou_threshold=options.iou_threshold,
    )
    detection.flag_edge_detections(detections, source.width, source.height)
    stages.append(f"detection: {len(detections)} accepted")

    masks: dict = {}
    segmentation_error: str | None = None
    if options.use_segmentation and detections:
        try:
            masks = segmentation.refine(
                source.array, detections, checkpoint=options.segmentation_checkpoint
            )
            stages.append(f"segmentation: {len(masks)} crown masks")
        except segmentation.SegmenterUnavailable as exc:
            segmentation_error = str(exc)
            stages.append("segmentation: skipped")
    elif not options.use_segmentation:
        stages.append("segmentation: disabled by user")

    crowns = metrics.build_crowns(detections, masks)
    summary = metrics.summarise(crowns, source.gsd, source.ground_area_m2())
    warnings = metrics.quality_warnings(summary, source.notes)
    if segmentation_error:
        warnings.insert(0, segmentation_error)

    run = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_s": round(time.perf_counter() - started, 2),
        "stages": stages,
        "options": asdict(options),
        "detector": detection.describe_backend(),
        "segmenter": segmentation.describe_backend(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    return Result(source=source, crowns=crowns, summary=summary, warnings=warnings, run=run)


def export_all(result: Result, out_dir: str | Path, stem: str | None = None) -> dict[str, Path]:
    """Write the annotated image, CSV, optional GeoJSON and run metadata."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or Path(result.source.name).stem or "run"

    written: dict[str, Path] = {}
    annotated = io_utils.annotate(result.source, result.crowns)
    written["png"] = out_dir / f"{stem}_annotated.png"
    annotated.save(written["png"])
    written["csv"] = io_utils.write_csv(out_dir / f"{stem}_crowns.csv", result.crowns, result.source.gsd)
    geojson = io_utils.write_geojson(out_dir / f"{stem}_crowns.geojson", result.source, result.crowns)
    if geojson:
        written["geojson"] = geojson
    written["metadata"] = io_utils.write_json(out_dir / f"{stem}_run.json", result.metadata())
    return written
