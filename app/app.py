"""ForestLens - Streamlit front end."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import theme  # noqa: E402
from src import detection, io_utils, pipeline, segmentation  # noqa: E402
from src.io_utils import GSD_METADATA  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"
PROVENANCE = SAMPLE_DIR / "PROVENANCE.md"
UPLOAD_TYPES = ["tif", "tiff", "png", "jpg", "jpeg"]
REPO = "https://github.com/RAVIYADAV6522/forestlens"

st.set_page_config(
    page_title="ForestLens — tree-crown detection",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.inject()


def intro() -> None:
    theme.navbar(
        "ForestLens",
        tags=[
            ("How it works", f"{REPO}/blob/main/docs/SUBMISSION.md"),
            ("Validation", f"{REPO}/blob/main/docs/VALIDATION.md"),
            ("GitHub", REPO),
        ],
    )
    theme.lede(
        "Detect individual tree crowns in high-resolution forest imagery and estimate the "
        "canopy area they cover — with the assumptions and the failure cases kept on screen."
    )
    theme.cards([
        (
            "What to upload",
            "A high-resolution RGB forest image. A georeferenced <strong>GeoTIFF</strong> is best "
            "— its metadata supplies the ground sampling distance. PNG and JPEG work too, but "
            "you will need to say how many metres one pixel covers.",
        ),
        (
            "What you get",
            "Every detected crown drawn over your image, a <strong>tree count</strong>, per-crown "
            "areas, a <strong>canopy-cover range</strong>, downloadable results — and an explicit "
            "list of what the run cannot tell you.",
        ),
        (
            "What it will not do",
            "Invent a physical area when the image scale is unknown, present model confidence as "
            "measurement accuracy, or report a single canopy-cover figure when the evidence only "
            "supports a range.",
        ),
    ])


def backend_status() -> None:
    """Status as compact badges. A missing detector is an error; missing masks are not."""
    detector = detection.describe_backend()
    segmenter = segmentation.describe_backend()

    badges = [
        ("Detector ready" if detector["available"] else "Detector missing",
         "ok" if detector["available"] else "warn"),
        ("Crown masks on" if segmenter["available"] else "Crown masks off — box proxy",
         "ok" if segmenter["available"] else "off"),
    ]
    if detector["version"]:
        badges.append((f"DeepForest {detector['version']}", "neutral"))
    theme.pills(badges)

    if not detector["available"]:
        theme.note(
            "No pretrained tree detector is installed, so this app cannot count trees. Install "
            "the requirements and reload. It will not fabricate a count in the meantime.",
            "danger",
        )
    elif not segmenter["available"]:
        theme.note(
            "Crown-mask refinement is unavailable, so crown areas come from bounding boxes and "
            "are labelled a proxy throughout. Measured against masks, boxes overestimate crown "
            "area by 12–22%.",
            "warn",
        )


def _scene_label(path: Path) -> str:
    sidecar = path.with_suffix(".provenance.json")
    if sidecar.exists():
        label = json.loads(sidecar.read_text()).get("label")
        if label:
            return f"{path.name} — {label}"
    return path.name


def pick_source():
    """Return an ImageSource from an upload or the bundled sample, or None."""
    samples = sorted(
        p for p in SAMPLE_DIR.glob("*") if p.suffix.lower().lstrip(".") in UPLOAD_TYPES
    )
    tab_upload, tab_sample = st.tabs(["Upload imagery", f"Sample scene ({len(samples)})"])

    with tab_upload:
        upload = st.file_uploader("Forest image", type=UPLOAD_TYPES)
        if upload is not None:
            suffix = Path(upload.name).suffix or ".png"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(upload.getbuffer())
                temp_path = Path(handle.name)
            source = io_utils.load_image(temp_path)
            source.name = upload.name
            return source

    with tab_sample:
        if not samples:
            theme.note(
                "No sample scene is bundled yet. Add one to data/sample/ and record its "
                "provider, date, GSD, CRS and licence in data/sample/PROVENANCE.md.",
                "info",
            )
        else:
            choice = st.selectbox(
                "Scene", samples, format_func=lambda p: _scene_label(p)
            )
            sidecar = choice.with_suffix(".provenance.json")
            if sidecar.exists():
                record = json.loads(sidecar.read_text())
                theme.pills([
                    (str(record.get("source_provider")), "neutral"),
                    (str(record.get("platform")), "neutral"),
                    (f"acquired {str(record.get('acquisition_datetime'))[:10]}", "neutral"),
                    (f"native GSD {record.get('native_sensor_gsd_m')} m/px", "ok"),
                    (f"grid {record.get('delivered_grid_spacing_m'):.3f} m", "neutral"),
                    (str(record.get("crs")), "neutral"),
                ])
                theme.note(f"Licence — {record.get('licence')}")
                with st.expander("Full provenance record"):
                    st.json(record)
            elif PROVENANCE.exists():
                with st.expander("Imagery provenance"):
                    st.markdown(PROVENANCE.read_text())
            if st.button("Load sample scene"):
                return io_utils.load_image(choice)
    return None


def resolve_gsd(source) -> None:
    theme.section("Image scale", kicker="Ground sampling distance")
    if source.gsd_origin == GSD_METADATA:
        theme.note(
            f"GSD read from raster metadata: {source.gsd:.4f} m/pixel (CRS {source.crs}). "
            "Physical areas are computed from this value, not from an assumption.",
            "info",
        )
        return

    theme.note(
        "This image carries no usable metric pixel size. Enter the ground sampling distance to "
        "get areas in square metres, or leave it at zero to get pixel areas only.",
        "warn",
    )
    value = st.number_input(
        "Ground sampling distance (metres per pixel)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=0.01,
        format="%.4f",
        help="0.5 means one pixel covers 0.5 m on the ground. Leave at 0 if you do not know it.",
    )
    if value > 0:
        pipeline.apply_gsd(source, value)
        theme.note(
            f"Using a user-supplied GSD of {value} m/px. The app records that this value came "
            "from you — in the run metadata and in every export."
        )


def analysis_options() -> pipeline.Options:
    with st.sidebar:
        st.markdown(
            '<div class="fl-section-kicker">Controls</div>'
            '<div class="fl-section-title" style="margin-bottom:.9rem">Analysis settings</div>',
            unsafe_allow_html=True,
        )
        theme.note(
            "Defaults are the validated settings. Every value you pick is written into the run "
            "metadata, so any count here can be reproduced exactly — including a bad one."
        )
        options = pipeline.Options(
            min_score=st.slider(
                "Minimum detection confidence", 0.05, 0.9, detection.DEFAULT_SCORE, 0.05,
                help="Detections scoring below this are dropped. Raise it for fewer, "
                     "safer trees; lower it and shrubs and shadows start counting.",
            ),
            iou_threshold=st.slider(
                "Duplicate suppression IoU", 0.1, 0.9, detection.DEFAULT_IOU, 0.05,
                help="Tiled inference finds the same tree more than once. Boxes overlapping "
                     "by more than this are merged. On the open-canopy sample this takes 993 "
                     "raw predictions down to 695.",
            ),
            patch_size=st.select_slider(
                "Tile size (px)", [400, 600, 800, 1000, 1200], detection.DEFAULT_PATCH,
                help="The window the detector slides over the image, and the most "
                     "consequential setting here. On the open-canopy sample: 800 px gives 695 "
                     "trees and 1.48 ha of crown; 400 px gives 1379 trees and 0.67 ha. 800 is "
                     "the value the validation in docs/VALIDATION.md was done at.",
            ),
            patch_overlap=st.slider(
                "Tile overlap", 0.0, 0.5, detection.DEFAULT_OVERLAP, 0.05,
                help="How much neighbouring tiles overlap, so a tree on a seam is not cut in "
                     "half. More overlap misses fewer edge trees but creates more duplicates "
                     "to suppress, and runs slower.",
            ),
            use_segmentation=st.checkbox(
                "Refine crowns with segmentation",
                value=segmentation.available(),
                disabled=not segmentation.available(),
                help="Replaces bounding-box areas with SAM 2 crown masks, which measure "
                     "12–22% smaller. Unavailable in this build, which ships detector-only.",
            ),
        )

        changed = [
            name
            for name, value, default in (
                ("confidence", options.min_score, detection.DEFAULT_SCORE),
                ("IoU", options.iou_threshold, detection.DEFAULT_IOU),
                ("tile size", options.patch_size, detection.DEFAULT_PATCH),
                ("tile overlap", options.patch_overlap, detection.DEFAULT_OVERLAP),
            )
            if value != default
        ]
        if changed:
            theme.note(
                "Changed from the validated defaults: "
                + ", ".join(changed)
                + ". The count below is no longer the one the validation figures refer to.",
                "warn",
            )
    return options


def show_metrics(result) -> None:
    summary = result.summary
    bracket = summary.get("cover_bracket") or {}

    if summary["total_canopy_area_ha"] is not None:
        crown_area = f"{summary['total_canopy_area_ha']:.3f} ha"
        crown_note = "Sum of accepted crowns; overlaps counted twice"
    else:
        crown_area = f"{summary['total_canopy_pixels']:,.0f} px"
        crown_note = "Pixel area only — no GSD supplied"

    if bracket and not bracket.get("inverted"):
        cover = f"{bracket['lower_bound_pct']:.0f}–{bracket['upper_bound_pct']:.0f}%"
        cover_note = f"A range, {bracket['bracket_width_pct']:.0f} points wide"
    else:
        cover = "unreliable"
        cover_note = "Estimates are inconsistent for this image"

    confidence = (
        f"{summary['mean_confidence']:.2f}" if summary["mean_confidence"] else "n/a"
    )
    ha = (summary["analysed_ground_area_m2"] or 0) / 10_000

    theme.stats(
        [
            ("Trees detected", f"{summary['tree_count']:,}",
             f"{summary['tree_count'] / ha:.1f} per hectare over {ha:.2f} ha" if ha else "Count after filtering"),
            ("Crown area", crown_area, crown_note),
            ("Canopy cover", cover, cover_note),
            ("Mean confidence", confidence, "Model score, not accuracy"),
        ],
        muted={3},
    )

    scale = summary.get("detection_scale", 1.0)
    if scale and scale != 1.0:
        theme.note(
            f"Detection ran on imagery resampled {scale:.2f}× to "
            f"{summary['detection_gsd_m_per_px']:.3f} m/px — the resolution this detector was "
            f"trained on. Source imagery is {summary['gsd_m_per_px']:.3f} m/px. Resampling adds "
            "no detail; it presents crowns at the pixel size the model expects. Areas are "
            "computed in the source raster's grid.",
            "info",
        )

    basis = "segmentation masks" if summary["proxy_crowns"] == 0 else (
        "bounding-box proxy" if summary["mask_backed_crowns"] == 0 else "mixed masks and proxy boxes"
    )
    detail = (
        f"Computed as pixel count × GSD² with GSD = {summary['gsd_m_per_px']:.4f} m/px "
        f"({result.source.gsd_origin})."
        if summary["gsd_m_per_px"]
        else "No GSD available, so pixel areas are reported as-is."
    )
    theme.note(
        f"Area basis: {basis} ({summary['mask_backed_crowns']} mask-backed, "
        f"{summary['proxy_crowns']} proxy). {detail}"
    )


def show_cover(result) -> None:
    """Canopy cover, reported as a bracket because one number would be wrong."""
    bracket = result.summary.get("cover_bracket")
    if not bracket:
        return

    theme.section(
        "Canopy cover",
        kicker="Bracketed, not asserted",
        note="Two independent estimates. The app does not average them into one figure.",
    )
    if bracket.get("inverted"):
        theme.note(bracket.get("note", "Cover estimates are inconsistent."), "danger")
        return

    lower, upper = bracket["lower_bound_pct"], bracket["upper_bound_pct"]
    theme.bracket(
        lower,
        upper,
        lower_note=(
            "Union of detected crown footprints — a union, so overlaps count once. Too low: "
            "every crown the detector missed contributes nothing. In closed canopy, far too low."
        ),
        upper_note=(
            f"Pixels where green dominates (2G − R − B > {bracket['vegetation_threshold']:g}). "
            "Too high: grass, shrubs and crops are green too. Deeply shadowed canopy can drop "
            "below the threshold and be missed."
        ),
        summary=(
            f"Two independent estimates, {bracket['bracket_width_pct']:.0f} points apart. True "
            "tree-canopy cover lies near or between them — the midpoint would not mean anything, "
            "so none is given."
        ),
    )
    with st.expander("Threshold sensitivity of the upper bound"):
        st.caption(
            "The vegetation threshold is a choice, and it moves the number. Shown so you can "
            "see how much."
        )
        st.table(
            {
                "rule": list(bracket["vegetation_sensitivity"].keys()),
                "vegetation cover": [
                    f"{v:.1%}" for v in bracket["vegetation_sensitivity"].values()
                ],
            }
        )
        st.caption(
            "Otsu's method was rejected for this threshold: on a near-uniformly vegetated "
            f"image it splits within the vegetation distribution (it suggests "
            f"{bracket['otsu_threshold_diagnostic']:.0f} here) and under-reports cover badly."
        )


def show_downloads(result) -> None:
    theme.section("Downloads", kicker="Take the results with you")
    annotated = io_utils.annotate(result.source, result.crowns)
    buffer = io.BytesIO()
    annotated.save(buffer, format="PNG")

    csv_header = ",".join(io_utils.CSV_COLUMNS)
    csv_body = "\n".join(
        ",".join(str(row[column]) for column in io_utils.CSV_COLUMNS) for row in result.rows()
    )
    geojson = io_utils.crowns_to_geojson(result.source, result.crowns)
    stem = Path(result.source.name).stem or "forestlens"

    columns = st.columns(4)
    columns[0].download_button("Annotated PNG", buffer.getvalue(), f"{stem}_annotated.png", "image/png")
    columns[1].download_button("Crowns CSV", f"{csv_header}\n{csv_body}", f"{stem}_crowns.csv", "text/csv")
    if geojson:
        columns[2].download_button(
            "Crowns GeoJSON", json.dumps(geojson, indent=2), f"{stem}_crowns.geojson", "application/geo+json"
        )
    else:
        columns[2].button("Crowns GeoJSON", disabled=True, help="Needs a georeferenced image (CRS + transform).")
    columns[3].download_button(
        "Run metadata JSON",
        json.dumps(result.metadata(), indent=2, default=str),
        f"{stem}_run.json",
        "application/json",
    )


def show_results(result) -> None:
    show_metrics(result)

    show_cover(result)

    theme.section(
        "Quality and limitations",
        kicker="Read this before the numbers",
        note=f"{len(result.warnings)} caveats apply to this run.",
    )
    for warning in result.warnings:
        theme.note(warning, "warn")

    theme.section(
        "Detected crowns",
        kicker="The evidence",
        note="Source and result side by side — the input is never hidden behind a number.",
    )
    before, after = st.columns(2, gap="medium")
    before.markdown('<div class="fl-card-label">Source imagery</div>', unsafe_allow_html=True)
    before.image(result.source.array, width="stretch")
    after.markdown(
        '<div class="fl-card-label">Detected crowns · orange = quality flagged</div>',
        unsafe_allow_html=True,
    )
    after.image(io_utils.annotate(result.source, result.crowns), width="stretch")

    theme.section("Per-crown measurements", kicker="Every detection, inspectable")
    rows = result.rows()
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        theme.note("No crowns to tabulate.")

    show_downloads(result)

    with st.expander("Run metadata (models, thresholds, timings)"):
        st.json(result.metadata()["run"])


def main() -> None:
    intro()
    backend_status()
    options = analysis_options()

    source = pick_source()
    if source is not None:
        st.session_state["source"] = source
    source = st.session_state.get("source")
    if source is None:
        return

    theme.section(
        source.name,
        kicker="Loaded scene",
        note=f"{source.width} × {source.height} px"
        + (f" · {source.crs}" if source.crs else "")
        + (
            f" · {(source.ground_area_m2() or 0) / 10_000:.2f} ha on the ground"
            if source.gsd
            else ""
        ),
    )
    preview, scale_col = st.columns([1, 1], gap="large")
    with preview:
        st.image(source.array, width="stretch")
    with scale_col:
        resolve_gsd(source)
        run = st.button(
            "Run analysis", type="primary", disabled=not detection.available(),
            width="stretch",
        )

    if run:
        with st.spinner("Detecting crowns — the first run downloads model weights…"):
            try:
                st.session_state["result"] = pipeline.analyse(source, options)
            except detection.DetectorUnavailable as exc:
                theme.note(str(exc), "danger")
                return

    result = st.session_state.get("result")
    if result is not None:
        st.divider()
        show_results(result)


main()
