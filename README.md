# ForestLens

Detect individual tree crowns in high-resolution forest imagery and estimate the canopy area
they cover — with the evidence, the assumptions and the failure cases kept visible.

Built for the Flora Carbon AI hiring hackathon: count tree crowns in high-resolution satellite
imagery, estimate canopy area, source your own imagery.

## The rule this project is built around

**If the system cannot justify a number, it does not present that number.**

Concretely:

- No ground sampling distance (GSD) → no physical area. The app reports pixel areas and says so.
- No segmentation masks → crown area comes from bounding boxes, and every metric, export and
  screen labels it a **PROXY** (which overestimates canopy).
- No tree detector installed → the app refuses to produce a count instead of inventing one.
- Model confidence is reported as a model score, never as measurement accuracy.
- A coverage figure above 100% is reported as invalid rather than quietly clipped.

## How it works

```
high-res image
  → preprocess (RGB, 2–98% stretch for non-8-bit rasters)
  → tiled detection (DeepForest, pretrained)
  → boxes + confidence → duplicate suppression (IoU NMS) + edge flags
  → box-prompted segmentation (SAM 2) → crown masks
  → pixel area × GSD²
  → tree count + total canopy area + coverage
  → annotated PNG + CSV + optional GeoJSON + run metadata
```

Tree counting and area measurement are deliberately separate stages: the count comes from the
detector, the area comes from whatever crown geometry we can actually defend.

### Area maths

With GSD `g` metres/pixel, a crown mask of `N` pixels covers `N × g²` square metres.
Total canopy area is the sum of accepted crown areas. Coverage is total canopy area divided by
the analysed ground area (image pixels × `g²`) × 100.

## Setup

```bash
uv venv --python 3.12          # or: python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/app.py
```

The app runs before the models are installed — it will tell you the detector is missing rather
than fake a result. `rasterio` is optional but needed to read GeoTIFF metadata (and therefore to
get a GSD automatically) and to export GeoJSON.

### Tests

```bash
python -m pytest tests -q
```

The suite covers the area maths, GSD precedence, duplicate suppression, edge flagging, tiling
coverage and export shapes. It needs only `numpy`, `pillow` and `pytest` — no model weights —
so the measurement logic stays verifiable without a GPU.

## Using it

1. Upload a high-resolution RGB forest image (GeoTIFF preferred) or load the bundled sample.
2. Confirm the GSD. A georeferenced raster supplies it; otherwise you enter it, and the app
   records that it came from you.
3. Run the analysis.
4. Inspect the detected crowns over the source image — orange outlines carry quality flags.
5. Read the metrics *and* the quality/limitations panel.
6. Download the annotated PNG, per-crown CSV, GeoJSON (when georeferenced) and run metadata.

## Layout

```
app/app.py          Streamlit UI
src/pipeline.py     orchestration, GSD precedence, run metadata, exports
src/detection.py    pretrained tree detector, NMS, edge flags
src/segmentation.py box-prompted crown masks (optional stage)
src/metrics.py      crown areas, canopy totals, quality warnings
src/io_utils.py     image/raster loading, tiling, annotation, CSV/GeoJSON writers
data/sample/        demo scene + PROVENANCE.md (fill this in before any demo)
outputs/            exported runs
tests/              measurement-logic tests, no model weights required
```

## Imagery

Source your own scene and record its provider, dataset, location, acquisition date, GSD, CRS,
licence terms and any processing in `data/sample/PROVENANCE.md` **before** analysing it. Verify
the licence for the exact asset, not just the dataset front page. A consumer map screenshot is
not measurement data and is not acceptable for the submission.

## Known limitations

| Limitation | What the app does about it |
| --- | --- |
| Dense overlapping canopy | Crowns merge; count is an undercount. Flagged in the warnings panel. |
| Low-resolution imagery | Individual crowns are not separable; a zero/near-zero count is surfaced as a likely resolution problem. |
| Unknown GSD | Physical area is withheld; pixel areas only. |
| Bounding-box proxy area | Labelled PROXY in the UI, CSV, GeoJSON and run metadata. |
| Crowns cut by the image edge | Flagged per crown; their areas are truncated. |
| Tiled inference | IoU-based duplicate suppression, threshold recorded in run metadata. |
| Mixed vegetation, shadow, haze | A pretrained detector can fire on shrubs and miss shaded crowns; no accuracy figure is claimed. |
| Cross-region generalisation | Not evaluated. The pretrained model may behave differently on other forest types. |

No accuracy number is published for this tool, because no labelled evaluation set has been run
against it.

## Planning documents

- [`docs/SPEC.md`](docs/SPEC.md) — what "done" means: the honesty contract, functional
  requirements, imagery and validation requirements, and the A1–A12 submission gate.
- [`docs/PLAN.md`](docs/PLAN.md) — the three-phase execution plan, timeboxes, go/no-go rules
  and the cut list.

## Status

Phase 0 (scaffold) complete: pipeline, UI and exports are built and the measurement logic is
tested without model weights. Phase 1 next — install the detector, source and licence-check a
real satellite scene, and get a live public URL up.
