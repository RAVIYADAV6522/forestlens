"""Image loading, raster metadata, tiling and export helpers."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

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
    path: Path | None = None
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
        path=path,
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
        path=path,
        gsd=gsd,
        gsd_origin=gsd_origin,
        crs=crs,
        transform=tuple(transform)[:6] if transform is not None else None,
        notes=notes,
    )


def from_array(array: np.ndarray, name: str = "uploaded image", **kwargs) -> ImageSource:
    return ImageSource(array=_to_rgb_uint8(np.asarray(array)), name=name, **kwargs)


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
                "area_m2": ("" if gsd is None else round(crown.area_m2(gsd), 3)),
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


MAX_DETECTION_PIXELS = 12_000_000  # ~3460x3460 RGB; bounds peak memory on a 1 GB host

#: Apparent crown width, in pixels, that the detector is tuned for. Measured: on a
#: 0.10 m/px scene whose crowns are ~85 px the mean detected box is 74 px, and the
#: mean box stays 47-74 px however far the image is zoomed — the detector looks for
#: objects of roughly this pixel size. Imagery whose crowns are much larger gets each
#: crown split into several boxes; much smaller and crowns are merged or missed.
MODEL_CROWN_PX = 75.0

#: Scales this close to 1 are not worth the resample.
NEUTRAL_SCALE = (0.8, 1.25)


def resample_for_detection(
    source: ImageSource,
    target_gsd: float,
    max_pixels: int = MAX_DETECTION_PIXELS,
    apparent_crown_px: float | None = None,
) -> tuple[np.ndarray, float, str | None]:
    """Resample so crowns occupy the pixel size the detector was tuned for.

    Two ways to derive the scale, in precedence order:

    * from the raster's GSD, against the detector's training GSD — the reliable path;
    * otherwise from a user-supplied apparent crown width in pixels, which is how an
      ordinary photograph with no geospatial metadata can still be scale-matched.

    Without either, detection runs at native scale and the caller is warned: imagery
    whose crowns are much wider than `MODEL_CROWN_PX` has each crown split into
    several boxes, which is the most common cause of a wildly inflated count.

    Returns (array, scale, note). Resampling adds no information — it only puts the
    imagery at the scale the model expects — so the caller must say so in the output.
    """
    low, high = NEUTRAL_SCALE

    if source.gsd is not None and target_gsd > 0:
        scale = source.gsd / target_gsd
        basis = (
            f"source imagery is {source.gsd:.3f} m/px against the detector's "
            f"~{target_gsd:.2f} m/px training resolution"
        )
    elif apparent_crown_px and apparent_crown_px > 0:
        scale = MODEL_CROWN_PX / apparent_crown_px
        basis = (
            f"crowns are about {apparent_crown_px:.0f} px wide in this image, against the "
            f"~{MODEL_CROWN_PX:.0f} px the detector is tuned for"
        )
    else:
        return (
            source.array,
            1.0,
            "This image carries no ground sampling distance and no crown width was given, so "
            f"detection ran at its native scale. The detector looks for crowns about "
            f"{MODEL_CROWN_PX:.0f} px wide: if the crowns here are much larger, each one is "
            "split into several boxes and the count is inflated; if much smaller, crowns are "
            "merged or missed. Set the approximate crown width to correct this.",
        )

    if low < scale < high:
        return source.array, 1.0, None

    capped = scale
    if scale > 1.0:
        capped = min(scale, (max_pixels / source.pixel_count) ** 0.5)
    # An upscale the memory cap has cut to 1x or below must fall back to native scale,
    # never invert into a downscale.
    if scale > 1.0 and capped <= high:
        return (
            source.array,
            1.0,
            f"Detection should have been upscaled, because {basis}, but the image is too "
            "large to resample within memory. Detection runs at native scale and will miss "
            "smaller crowns.",
        )

    width, height = max(round(source.width * capped), 1), max(round(source.height * capped), 1)
    array = np.asarray(
        Image.fromarray(source.array).resize((width, height), Image.LANCZOS)
    )

    direction = "up" if capped > 1 else "down"
    note = (
        f"Imagery resampled {direction} {capped:.2f}x for detection only, because {basis}. "
        "Resampling adds no detail; it only presents crowns at the pixel size the model "
        "expects. Areas are still computed in the source raster's grid."
    )
    if capped < scale:
        note += f" Scale was capped at {capped:.2f}x (from {scale:.2f}x) by the memory limit."
    return array, capped, note


def write_temp_raster(array: np.ndarray, gsd: float | None = None) -> Path | None:
    """Write an array to a temporary tiled GeoTIFF for windowed inference.

    DeepForest's low-memory path reads windows from a file rather than holding the
    whole image plus all its crops in RAM. Returns None when rasterio is missing, in
    which case the caller falls back to in-memory inference.
    """
    try:
        import rasterio
        from rasterio.transform import Affine
    except ImportError:
        return None

    import tempfile

    step = gsd or 1.0
    path = Path(tempfile.mkdtemp(prefix="forestlens-")) / "detection_input.tif"
    with rasterio.open(
        path, "w", driver="GTiff",
        height=array.shape[0], width=array.shape[1], count=3, dtype="uint8",
        # Origin offset from zero so the matrix is not flipped-identity, which GDAL
        # warns about and may discard.
        transform=Affine(step, 0, 0.0, 0, -step, array.shape[0] * step),
        tiled=True, blockxsize=256, blockysize=256, compress="deflate",
    ) as destination:
        destination.write(np.transpose(array, (2, 0, 1)))
    return path
