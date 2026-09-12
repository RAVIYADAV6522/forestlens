"""Image loading, raster metadata, tiling and export helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None

RASTER_SUFFIXES = {".tif", ".tiff"}

GSD_METADATA = "metadata"
GSD_USER = "user"
GSD_UNKNOWN = "unknown"


@dataclass
class ImageSource:
    """An image plus everything we know about how it maps to the ground."""

    array: np.ndarray
    name: str
    gsd: float | None = None
    gsd_origin: str = GSD_UNKNOWN
    crs: str | None = None
    transform: tuple | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def height(self) -> int:
        return self.array.shape[0]

    @property
    def width(self) -> int:
        return self.array.shape[1]

    @property
    def pixel_count(self) -> int:
        return self.height * self.width

    @property
    def georeferenced(self) -> bool:
        return self.transform is not None and self.crs is not None

    def ground_area_m2(self) -> float | None:
        if self.gsd is None:
            return None
        return self.pixel_count * self.gsd**2


def _to_rgb_uint8(array: np.ndarray) -> np.ndarray:
    if array.ndim == 2:
        array = np.stack([array] * 3, axis=-1)
    if array.shape[-1] > 3:
        array = array[..., :3]
    if array.dtype == np.uint8:
        return np.ascontiguousarray(array)

    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return np.zeros(array.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, [2, 98])
    if hi <= lo:
        lo, hi = float(finite.min()), float(finite.max() or 1.0)
    scaled = (array.astype(np.float32) - lo) / max(hi - lo, 1e-6)
    return np.ascontiguousarray((np.clip(scaled, 0, 1) * 255).astype(np.uint8))


def load_image(path: str | Path) -> ImageSource:
    """Load an image, preferring rasterio so GeoTIFF metadata survives."""
    path = Path(path)
    if path.suffix.lower() in RASTER_SUFFIXES:
        source = _load_raster(path)
        if source is not None:
            return source
    with Image.open(path) as handle:
        array = np.array(handle.convert("RGB"))
    return ImageSource(
        array=array,
        name=path.name,
        notes=["No geospatial metadata: ground sampling distance must be supplied by the user."],
    )


def _load_raster(path: Path) -> ImageSource | None:
    try:
        import rasterio
    except ImportError:
        return None

    with rasterio.open(path) as dataset:
        array = dataset.read(indexes=list(range(1, min(dataset.count, 3) + 1)))
        array = np.transpose(array, (1, 2, 0))
        transform = dataset.transform
        crs = str(dataset.crs) if dataset.crs else None
        notes: list[str] = []
        gsd: float | None = None
        gsd_origin = GSD_UNKNOWN

        if transform is not None and not transform.is_identity:
            x_res, y_res = abs(transform.a), abs(transform.e)
            if crs and getattr(dataset.crs, "is_geographic", False):
                notes.append(
                    "Raster is in a geographic CRS (degrees). Pixel size was not converted to "
                    "metres; supply the ground sampling distance in metres/pixel."
                )
            elif x_res > 0 and y_res > 0:
                gsd = float((x_res + y_res) / 2)
                gsd_origin = GSD_METADATA
                if abs(x_res - y_res) / max(x_res, y_res) > 0.01:
                    notes.append(
                        f"Non-square pixels ({x_res:.4f} x {y_res:.4f}); using the mean as GSD."
                    )
        if gsd is None and gsd_origin == GSD_UNKNOWN:
            notes.append("Raster carries no usable metric pixel size.")

    return ImageSource(
        array=_to_rgb_uint8(array),
        name=path.name,
        gsd=gsd,
        gsd_origin=gsd_origin,
        crs=crs,
        transform=tuple(transform)[:6] if transform is not None else None,
        notes=notes,
    )


def from_array(array: np.ndarray, name: str = "uploaded image", **kwargs) -> ImageSource:
    return ImageSource(array=_to_rgb_uint8(np.asarray(array)), name=name, **kwargs)


def tiles(width: int, height: int, size: int, overlap: int) -> Iterator[tuple[int, int, int, int]]:
    """Yield (x1, y1, x2, y2) tiles covering the image with a fixed overlap."""
    if size <= 0:
        raise ValueError("tile size must be positive")
    step = max(size - overlap, 1)
    ys = list(range(0, max(height - overlap, 1), step))
    xs = list(range(0, max(width - overlap, 1), step))
    for y in ys:
        for x in xs:
            x2, y2 = min(x + size, width), min(y + size, height)
            yield max(x2 - size, 0), max(y2 - size, 0), x2, y2


def annotate(source: ImageSource, crowns, draw_masks: bool = True) -> Image.Image:
    """Draw crown outlines (and masks where available) onto the source image."""
    base = Image.fromarray(source.array).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    canvas = ImageDraw.Draw(overlay)

    for crown in crowns:
        colour = (255, 92, 0) if crown.flags else (46, 204, 113)
        if draw_masks and crown.mask is not None:
            mask_crop, x_off, y_off = crown.mask
            tint = Image.new("RGBA", (mask_crop.shape[1], mask_crop.shape[0]), colour + (90,))
            alpha = Image.fromarray((mask_crop * 255).astype(np.uint8), mode="L")
            overlay.paste(tint, (int(x_off), int(y_off)), alpha)
        x1, y1, x2, y2 = crown.box
        canvas.rectangle([x1, y1, x2, y2], outline=colour + (255,), width=2)

    return Image.alpha_composite(base, overlay).convert("RGB")


CSV_COLUMNS = [
    "tree_id",
    "confidence",
    "x1",
    "y1",
    "x2",
    "y2",
    "pixel_area",
    "area_basis",
    "area_m2",
    "flags",
]


def crowns_to_rows(crowns, gsd: float | None) -> list[dict]:
    rows = []
    for crown in crowns:
        x1, y1, x2, y2 = crown.box
        rows.append(
            {
                "tree_id": crown.id,
                "confidence": round(crown.score, 4),
                "x1": round(x1, 2),
                "y1": round(y1, 2),
                "x2": round(x2, 2),
                "y2": round(y2, 2),
                "pixel_area": int(crown.pixel_area),
                "area_basis": crown.area_basis,
                "area_m2": ("" if gsd is None else round(crown.pixel_area * gsd**2, 3)),
                "flags": "|".join(crown.flags),
            }
        )
    return rows


def write_csv(path: str | Path, crowns, gsd: float | None) -> Path:
    path = Path(path)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(crowns_to_rows(crowns, gsd))
    return path


def _pixel_to_world(transform: tuple, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    return a * x + b * y + c, d * x + e * y + f


def crowns_to_geojson(source: ImageSource, crowns) -> dict | None:
    """Crown polygons in world coordinates. None when georeferencing is missing."""
    if not source.georeferenced:
        return None

    features = []
    for crown in crowns:
        ring = _crown_ring(crown)
        coords = [_pixel_to_world(source.transform, x, y) for x, y in ring]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {
                    "tree_id": crown.id,
                    "confidence": round(crown.score, 4),
                    "pixel_area": int(crown.pixel_area),
                    "area_basis": crown.area_basis,
                    "flags": crown.flags,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": source.crs}},
        "features": features,
    }


def _crown_ring(crown) -> list[tuple[float, float]]:
    if crown.mask is not None:
        ring = _mask_outline(crown)
        if ring is not None:
            return ring
    x1, y1, x2, y2 = crown.box
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]


def _mask_outline(crown) -> list[tuple[float, float]] | None:
    try:
        from rasterio.features import shapes
    except ImportError:
        return None
    mask_crop, x_off, y_off = crown.mask
    polygons = [
        geom
        for geom, value in shapes(mask_crop.astype(np.uint8), mask=mask_crop)
        if value == 1
    ]
    if not polygons:
        return None
    largest = max(polygons, key=lambda geom: len(geom["coordinates"][0]))
    return [(x + x_off, y + y_off) for x, y in largest["coordinates"][0]]


def write_geojson(path: str | Path, source: ImageSource, crowns) -> Path | None:
    payload = crowns_to_geojson(source, crowns)
    if payload is None:
        return None
    path = Path(path)
    path.write_text(json.dumps(payload, indent=2))
    return path


def write_json(path: str | Path, payload: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


MAX_DETECTION_PIXELS = 36_000_000  # ~6000x6000 RGB; keeps peak torch memory sane on 8 GB


def resample_for_detection(
    source: ImageSource, target_gsd: float, max_pixels: int = MAX_DETECTION_PIXELS
) -> tuple[np.ndarray, float, str | None]:
    """Upsample so crowns occupy the pixel size the detector was trained on.

    Returns (array, scale, note). Resampling adds no information — it only puts the
    imagery at the scale the model expects — so the caller must say so in the output.
    Scale is capped by `max_pixels` to stay within memory.
    """
    if source.gsd is None or target_gsd <= 0:
        return source.array, 1.0, None

    scale = source.gsd / target_gsd
    if scale <= 1.25:
        return source.array, 1.0, None

    capped = min(scale, (max_pixels / source.pixel_count) ** 0.5)
    if capped <= 1.25:
        return (
            source.array,
            1.0,
            f"Imagery at {source.gsd:.3f} m/px is coarser than the detector's training "
            f"resolution ({target_gsd:.2f} m/px), but the image is too large to resample "
            "within memory. Detection runs at native scale and will miss smaller crowns.",
        )

    width, height = round(source.width * capped), round(source.height * capped)
    array = np.asarray(
        Image.fromarray(source.array).resize((width, height), Image.LANCZOS)
    )

    note = (
        f"Imagery resampled {capped:.2f}x for detection only ({source.gsd:.3f} → "
        f"{source.gsd / capped:.3f} m/px effective) to match the detector's ~{target_gsd:.2f} "
        "m/px training resolution. Resampling adds no detail; it only presents crowns at the "
        "pixel size the model expects. Areas are still computed in the source raster's grid."
    )
    if capped < scale:
        note += (
            f" Scale was capped at {capped:.2f}x (from {scale:.2f}x) by the memory limit."
        )
    return array, capped, note
