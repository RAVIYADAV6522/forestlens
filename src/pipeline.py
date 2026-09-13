"""Orchestration: imagery in, auditable result out."""

from __future__ import annotations

import platform
import resource
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import cover, detection, io_utils, metrics, segmentation
from .io_utils import GSD_METADATA, GSD_USER, ImageSource
from .metrics import Crown


#: The GSD the pretrained DeepForest tree model was trained on (NEON airborne RGB).
#: Coarser imagery is resampled to this scale for detection — see docs/SPEC.md §4.
MODEL_TRAINING_GSD = 0.10


def peak_rss_mb() -> float:
    """Peak resident memory of this process, in MB.

    Reported in every run's metadata so the deployed app measures its own footprint
    instead of relying on a host's documented limit. Note the unit difference:
    getrusage returns bytes on macOS and kilobytes on Linux.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(peak / divisor, 1)


@dataclass
class Options:
    min_score: float = detection.DEFAULT_SCORE
    iou_threshold: float = detection.DEFAULT_IOU
    patch_size: int = detection.DEFAULT_PATCH
    patch_overlap: float = detection.DEFAULT_OVERLAP
    use_segmentation: bool = True
    low_memory: bool = True
    segmentation_checkpoint: str = segmentation.DEFAULT_CHECKPOINT
    #: Skip segmentation above this many crowns. Masks cost ~0.12 s each on Apple MPS but
    #: several times that on a CPU host, so a 695-crown scene would stall a free-tier demo
    #: for minutes. Box areas are already honest and labelled, so skipping degrades
    #: gracefully rather than hanging.
    max_segmentation_crowns: int = 250
    match_model_gsd: bool = True
    model_training_gsd: float = MODEL_TRAINING_GSD
    #: Approximate crown width in pixels, for imagery with no GSD. Lets an ordinary
    #: photograph be scale-matched; ignored when the raster supplies a GSD, which is
    #: the more reliable basis.
    apparent_crown_px: float | None = None


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


def rescale_detections(detections, scale: float):
    """Map boxes found on a resampled image back into source-raster pixels.

    Everything downstream — annotation, area, GeoJSON — then works in the source
    grid, so a resampled run and a native run are directly comparable.
    """
    for det in detections:
        x1, y1, x2, y2 = det.box
        det.box = (x1 / scale, y1 / scale, x2 / scale, y2 / scale)
    return detections


def analyse(source: ImageSource, options: Options | None = None) -> Result:
    options = options or Options()
    started = time.perf_counter()
    stages: list[str] = []
    extra_warnings: list[str] = []

    array, scale, resample_note = (source.array, 1.0, None)
    if options.match_model_gsd:
        array, scale, resample_note = io_utils.resample_for_detection(
            source,
            options.model_training_gsd,
            apparent_crown_px=options.apparent_crown_px,
            patch_size=options.patch_size,
        )
    if resample_note:
        extra_warnings.append(resample_note)
    if scale != 1.0:
        stages.append(f"resample: {scale:.2f}x for detection input")

    counts: dict = {}
    detections = detection.detect(
        array,
        patch_size=options.patch_size,
        patch_overlap=options.patch_overlap,
        min_score=options.min_score,
        iou_threshold=options.iou_threshold,
        low_memory=options.low_memory,
        stats=counts,
    )
    if scale != 1.0:
        rescale_detections(detections, scale)
    detection.flag_edge_detections(detections, source.width, source.height)
    if counts:
        stages.append(
            f"detection: {counts['raw']} raw → {counts['after_confidence']} after confidence "
            f"→ {counts['after_suppression']} after suppression "
            f"({counts['removed_by_suppression']} removed)"
        )
    else:
        stages.append(f"detection: {len(detections)} accepted")

    # The whole-image branch of detect() resizes min(h, w) to NETWORK_MIN_SIZE rather than
    # patch_size, so the scale correction above does not apply to it.
    if max(array.shape[:2]) <= options.patch_size:
        extra_warnings.append(
            f"This image is smaller than the {options.patch_size} px tile size, so detection "
            f"ran on the whole image at once. The detector rescales it to "
            f"{io_utils.NETWORK_MIN_SIZE:.0f} px based on its shorter side "
            f"({min(array.shape[:2])} px), not on the tile size, so the scale match is off by "
            f"a factor of about {options.patch_size / max(min(array.shape[:2]), 1):.2f}. "
            "Crop or upload a larger image for a scale-matched count."
        )

    masks: dict = {}
    segmentation_error: str | None = None
    too_many = len(detections) > options.max_segmentation_crowns
    if options.use_segmentation and detections and too_many:
        stages.append(f"segmentation: skipped ({len(detections)} crowns)")
        extra_warnings.append(
            f"Crown-mask refinement was skipped because this scene has {len(detections)} "
            f"detections, above the {options.max_segmentation_crowns} limit set to keep the "
            "demo responsive. Crown areas below come from bounding boxes, which overestimate "
            "crown area by roughly 12-22% (measured; see docs/VALIDATION.md F8)."
        )
    elif options.use_segmentation and detections:
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
    summary["cover_bracket"] = cover.bracket(crowns, source.array)
    summary["detection_scale"] = scale
    # The resolution the weights actually operate at, which is not the resolution of the
    # array handed to the detector: every tile is rescaled to NETWORK_MIN_SIZE first.
    summary["network_gsd_m_per_px"] = (
        None
        if source.gsd is None
        else source.gsd / scale * options.patch_size / io_utils.NETWORK_MIN_SIZE
    )
    summary["detection_gsd_m_per_px"] = (
        None if source.gsd is None else source.gsd / scale
    )
    warnings = metrics.quality_warnings(summary, source.notes) + extra_warnings
    warnings.extend(metrics.cover_warnings(summary["cover_bracket"]))
    if source.gsd is not None and source.gsd > options.model_training_gsd * 1.25:
        warnings.append(
            f"Scene resolution is {source.gsd:.3f} m/px; the detector was trained on "
            f"~{options.model_training_gsd:.2f} m/px imagery. It is operating outside its "
            "training domain, so treat the count as a lower bound and expect smaller crowns "
            "to be missed."
        )
    if segmentation_error:
        warnings.insert(0, segmentation_error)

    run = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_s": round(time.perf_counter() - started, 2),
        "detection_scale": scale,
        "peak_rss_mb": peak_rss_mb(),
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
