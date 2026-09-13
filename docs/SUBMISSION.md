# ForestLens — Tree-Crown Detection and Canopy-Area Estimation

**Live demo:** <https://forestlens-cujmcn43y5s8ev8vguauez.streamlit.app> · **Repository:** https://github.com/RAVIYADAV6522/forestlens

---

# Page 1 — Problem and System

## Objective

Given high-resolution satellite imagery of a forest: count the individual tree crowns, and
estimate the canopy area they cover. Built solo over one weekend, imagery self-sourced.

## Imagery and provenance

Three scenes, two sources, both with licences verified for the exact assets used.

| Scene | Source | Native GSD | Grid | Canopy | Area |
| --- | --- | --- | --- | --- | --- |
| `bc_open_canopy` | Maxar/Vantor Open Data, WorldView-2, 2022-07-14 | 0.49 m | 0.305 m | open pine/fir over grass | 9.77 ha |
| `bc_dense_canopy` | Maxar/Vantor Open Data, WorldView-2, 2022-05-18 | 0.49 m | 0.305 m | near-closed conifer | 9.77 ha |
| `ch_closed_canopy` | swisstopo SWISSIMAGE 10 cm, 2022 | 0.10 m | 0.10 m | closed mixed beech/conifer | 4.19 ha |

The BC scenes are pre-fire crops near West Kelowna (CC BY-NC 4.0 — attribution, **non-commercial
only**, which means commercial deployment of this tool would need separately licensed imagery).
The Swiss scene is swisstopo open government data, where commercial use *is* permitted with
source citation. Full records including CRS, off-nadir, sun elevation, cloud and processing steps
are in `data/sample/PROVENANCE.md` and per-scene JSON sidecars, written automatically at fetch
time by `scripts/fetch_maxar_crop.py` and `scripts/fetch_swissimage_crop.py`. Both read only the
requested window from the public COG, so crops are ~1–10 MB and exactly reproducible.

**Native GSD vs grid spacing** are tracked separately. The Maxar ARD product is delivered on a
0.305 m grid but the sensor resolved 0.49 m. Areas computed from the grid are geometrically
correct for the delivered raster; detectable detail is limited by the native GSD. No amount of
grid refinement recovers sub-0.49 m structure.

## Pipeline

```
image → read GSD/CRS from raster → resample to detector's training GSD
      → tiled detection (DeepForest) → boxes + confidence
      → IoU duplicate suppression → edge flags → map boxes back to source pixels
      → per-crown pixel area × GSD²
      → tree count · crown-area sum · canopy-cover bracket
      → annotated PNG · CSV · GeoJSON · run metadata
```

## Models, and why

**DeepForest** (`weecology/deepforest-tree`) for individual-tree detection: a pretrained
model purpose-built for the task, which under a weekend constraint beats training from scratch.
**SAM 2** (`facebook/sam2-hiera-small`, box-prompted) refines each detection into a crown mask,
because a bounding box overestimates crown area by 12–22% (measured, Page 2). Where SAM 2 is
unavailable the app falls back to box areas and labels every one of them a proxy.

The critical property of the pretrained model is its **training resolution: ~0.10 m/px NEON
airborne RGB.** Run directly on 0.305 m satellite imagery it produces 5.8 trees/ha with 15 m
"crowns" where real crowns are 4–8 m — it fails outright. The pipeline therefore upsamples the
detection input to the model's training GSD (3.05× here), then maps boxes back into source-raster
pixels so area, annotation and GeoJSON all stay in one coordinate frame. On the same crop that
takes the count from 57 to 695 and mean crown size to 5.2 m.

**Resampling adds no information.** It presents crowns at the pixel size the model expects,
nothing more. The 57 → 695 jump is evidence that the input scale was wrong, not evidence that
695 is right. The scale factor is anchored to the model's documented training GSD rather than
chosen empirically, because the count rises monotonically with scale and never plateaus — so
"pick the best-looking count" would be tuning to a preferred answer.

## How tree count is computed

Tiled inference (800 px tiles, 0.15 overlap) on the resampled image; detections below the
confidence threshold (default 0.25) dropped; greedy IoU non-maximum suppression at 0.4 to remove
duplicates across tile overlaps; detections touching the image border flagged as clipped. On
`bc_open_canopy` the chain is 1544 raw window predictions → 993 after DeepForest's own mosaic
NMS (at its un-passed 0.15 default) → 695 after confidence ≥ 0.25 → 695 after our IoU
suppression, which removes **nothing**: DeepForest already bounds every output pair below 0.15,
so our 0.40 control cannot act. An earlier version of this report credited the 993 → 695 step to
that control; it is entirely the confidence filter. Every threshold is recorded in the run
metadata, so a count is reproducible from its own export.

## How canopy area is computed

With GSD `g` m/px, a crown of `N` pixels covers `N × g²` m². Per-crown areas sum to a total
crown area. If `g` is unknown the app reports pixel areas and **withholds physical area entirely**
rather than assuming a value.

Canopy *cover* is reported as a **bracket, not a number**:

- **Lower bound** — the *union* of crown footprints (a union, so overlapping boxes are not
  double counted). Too low by every crown the detector missed.
- **Upper bound** — green vegetation cover, `2G − R − B > 0`. Too high: grass, shrubs and crops
  are green too.

On all three scenes these bounds sit 73–81 points apart. When they differ by more than 25 points
the app states the range and explicitly declines to report a single cover figure, because the
midpoint would not mean anything. That is the honest answer: **this pipeline counts relatively
separable trees well and cannot measure canopy cover to a useful precision.**

---

# Page 2 — Validation, Limitations, Reproducibility

## Validation setup

No labelled ground truth exists for these scenes, so validation is observational. Reference
counts were made **by eye, before any detections were displayed** (to avoid anchoring), using a
stated rule: one count per distinguishable crown unit bounded by shadow lines or texture
discontinuity, clumps counted by apparent apex, crops quartered and counted cell by cell.

**These counts were made by the AI assistant that built the tool, not by a human expert or field
survey.** They are independent of the detector but they are not ground truth. A human expert
count is the most valuable thing that could be added next.

| Crop | Scene | Area | Reference | Detected | Difference |
| --- | --- | --- | --- | --- | --- |
| openA | `bc_open_canopy`, resampled 3.05× | 0.610 ha | 48 ± 10 | 57 | **+19%** |
| openB | `bc_open_canopy`, resampled 3.05× | 0.610 ha | 36 ± 8 | 46 | **+28%** |
| chA | `ch_closed_canopy`, native 0.10 m | 0.262 ha | 48 ± 14 | 9 | **−81%** |

## The main finding: closure, not resolution

The 10 cm Swiss scene is at *exactly* the detector's training resolution and is the **worst**
performing of the three: it recovers roughly one crown in five, and reports 21.3% cover on a
canopy visibly ~95–100% closed. Detections cluster on sunlit broadleaf crowns and ignore darker
conifer areas.

Because resolution is optimal there, the binding constraint is **canopy closure** — and
secondarily **structural domain**, since DeepForest's NEON training data is largely open North
American conifer and savanna, structurally unlike closed European mixed forest. Finer imagery is
not sufficient and here was not even helpful. Per-hectare counts also saturate: 71.2 vs 72.2 on
two BC scenes of visibly very different density.

## Negative controls

| Control | Trees | Trees/ha | Crown union | Green vegetation |
| --- | --- | --- | --- | --- |
| Open water | 2 | 0.2 | 0.0% | **94.3%** |
| Built-up (downtown Kelowna) | 125 | 12.8 | 3.1% | 31.0% |

Water passes the count test (effectively clean) and **breaks the vegetation index**, which
reported 94.3% vegetation on a lake because turbid water is genuinely green-dominant in RGB.
Texture was tested as a fix and rejected: water sits at median local σ 4.8 and closed canopy at
20.0, but the open Okanagan stand is 6.3 — any threshold removing the lake would delete a real
forest scene. Rather than ship a heuristic that works on one image, the app **flags** the
condition. The urban control tests specificity rather than zero-detection (cities have real
street trees); detections land overwhelmingly on actual trees, with building roofs almost
entirely clean and a handful of genuine rooftop false positives.

## Assumptions and limitations

- Crown-summed area is **not** canopy cover in closed canopy. Cover is bracketed, never asserted.
- Counts in closed canopy are severe **lower bounds** (~20% recall observed).
- Counts in open canopy run **20–30% high**, likely clump splitting and shadow detections.
- Confidence values are model scores, **not** accuracy. No accuracy figure is published anywhere.
- Crowns clipped by the image edge have truncated areas and are flagged per crown.
- Crown areas come from segmentation masks where available, labelled `segmentation_mask`;
  otherwise from bounding boxes, labelled `bounding_box_proxy` in the UI, CSV, GeoJSON and
  metadata. Masks on 0.305 m imagery are better than boxes but are not precise crown outlines.
- Generalisation beyond these three scenes is untested.
- **No carbon or biomass estimate is offered.** Canopy area is geometry; converting it to carbon
  requires allometry, species and field calibration this project does not have.

## Reproducibility and deployment

Python 3.12, Streamlit UI, DeepForest/torch (CPU wheels pinned), rasterio for raster metadata
and GeoJSON. `pip install -r requirements.txt && streamlit run app/app.py`. **49 tests** cover
the area arithmetic, GSD precedence, resampling and box remapping, union-vs-sum cover, duplicate
suppression, edge flagging and export shapes — and run without model weights, so the
measurement logic is verifiable without a GPU. Imagery is re-fetchable via the two scripts; every
run exports a metadata JSON recording image, GSD and its origin, model versions, all thresholds,
resampling scale and timestamp.

**Default behaviour on the bundled scenes** (Apple M2, MPS):

| Scene | Trees | Trees/ha | Detection scale | Crown area from | Cover bracket | Runtime |
| --- | --- | --- | --- | --- | --- | --- |
| `bc_open_canopy` | 695 | 71.2 | 3.05× | boxes (proxy) | 17.0–92.6% | 14.0 s |
| `bc_dense_canopy` | 705 | 72.2 | 3.05× | boxes (proxy) | 15.1–96.3% | 6.1 s |
| `ch_closed_canopy` | 158 | 37.7 | 1.00× | masks | 16.5–93.9% | 7.1 s |

**A stranger runs it** by opening the demo, picking a bundled scene (provenance and licence shown
inline), pressing Run, then reading the count, the crown areas, the cover bracket and the
limitations panel. GSD comes from raster metadata where present; otherwise the app asks, and
records that the value came from the user.

**Channel order was verified, not assumed.** DeepForest's `predict_tile` docstring specifies
BGR input; this pipeline passes RGB. Tested both on the library's own bundled NEON crop: RGB
gives 55 detections at mean confidence 0.535 (35 above 0.5), BGR gives 29 at 0.389 (5 above
0.5). RGB is correct and the docstring is stale. Every count in this submission would otherwise
have come from swapped colour channels.

**Memory.** Detection, not imagery, is the cost: peak RSS ~1100 MB on a 3125² detection input,
with a ~1050 MB floor even on the smaller scene. Inference reads one window at a time from a
temporary tiled raster rather than holding the image and all its crops, which saves ~170 MB for
bit-identical results (verified by box hash). Run-to-run variance is ±150 MB. Each run records
its own `peak_rss_mb`, so the deployed app reports its real footprint.

**Crown masks are enabled locally, excluded from the deployed MVP.** SAM 2 costs 0.12 s per crown on Apple MPS
(7.2 s for the whole Swiss scene) but several times that on a CPU host, so scenes above 250
detections skip segmentation and fall back to box areas — explicitly labelled a proxy, with the
measured 12–22% overestimate stated in the warning. In practice the 158-crown Swiss scene runs
with masks and the 695-crown BC scenes run with labelled proxies. Degrading to an honest
approximation beats stalling a demo for minutes.

Masks run 0.78× box area at a true 0.10 m and 0.88× on the 0.305 m raster, where a 5 m crown
spans ~16 px and there is little real detail to refine against. Worth stating plainly: this
corrects crown areas by ~20% and does nothing about the dominant error, which is the 80% of
crowns missed in closed canopy.

## What more time or data would buy

1. **Human expert or field reference counts** — converts every "plausible" here into a measurement.
2. **Fine-tuning on closed-canopy imagery** — directly targets the ~20% recall failure, which is
   the dominant error and not fixable by thresholds.
3. **A canopy-vs-ground segmentation model** — replaces the 73-point cover bracket with an actual
   measurement, since crown detection is the wrong instrument for cover.
4. **LiDAR or photogrammetric height** — separates trees from grass, which RGB greenness cannot.
5. Calibrated uncertainty per detection, and geospatial change detection across dates.
