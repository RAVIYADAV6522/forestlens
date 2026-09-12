"""ForestLens - Streamlit front end."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import detection, io_utils, pipeline, segmentation  # noqa: E402
from src.io_utils import GSD_METADATA, GSD_UNKNOWN  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"
PROVENANCE = SAMPLE_DIR / "PROVENANCE.md"
UPLOAD_TYPES = ["tif", "tiff", "png", "jpg", "jpeg"]

st.set_page_config(page_title="ForestLens", page_icon="🌳", layout="wide")


def intro() -> None:
    st.title("🌳 ForestLens")
    st.caption(
        "Detect individual tree crowns in high-resolution forest imagery and estimate the "
        "canopy area they cover."
    )
    with st.container(border=True):
        st.markdown(
            "**What to upload** — a high-resolution RGB forest image. A georeferenced GeoTIFF is "
            "best: its metadata supplies the ground sampling distance (GSD). A PNG or JPEG works "
            "too, but you must tell the app how many metres one pixel covers.\n\n"
            "**What you get** — every detected crown drawn on your image, a tree count, canopy "
            "area, coverage, downloadable results, and an explicit list of what this run cannot "
            "tell you.\n\n"
            "**What this will not do** — invent a physical area when the image scale is unknown, "
            "or present a model confidence score as measurement accuracy."
        )


def backend_status() -> None:
    detector = detection.describe_backend()
    segmenter = segmentation.describe_backend()
    left, right = st.columns(2)
    left.metric("Tree detector", "ready" if detector["available"] else "not installed")
    right.metric("Crown segmentation", "ready" if segmenter["available"] else "not installed")
    if not detector["available"]:
        st.error(
            "No pretrained tree detector is installed, so this app cannot count trees. "
            "Install the requirements (`pip install -r requirements.txt`) and reload. "
            "It will not fabricate a count in the meantime."
        )
    elif not segmenter["available"]:
        st.warning(
            "Segmentation is unavailable, so crown areas will be reported as a clearly labelled "
            "bounding-box PROXY, which overestimates canopy area."
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
            st.info(
                "No sample scene is bundled yet. Add one to `data/sample/` and record its "
                "provider, date, GSD, CRS and licence in `data/sample/PROVENANCE.md`."
            )
        else:
            choice = st.selectbox(
                "Scene", samples, format_func=lambda p: _scene_label(p)
            )
            sidecar = choice.with_suffix(".provenance.json")
            if sidecar.exists():
                record = json.loads(sidecar.read_text())
                st.caption(
                    f"**{record.get('source_provider')}** · {record.get('platform')} · "
                    f"acquired {str(record.get('acquisition_datetime'))[:10]} · "
                    f"native GSD {record.get('native_sensor_gsd_m')} m/px on a "
                    f"{record.get('delivered_grid_spacing_m'):.3f} m grid · {record.get('crs')}"
                )
                st.caption(f"Licence: {record.get('licence')}")
                with st.expander("Full provenance record"):
                    st.json(record)
            elif PROVENANCE.exists():
                with st.expander("Imagery provenance"):
                    st.markdown(PROVENANCE.read_text())
            if st.button("Load sample scene"):
                return io_utils.load_image(choice)
    return None


def resolve_gsd(source) -> None:
    st.subheader("Image scale")
    if source.gsd_origin == GSD_METADATA:
        st.success(
            f"GSD read from raster metadata: **{source.gsd:.4f} m/pixel** "
            f"(CRS {source.crs}). Physical areas are computed from this value."
        )
        return

    st.warning(
        "This image carries no usable metric pixel size. Enter the ground sampling distance to "
        "get areas in square metres, or leave it blank to get pixel areas only."
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
        st.caption(
            f"Using a user-supplied GSD of {value} m/px. This assumption is recorded in the run "
            "metadata and in every export."
        )


def analysis_options() -> pipeline.Options:
    with st.sidebar:
        st.header("Analysis settings")
        options = pipeline.Options(
            min_score=st.slider("Minimum detection confidence", 0.05, 0.9, detection.DEFAULT_SCORE, 0.05),
            iou_threshold=st.slider("Duplicate suppression IoU", 0.1, 0.9, detection.DEFAULT_IOU, 0.05),
            patch_size=st.select_slider("Tile size (px)", [400, 600, 800, 1000, 1200], detection.DEFAULT_PATCH),
            patch_overlap=st.slider("Tile overlap", 0.0, 0.5, detection.DEFAULT_OVERLAP, 0.05),
            use_segmentation=st.checkbox(
                "Refine crowns with segmentation",
                value=segmentation.available(),
                disabled=not segmentation.available(),
            ),
        )
        st.caption(
            "Thresholds change the count. Whatever you pick is recorded in the run metadata so "
            "the number stays reproducible."
        )
    return options


def show_metrics(result) -> None:
    summary = result.summary
    columns = st.columns(4)
    columns[0].metric("Trees detected", f"{summary['tree_count']:,}")

    if summary["total_canopy_area_ha"] is not None:
        columns[1].metric("Canopy area", f"{summary['total_canopy_area_ha']:.3f} ha")
        columns[2].metric(
            "Coverage",
            f"{summary['canopy_coverage_pct']:.1f}%" if summary["canopy_coverage_pct"] else "n/a",
        )
    else:
        columns[1].metric("Canopy area", f"{summary['total_canopy_pixels']:,.0f} px")
        columns[2].metric("Coverage", "needs GSD")
    columns[3].metric(
        "Mean confidence",
        f"{summary['mean_confidence']:.2f}" if summary["mean_confidence"] else "n/a",
    )

    scale = summary.get("detection_scale", 1.0)
    if scale and scale != 1.0:
        st.info(
            f"Detection ran on imagery resampled **{scale:.2f}×** to "
            f"**{summary['detection_gsd_m_per_px']:.3f} m/px**, the resolution this detector was "
            f"trained on. Source imagery is {summary['gsd_m_per_px']:.3f} m/px. Resampling adds "
            "no detail — it presents crowns at the pixel size the model expects. Areas are "
            "computed in the source raster's grid."
        )

    basis = "segmentation masks" if summary["proxy_crowns"] == 0 else (
        "bounding-box PROXY" if summary["mask_backed_crowns"] == 0 else "mixed masks and PROXY boxes"
    )
    st.info(
        f"Area basis: **{basis}** "
        f"({summary['mask_backed_crowns']} mask-backed, {summary['proxy_crowns']} proxy). "
        + (
            f"Computed as pixel count x GSD² with GSD = {summary['gsd_m_per_px']:.4f} m/px "
            f"({result.source.gsd_origin})."
            if summary["gsd_m_per_px"]
            else "No GSD available, so pixel areas are reported as-is."
        )
    )


def show_downloads(result) -> None:
    st.subheader("Downloads")
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

    st.subheader("Quality and limitations")
    for warning in result.warnings:
        st.warning(warning)

    st.subheader("Detected crowns")
    before, after = st.columns(2)
    before.caption("Source image")
    before.image(result.source.array, width="stretch")
    after.caption("Detected crowns — orange outlines carry quality flags")
    after.image(io_utils.annotate(result.source, result.crowns), width="stretch")

    st.subheader("Per-crown measurements")
    rows = result.rows()
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No crowns to tabulate.")

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

    st.divider()
    st.image(source.array, caption=f"{source.name} — {source.width} x {source.height} px", width=520)
    resolve_gsd(source)

    if st.button("Run analysis", type="primary", disabled=not detection.available()):
        with st.spinner("Detecting crowns…"):
            try:
                st.session_state["result"] = pipeline.analyse(source, options)
            except detection.DetectorUnavailable as exc:
                st.error(str(exc))
                return

    result = st.session_state.get("result")
    if result is not None:
        st.divider()
        show_results(result)


main()
