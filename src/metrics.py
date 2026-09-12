"""Crown areas, canopy totals and the honesty rules around them."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

AREA_FROM_MASK = "segmentation_mask"
AREA_FROM_BOX = "bounding_box_proxy"


@dataclass
class Crown:
    """An accepted detection together with the area we are willing to claim."""

    id: int
    box: tuple[float, float, float, float]
    score: float
    pixel_area: float
    area_basis: str
    mask: tuple[np.ndarray, int, int] | None = None
    flags: list[str] = field(default_factory=list)

    def area_m2(self, gsd: float | None) -> float | None:
        return to_physical_area(self.pixel_area, gsd)


def build_crowns(detections, masks: dict | None = None) -> list[Crown]:
    """Combine detections with masks, falling back to box area per crown."""
    masks = masks or {}
    crowns = []
    for detection in detections:
        mask = masks.get(detection.id)
        if mask is not None:
            crop, x_off, y_off = mask
            crowns.append(
                Crown(
                    id=detection.id,
                    box=detection.box,
                    score=detection.score,
                    pixel_area=float(crop.sum()),
                    area_basis=AREA_FROM_MASK,
                    mask=mask,
                    flags=list(detection.flags),
                )
            )
        else:
            crowns.append(
                Crown(
                    id=detection.id,
                    box=detection.box,
                    score=detection.score,
                    pixel_area=float(detection.box_pixel_area),
                    area_basis=AREA_FROM_BOX,
                    flags=list(detection.flags),
                )
            )
    return crowns


def to_physical_area(pixel_area: float, gsd: float | None) -> float | None:
    """pixel count x GSD^2. None when GSD is unknown - never a guess.

    The single implementation of this conversion. Everything that reports an area in
    square metres goes through here, so the tests that pin this arithmetic are pinning
    the shipped numbers rather than a parallel copy of them.
    """
    if gsd is None:
        return None
    if gsd <= 0:
        raise ValueError("GSD must be positive")
    return pixel_area * gsd**2


def summarise(
    crowns: list[Crown],
    gsd: float | None,
    ground_area_m2: float | None = None,
) -> dict:
    """Headline metrics. Physical values are omitted entirely without a GSD."""
    pixel_areas = np.array([crown.pixel_area for crown in crowns], dtype=float)
    bases = {crown.area_basis for crown in crowns}

    summary: dict = {
        "tree_count": len(crowns),
        "total_canopy_pixels": float(pixel_areas.sum()) if len(crowns) else 0.0,
        "mean_crown_pixels": float(pixel_areas.mean()) if len(crowns) else None,
        "median_crown_pixels": float(np.median(pixel_areas)) if len(crowns) else None,
        "area_basis": sorted(bases) if bases else [],
        "mask_backed_crowns": sum(1 for c in crowns if c.area_basis == AREA_FROM_MASK),
        "proxy_crowns": sum(1 for c in crowns if c.area_basis == AREA_FROM_BOX),
        "flagged_crowns": sum(1 for c in crowns if c.flags),
        "mean_confidence": float(np.mean([c.score for c in crowns])) if len(crowns) else None,
        "gsd_m_per_px": gsd,
        "total_canopy_area_m2": None,
        "total_canopy_area_ha": None,
        "mean_crown_area_m2": None,
        "median_crown_area_m2": None,
        "analysed_ground_area_m2": ground_area_m2,
        "canopy_coverage_pct": None,
    }

    if gsd is not None and len(crowns):
        total_m2 = to_physical_area(summary["total_canopy_pixels"], gsd)
        summary["total_canopy_area_m2"] = total_m2
        summary["total_canopy_area_ha"] = total_m2 / 10_000
        summary["mean_crown_area_m2"] = to_physical_area(summary["mean_crown_pixels"], gsd)
        summary["median_crown_area_m2"] = to_physical_area(summary["median_crown_pixels"], gsd)
        if ground_area_m2:
            summary["canopy_coverage_pct"] = total_m2 / ground_area_m2 * 100

    return summary


def quality_warnings(summary: dict, source_notes: list[str] | None = None) -> list[str]:
    """Plain-language caveats the UI and the report must both show."""
    warnings = list(source_notes or [])

    if summary["gsd_m_per_px"] is None:
        warnings.append(
            "Ground sampling distance is unknown, so no physical area is reported. "
            "Areas below are pixel counts only."
        )
    if summary["proxy_crowns"]:
        warnings.append(
            f"{summary['proxy_crowns']} of {summary['tree_count']} crowns use a bounding-box "
            "PROXY area, not a true crown mask. Proxy areas overestimate canopy."
        )
    if summary["flagged_crowns"]:
        warnings.append(
            f"{summary['flagged_crowns']} crowns carry quality flags (e.g. clipped at the image "
            "edge); their areas are unreliable."
        )
    coverage = summary["canopy_coverage_pct"]
    if coverage is not None and coverage > 100:
        warnings.append(
            "Computed coverage exceeds 100%, which means crowns overlap or areas are "
            "overestimated. Treat the coverage figure as invalid."
        )
    if summary["tree_count"] == 0:
        warnings.append(
            "No trees were detected. The imagery may be too coarse for individual-crown "
            "detection, or the confidence threshold may be too high."
        )
    warnings.append(
        "Confidence values are model scores, not measurement accuracy. No accuracy figure is "
        "claimed for this run."
    )
    return warnings


#: Above this width the two cover estimates are too far apart for the midpoint to mean
#: anything, so the app must refuse to collapse them into a single figure.
WIDE_BRACKET_PCT = 25.0


def cover_warnings(bracket: dict) -> list[str]:
    """Plain-language caveats for the canopy-cover bracket."""
    warnings = []
    lower, upper = bracket["lower_bound_pct"], bracket["upper_bound_pct"]

    if bracket.get("inverted"):
        warnings.append(bracket.get("note", "Cover estimates are inconsistent."))
        return warnings

    if bracket["bracket_width_pct"] > WIDE_BRACKET_PCT:
        warnings.append(
            f"Canopy cover can only be bracketed between {lower:.1f}% (union of detected "
            f"crowns) and {upper:.1f}% (green vegetation of any kind) — a {bracket['bracket_width_pct']:.0f} "
            "point spread. No single cover figure is reported because the two independent "
            "estimates do not agree closely enough for one to be meaningful. The lower bound "
            "misses undetected crowns; the upper bound counts grass and shrubs as well as trees."
        )
    texture = bracket.get("vegetation_texture") or {}
    if texture.get("smooth"):
        warnings.append(
            f"The pixels classified as vegetation are unusually smooth (median local sigma "
            f"{texture['median_vegetation_std']:.1f}, below {texture['threshold']:.0f}). Canopy is "
            "strongly textured, so smooth green surfaces — open water especially, but also "
            "painted roofs or sports pitches — may be inflating the upper bound. Check the "
            "image before trusting it."
        )

    warnings.append(bracket["vegetation_caveat"])
    return warnings
