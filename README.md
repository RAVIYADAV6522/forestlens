# ForestLens

Detect individual tree crowns in high-resolution forest imagery and estimate the canopy area
they cover — with the assumptions, the uncertainty and the failure cases kept on screen.

Built for the Flora Carbon AI hiring hackathon: count tree crowns in high-resolution satellite
imagery, estimate canopy area, source your own imagery.

**Live demo:** <https://forestlens-cujmcn43y5s8ev8vguauez.streamlit.app> · **Docs:**
[two-page submission](docs/SUBMISSION.md) · [validation findings](docs/VALIDATION.md)

---

## The rule this project is built around

**If the system cannot justify a number, it does not present that number.**

- No ground sampling distance (GSD) → no physical area. Pixel areas only, stated as such.
- No segmentation masks → crown area comes from bounding boxes, labelled `bounding_box_proxy`
  everywhere, with the measured 12–22% overestimate shown.
- No tree detector installed → the app refuses to produce a count rather than inventing one.
  There is deliberately no synthetic fallback detector.
- Model confidence is reported as a model score, **never** as accuracy. No accuracy figure is
  published anywhere in this project, because no labelled evaluation set exists for these scenes.
- Canopy cover is reported as a **bracket**; when the two independent estimates disagree by more
  than 25 points the app declines to give a single figure at all.
- Coverage above 100% is reported as invalid rather than quietly clipped.
- No carbon or biomass estimate. Canopy area is geometry; converting it to carbon needs
  allometry, species and field calibration this project does not have.

## What we found

Six findings shaped the build. Evidence and method in [`docs/VALIDATION.md`](docs/VALIDATION.md).

**1. The pretrained detector fails outright on native satellite imagery.** At 0.305 m/px it
reported 5.8 trees/ha with 15 m "crowns" where real crowns are 4–8 m, firing on clumps and
shadows. DeepForest was trained on ~0.10 m/px imagery, so the pipeline resamples the detection
input to that resolution — taking the same crop to 71.2 trees/ha with 5.2 m crowns.

Resampling adds no information; it only presents crowns at the pixel size the model expects. The
scale is anchored to the model's documented training GSD, **not** chosen empirically — the count
rises monotonically with scale and never plateaus, so picking the nicest number would be tuning
to a preferred answer.

**2. Recall on closed canopy is strongly scale-dependent — and an earlier version of this
README got that wrong.** A 10 cm scene recovered about one crown in five at the scale the app
shipped, and this file previously concluded that canopy closure rather than resolution was the
binding constraint. Varying only the network scale on that same scene gives 29 / 158 / 408 / 548
trees at 0.14 / 0.10 / 0.07 / 0.05 m per network pixel, against a blind visual density of
183 ± 53 /ha. A substantial part of the failure was an app-level scale choice, not the canopy.
Which scale is *correct* is unresolved: the finer ones shrink the median crown to 3.4 m, so they
may be fragmenting rather than finding. See `docs/VALIDATION.md` F4 and F12.

**3. Summed crown boxes are not canopy cover.** Detection fires on separable crown apexes and
cannot tile interlocking canopy, so cover is bracketed between the crown *union* (lower) and
green vegetation cover (upper). On all three scenes those bounds sit 73–81 points apart — the
honest conclusion being that this pipeline counts relatively separable trees and **cannot measure
canopy cover to a useful precision**.

**4. Bounding boxes overestimate crown area by 12–22%,** measured against SAM 2 masks, and the
ratio depends on native resolution (0.78× at a true 0.10 m, 0.88× on 0.305 m imagery where a 5 m
crown spans ~16 px and there is little real detail to refine against).

**5. The tile-size control was silently a scale control.** DeepForest rescales every tile to an
800 px short side, so the detector's real scale is `patch_size × gsd / 800` — which this project
accounted for nowhere. The slider moved the count 3.4× and the median detected crown 2.0×, and
dropping the tile size to fight duplicates made the fragmentation worse. The factor is now
divided out; median crown width is tile-invariant and the shipped default is unchanged. The IoU
"duplicate suppression" control, meanwhile, removes **zero** boxes — DeepForest already bounds
every output pair below its own 0.15 — and four documents previously credited it with a reduction
that was entirely the confidence filter. See F12.

**6. The library's channel-order docstring is wrong.** `predict_tile` documents BGR input; this
pipeline passes RGB. On DeepForest's own NEON crop, RGB gives 55 detections at mean confidence
0.535 against BGR's 29 at 0.389. RGB is correct — worth checking, since the alternative was every
count in this project coming from swapped colour channels.

## Results on the bundled scenes

Apple M2, windowed inference, detector-only (masks off, as deployed):

| Scene | Source | Native GSD | Trees | Trees/ha | Detection scale | Canopy cover | Runtime |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `bc_open_canopy` | Maxar WV-02 | 0.49 m | 695 | 71.2 | 3.05× | 17.0–92.6% | ~14 s |
| `bc_dense_canopy` | Maxar WV-02 | 0.49 m | 705 | 72.2 | 3.05× | 15.1–96.3% | ~6 s |
| `ch_closed_canopy` | SWISSIMAGE | 0.10 m | 158 | 37.7 | 1.00× | 21.0–93.9% | ~7 s |

Against independent counts made by eye **before** any detections were displayed: open canopy
over-counts by +19% and +28%; closed canopy under-counts by −81%. Those reference counts were made
by the AI assistant that built the tool, not a human expert — stated wherever they appear.

## How it works

```
image → read GSD/CRS from raster → resample to the detector's training GSD
      → windowed tiled detection (DeepForest) → boxes + confidence
      → IoU duplicate suppression → edge flags → map boxes back to source pixels
      → optional SAM 2 crown masks → per-crown pixel area × GSD²
      → tree count · crown-area sum · canopy-cover bracket
      → annotated PNG · CSV · GeoJSON · run metadata
```

Tree counting and area measurement are deliberately separate stages: the count comes from the
detector, the area from whatever crown geometry can actually be defended.

### Area maths

With GSD `g` m/px, a crown of `N` pixels covers `N × g²` m². Total crown area is the sum of
accepted crowns. Canopy *cover* uses the crown **union** — not the sum — so overlapping
detections are not double counted, divided by the analysed ground area (image pixels × `g²`).

## Using it

1. Upload a high-resolution RGB forest image (GeoTIFF preferred) or load a bundled scene. The
   detection thresholds sit behind **Advanced settings** in the sidebar, collapsed by default,
   with their active values summarised beside them — the defaults are the validated ones.
2. Confirm the scale — the single biggest lever on the count. A georeferenced raster supplies
   its GSD; otherwise enter the GSD, or, for an ordinary photograph, the approximate width of
   one crown in pixels. The detector looks for crowns about 75 px wide, so an unscaled close-up
   splits each crown into several boxes. Either value is recorded as user-supplied.
3. Run the analysis.
4. Inspect the detected crowns over the source image — orange outlines carry quality flags.
5. Read the metrics, the cover bracket **and** the quality/limitations panel.
6. Download the annotated PNG, per-crown CSV, GeoJSON (when georeferenced) and run metadata.

## Setup

```bash
uv venv --python 3.12          # or: python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/app.py
```

The app runs before the models are installed — it reports that the detector is missing rather
than faking a result. `rasterio` is required to read GeoTIFF metadata (and so obtain a GSD
automatically), to export GeoJSON, and to back the windowed inference path.

### Crown masks (optional)

```bash
pip install -r requirements-segmentation.txt
```

Adds SAM 2 box-prompted crown masks. Excluded from the deployed MVP deliberately: it loads a
second model and corrects crown areas by ~20% without touching the dominant error, which is
crowns missed in closed canopy. Without it the app labels every area a proxy and says by how much
it runs high.

### Tests

```bash
python -m pytest tests -q        # 108 tests; 106 run by default, 2 opt-in
python scripts/qa_check.py       # 13 mechanical checks against docs/SPEC.md §10

# Opt-in: drives the real app through a full analysis via Streamlit's test harness
FORESTLENS_SLOW_TESTS=1 python -m pytest tests/test_app_renders.py -q
```

The suite covers the area arithmetic, GSD precedence, resampling and box remapping, union-vs-sum
cover, Otsu behaviour, duplicate suppression, edge flagging, mask acceptance, export shapes and
the UI's HTML contract (escaping, and the cover bar clamping to 0–100%). It needs only numpy,
pillow and pytest — **no model weights** — so the measurement logic stays verifiable without a
GPU. `qa_check.py` includes a grep for accuracy claims that should not exist.

`tests/test_app_renders.py` additionally drives the real app through Streamlit's `AppTest`
harness, which catches widget arguments the installed Streamlit rejects and exceptions on paths
that only run once a scene is analysed — neither of which a syntax check finds.

### Memory

Detection is the memory cost, not the imagery. Peak RSS measured in a clean process with
streamlit imported, on a 3125×3125 detection input:

| Path | Peak RSS | Detections |
| --- | --- | --- |
| In-memory tiling | ~1270 MB | 695 |
| **Windowed (default)** | **~1100 MB** | 695, identical boxes |

The windowed path writes the detection input to a temporary tiled GeoTIFF so DeepForest reads one
window at a time. Run-to-run variance is ±150 MB and the floor is ~1050 MB even on the smaller
scene, so this is torch's forward pass rather than anything image-sized. Every run records its own
`peak_rss_mb`, so the deployed app reports its real footprint instead of trusting a documented
limit.

### Deploying

**Streamlit Community Cloud** — connect this repo at [share.streamlit.io](https://share.streamlit.io),
main file path `app/app.py`, Python 3.12.

**Hugging Face Spaces was tried and abandoned.** Its Streamlit SDK has been removed entirely
(`sdk: streamlit` now fails with *"Invalid option: expected one of gradio|docker|static"*, despite
still being documented), and it **no longer hosts Docker or Gradio Spaces on the free CPU tier** —
`create_repo` returns `402 Payment Required` and points at PRO. A working Dockerfile and deploy
script were written for that route and then removed rather than left in the repo as an untested,
unusable path; they are in the git history if needed.

## Layout

```
app/app.py                      Streamlit UI
app/theme.py                    palette, global CSS and the app's own components
src/pipeline.py                 orchestration, GSD precedence, resampling, run metadata, exports
src/detection.py                tree detector, windowed tiled inference, NMS, edge flags
src/segmentation.py             box-prompted crown masks (SAM 2), device selection, acceptance
src/metrics.py                  crown areas, canopy totals, quality and cover warnings
src/cover.py                    cover bracketing: crown union vs green vegetation, texture flag
src/io_utils.py                 raster loading, resampling, annotation, CSV/GeoJSON writers
scripts/fetch_maxar_crop.py     reproducible Maxar/Vantor ARD imagery fetcher
scripts/fetch_swissimage_crop.py  reproducible SWISSIMAGE fetcher
scripts/qa_check.py             mechanical QA against the acceptance criteria
scripts/build_figures.py        re-renders report/deck figures from the bundled scenes
scripts/build_report.py         assembles the self-contained IEEE report
scripts/build_deck.py           builds the 12-slide deck with speaker notes
scripts/build_submission_pdf.py two-page submission PDF (fails if it exceeds 2 pages)
data/sample/                    three scenes + provenance records
docs/                           spec, plan, validation findings, submission, demo script
docs/report/                    IEEE report, slide deck, figures
tests/                          108 tests; measurement logic runs without model weights
```

## Imagery

Three scenes, two providers, licences verified for the exact assets used. Full records — CRS,
off-nadir, sun elevation, cloud, processing steps — in
[`data/sample/PROVENANCE.md`](data/sample/PROVENANCE.md) and per-scene JSON sidecars written
automatically at fetch time.

- **Maxar/Vantor Open Data** (WorldView-2, pre-fire Okanagan BC) — **CC BY-NC 4.0**: attribution
  required, **non-commercial only**. Commercial deployment of this tool would need separately
  licensed imagery.
- **swisstopo SWISSIMAGE 10 cm** — open government data, **commercial use permitted** with source
  citation (© swisstopo).

Both fetch scripts read only the requested window from the public COG, so crops are 1–10 MB and
exactly reproducible. Consumer map screenshots are not measurement data and are not used.

## Known limitations

| Limitation | Measured | What the app does about it |
| --- | --- | --- |
| **Closed canopy** | ~1 crown in 5 detected | Counts are severe lower bounds; warned in the panel |
| **Canopy cover** | bounds 73–81 pts apart | Reported as a bracket; single figure refused |
| Open-canopy over-count | +19% to +28% vs reference | Stated in the validation doc; no accuracy claimed |
| Coarse imagery | fails at native 0.305 m | Resampled to training GSD; both facts surfaced |
| **Wrong-scale photographs** | **zoom alone swings the count 7×** | Scale set from a GSD, or from a supplied crown width; warns when neither is known |
| Bounding-box area | overestimates by 12–22% | Masks where available, else labelled PROXY |
| Green water | lake read as 94.3% vegetation | Smooth-vegetation warning; no silent "fix" applied |
| Unknown GSD | — | Physical area withheld; pixel areas only |
| Crowns cut by image edge | 30 of 695 on one scene | Flagged per crown; areas truncated |
| Tile-overlap duplicates | 1544 raw → 993 kept | DeepForest's own mosaic NMS at 0.15; **our IoU control removes 0** |
| Tile size sensitivity | patch 400 → 1379 trees vs 800 → 695 | Recorded; the validated 800 is the default |
| Cross-region generalisation | not evaluated | Stated, not claimed |

## Report and slides

- **[`docs/report/ForestLens-2page.pdf`](docs/report/ForestLens-2page.pdf)** — the two-page
  submission PDF: approach, architecture, key decisions, what worked, what didn't, known
  limitations. The build asserts it stays within two pages.
- **[`docs/report/index.html`](docs/report/index.html)** — IEEE-format technical report.
  Self-contained single file: open it in a browser, or print to PDF. Covers the method, all
  three findings, the rejected approaches, and threats to validity, with eight references.
- **[`docs/report/ForestLens-deck.pptx`](docs/report/ForestLens-deck.pptx)** — 12-slide
  interview deck, **with speaker notes on every slide** covering the questions each slide
  invites.

Both are generated, so their figures and numbers cannot drift from the runs that produced them:

```bash
python scripts/build_figures.py   # re-renders the figures, printing the count in each
python scripts/build_report.py    # inlines them into the report
python scripts/build_deck.py      # rebuilds the deck
python scripts/build_submission_pdf.py   # rebuilds the two-page PDF
```

## Documents

- [`docs/SUBMISSION.md`](docs/SUBMISSION.md) — the two-page technical explanation.
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — findings, reference counts, negative controls,
  and the approaches that were tried and rejected.
- [`docs/SPEC.md`](docs/SPEC.md) — requirements and the A1–A12 submission gate.
- [`docs/PLAN.md`](docs/PLAN.md) — three-phase execution plan and status.
- [`docs/DEMO.md`](docs/DEMO.md) — 90-second demo script and expected questions.
- [`data/sample/PROVENANCE.md`](data/sample/PROVENANCE.md) — imagery sources and licences.

## Status

Working end to end on three real scenes. 108 tests and 13/13 QA checks green, verified from a
clean clone. Detection, resampling, crown masks, cover bracketing, exports, run metadata,
validation and the two-page submission are all complete.

**Outstanding:**

- **Peak memory on the deployed host.** ~1.1 GB locally; Streamlit Community Cloud documents a
  1 GB limit, so each run reports its own `peak_rss_mb` to confirm the real figure rather than
  trusting either number.
- **Human expert reference counts.** The counts behind "+19–28%" and "~1 in 5" were made by an AI
  assistant by eye, not a human expert or field survey. The substitution is stated wherever those
  numbers appear, and replacing it is the single most valuable remaining step.

## Licence

Code is MIT ([`LICENSE`](LICENSE)). **The sample imagery is not** — see the imagery section above
and `data/sample/PROVENANCE.md`.
