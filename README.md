---
title: ForestLens
emoji: 🌳
colorFrom: green
colorTo: gray
sdk: streamlit
sdk_version: 1.63.0
app_file: app/app.py
pinned: false
license: mit
short_description: Tree-crown detection and canopy-area estimation from forest imagery
---

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
  screen labels it a **PROXY** (measured to overestimate crown area by 12–22%).
- No tree detector installed → the app refuses to produce a count instead of inventing one.
- Model confidence is reported as a model score, never as measurement accuracy.
- Canopy cover is reported as a **bracket**, and when the two independent estimates are more
  than 25 points apart the app declines to give a single figure at all.
- A coverage figure above 100% is reported as invalid rather than quietly clipped.

## What we found (and what it means)

Three findings shaped the build. Full evidence in [`docs/VALIDATION.md`](docs/VALIDATION.md).

1. **Pretrained DeepForest fails on native satellite imagery.** At 0.305 m/px it reported 5.8
   trees/ha with 15 m "crowns" where real crowns are 4–8 m. The model was trained on ~0.10 m/px
   imagery, so the pipeline resamples the detection input to that resolution — which takes the
   same crop to 71.2 trees/ha with 5.2 m crowns. Resampling adds no information; it only presents
   crowns at the pixel size the model expects.
2. **Canopy closure, not resolution, is the binding constraint.** A 10 cm scene at *exactly* the
   model's training resolution was the worst performer of the three: ~1 crown in 5 detected, and
   21% cover reported on a canopy visibly ~100% closed.
3. **Summed crown boxes are not canopy cover.** Detection fires on separable crown apexes and
   cannot tile interlocking canopy, so cover is bracketed between the crown union and green
   vegetation cover. On all three scenes those bounds are 73–81 points apart, which is the honest
   answer: this pipeline counts relatively separable trees and **cannot measure canopy cover to a
   useful precision**.

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
src/pipeline.py     orchestration, GSD precedence, resampling, run metadata, exports
src/detection.py    pretrained tree detector, tiled inference, NMS, edge flags
src/segmentation.py box-prompted crown masks (SAM 2), device selection, mask acceptance
src/metrics.py      crown areas, canopy totals, quality and cover warnings
src/cover.py        canopy-cover bracketing: crown union vs green vegetation
src/io_utils.py     raster loading, resampling, tiling, annotation, CSV/GeoJSON writers
scripts/            reproducible imagery fetchers (Maxar ARD, SWISSIMAGE)
data/sample/        three scenes + provenance records
docs/               spec, plan, validation findings, two-page submission
outputs/            exported runs
tests/              54 tests; measurement logic runs without model weights
```

## Imagery

Source your own scene and record its provider, dataset, location, acquisition date, GSD, CRS,
licence terms and any processing in `data/sample/PROVENANCE.md` **before** analysing it. Verify
the licence for the exact asset, not just the dataset front page. A consumer map screenshot is
not measurement data and is not acceptable for the submission.

## Known limitations

| Limitation | Measured | What the app does about it |
| --- | --- | --- |
| **Closed canopy** | ~1 crown in 5 detected | Counts are severe lower bounds; warned in the panel |
| **Canopy cover** | bounds 73–81 pts apart | Reported as a bracket; single figure refused |
| Open-canopy over-count | +19% to +28% vs reference | Stated in `docs/VALIDATION.md`; no accuracy claimed |
| Coarse imagery | fails at native 0.305 m | Resampled to training GSD; both facts surfaced |
| Bounding-box area | overestimates by 12–22% | Masks used where available, else labelled PROXY |
| Green water | lake read as 94.3% vegetation | Smooth-vegetation warning; no silent "fix" applied |
| Unknown GSD | — | Physical area withheld; pixel areas only |
| Crowns cut by image edge | 30 of 695 on one scene | Flagged per crown; areas truncated |
| Tiled inference duplicates | 993 raw → 695 kept | IoU suppression; threshold in run metadata |
| Cross-region generalisation | not evaluated | Stated, not claimed |

No accuracy number is published for this tool, because no labelled evaluation set has been run
against it. Nor is any carbon or biomass figure: canopy area is geometry, and converting it to
carbon needs allometry, species and field calibration this project does not have.

## Documents

- [`docs/SUBMISSION.md`](docs/SUBMISSION.md) — the two-page technical explanation.
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — findings, reference counts, negative controls.
- [`docs/SPEC.md`](docs/SPEC.md) — requirements and the submission gate.
- [`docs/PLAN.md`](docs/PLAN.md) — three-phase execution plan.
- [`data/sample/PROVENANCE.md`](data/sample/PROVENANCE.md) — imagery sources and licences.

## Status

Working end to end on three real scenes, 54 tests green. Detection, resampling, crown masks,
cover bracketing, exports and run metadata are all done, and the two-page submission is written.

**Outstanding:** the live demo is not deployed yet (needs a Hugging Face token), and the
reference counts in `docs/VALIDATION.md` were made by eye by an AI assistant rather than a human
expert — that substitution is stated wherever those numbers appear, and replacing them is the
most valuable next step.
