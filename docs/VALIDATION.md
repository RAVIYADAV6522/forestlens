# Validation

No accuracy figure is published in this project. There is no labelled ground truth for these
scenes, so what follows is a set of observations on named crops, with the method and its
uncertainty stated. Where a number is uncertain, the uncertainty is given.

**Who counted.** The reference counts below were made by eye by the AI assistant (Claude) that
built this tool, not by a human expert and not by field survey. They are an independent
cross-check — they do not come from the detector — but they are not ground truth, and on
interlocking canopy they carry large error bars. A human expert count remains outstanding and
is the single most valuable thing that could be added.

## Scenes

| Scene | Source | Native GSD | Grid | Canopy | Area |
| --- | --- | --- | --- | --- | --- |
| `bc_open_canopy` | Maxar/Vantor WV-02 | 0.49 m | 0.305 m | open pine/fir over grass | 9.77 ha |
| `bc_dense_canopy` | Maxar/Vantor WV-02 | 0.49 m | 0.305 m | near-closed conifer | 9.77 ha |
| `ch_closed_canopy` | swisstopo SWISSIMAGE | 0.10 m | 0.10 m | closed mixed beech/conifer | 4.19 ha |

Settings throughout: pretrained `weecology/deepforest-tree`, confidence ≥ 0.25, tiles 800 px,
overlap 0.15, IoU 0.4.

---

## F1 — Pretrained DeepForest fails at native satellite resolution

On `bc_open_canopy` at native scale: **57 detections over 9.77 ha (5.8 trees/ha)**, mean
detected "crown" 179 m² (≈15 m across). The scene visibly holds several hundred crowns and real
crowns are 4–8 m across. Boxes landed on clumps and shadow patches; dense areas went entirely
undetected.

**Cause:** the model was trained on ~0.10 m/px NEON airborne RGB. At 0.305 m/px a 5 m crown
spans ~16 px, far below the scale the detector learned.

## F2 — Resampling to the training GSD changes the count by an order of magnitude

Same crop, same settings, varying only detection input scale:

| Scale | Effective GSD | Trees | Trees/ha | Mean crown | Mean conf |
| --- | --- | --- | --- | --- | --- |
| 1× | 0.305 m | 57 | 5.8 | 179 m² (15.1 m) | 0.315 |
| 2× | 0.153 m | 392 | 40.1 | 49.0 m² (7.9 m) | 0.345 |
| **3.05×** | **0.100 m** | **695** | **71.2** | **21.3 m² (5.2 m)** | **0.328** |
| 4× | 0.076 m | 836 | 85.6 | 12.1 m² (3.9 m) | 0.313 |

**Why 3.05× and not the "best" scale:** the count rises monotonically and never plateaus, so
there is no empirical optimum. The only defensible anchor is the model's documented training
GSD (~0.10 m/px), which is what the pipeline uses. Picking 4× because 836 looked better would
be tuning to a preferred answer.

**What resampling does not do:** it adds no information. Lanczos upsampling of 0.49 m imagery
cannot recover sub-0.49 m structure — it only presents crowns at the pixel size the detector
expects. The jump from 57 to 695 shows the *input scale* was wrong; it is not evidence that 695
is correct. That is what F5 tests.

## F3 — Summed crown boxes are not canopy cover

| Scene | Trees | Trees/ha | Cover from summed boxes | Visual cover |
| --- | --- | --- | --- | --- |
| `bc_open_canopy` | 695 | 71.2 | 15.1% | broadly consistent |
| `bc_dense_canopy` | 705 | 72.2 | 13.3% | ~70–90% |
| `ch_closed_canopy` | 158 | 37.7 | 21.3% | **~95–100%** |

The detector fires on separable crown apexes, so the union of its boxes cannot tile
interlocking canopy. Summing also double-counts overlaps, which is why the app now computes
cover from the crown **union** rather than the sum.

Per-hectare counts are also nearly identical across the two BC scenes (71.2 vs 72.2) despite
visibly very different stand densities — the detector saturates once crowns stop being
individually separable.

**Consequence:** counting trees and measuring canopy cover are different measurements requiring
different methods. The app therefore reports cover as a bracket (F6) and never as a single
figure when the bounds disagree.

## F4 — The failure is canopy closure, not resolution

`ch_closed_canopy` is at **exactly** the model's training resolution (0.10 m, no resampling)
and is the *worst* performing scene: 37.7 trees/ha and 21.3% cover on a canopy that is visibly
~95–100% closed. Detections are sparse and scattered, clustering on sunlit broadleaf crowns
while darker conifer areas are ignored.

**This conclusion was overstated, and F12 is why.** The figures above were measured at a
network scale of 0.10 m/px. Re-running the full scene while varying *only* that scale:

| Network GSD | Trees | Trees/ha | Median crown |
| --- | --- | --- | --- |
| 0.14 m | 29 | 7 | 8.8 m |
| 0.10 m | **158** | **38** | 6.7 m |
| 0.07 m | 408 | 97 | 4.5 m |
| 0.05 m | 548 | 131 | 3.4 m |

Against the blind visual density of 183 ± 53 /ha, the 0.05 m network scale reaches 131/ha —
inside the lower end of that interval — where 0.10 m reaches 38/ha. So **a substantial part of
what this document called a closure failure was the network scale**, which is an app-level
choice, not a property of the canopy.

What survives: recall on this scene is strongly scale-dependent, and at the scale the app shipped
it recovered roughly one crown in five. What does **not** survive is the claim that closure rather
than resolution is the binding constraint. It cannot be settled from the evidence here, because
the finer scales also shrink the median crown to 3.4 m — below plausible for mature mixed forest —
so they may be fragmenting rather than finding. Distinguishing the two needs reference counts at
each scale, which do not exist. Structural domain shift remains a plausible contributor and is
equally untested.

## F5 — Independent visual counts

Counting rule: one count per distinguishable crown unit — a contiguous region of consistent
texture and colour bounded by shadow lines or texture discontinuity, with an identifiable
centre. Clumps that could not be separated were counted by apparent apex. Crops were quartered
on screen and counted cell by cell. **Crops were counted before any detections were displayed**,
to avoid anchoring on the model's answer.

| Crop | Scene | Area | Visual count | Detected | Difference |
| --- | --- | --- | --- | --- | --- |
| openA | `bc_open_canopy` (resampled 3.05×) | 0.610 ha | 48 ± 10 | 57 | **+19%** |
| openB | `bc_open_canopy` (resampled 3.05×) | 0.610 ha | 36 ± 8 | 46 | **+28%** |
| chA | `ch_closed_canopy` (native 0.10 m) | 0.262 ha | 48 ± 14 | 9 | **−81%** |

Crop windows, reproducible from the committed rasters: openA (200, 200, 256²), openB
(600, 700, 256²), chA (400, 400, 512²).

**Reading this honestly:**

- In **open canopy** the detector over-counts by roughly 20–30%, which is at or just beyond the
  edge of the counting uncertainty. Likely causes are clump splitting and shadow detections.
  The resampled-satellite count is the right order of magnitude — F2's 695 is plausible, not
  confirmed.
- In **closed canopy** the detector finds roughly **one crown in five**. This is not a
  borderline result and no threshold tuning fixes it.
- The counting uncertainty is itself a finding: at 0.49 m native GSD even a careful human-style
  count cannot separate clumps reliably, so open-canopy agreement should not be over-read.

## F6 — Canopy cover can only be bracketed

The app reports two independent estimates and refuses to average them when they are more than
25 points apart:

| Scene | Lower (crown union) | Upper (green vegetation) | Width |
| --- | --- | --- | --- |
| `bc_open_canopy` | 15.1% | 92.6% | 78 pts |
| `bc_dense_canopy` | 13.3% | 96.3% | 83 pts |
| `ch_closed_canopy` | 21.0% | 93.9% | 73 pts |

The brackets are wide, and that is the truthful answer: **this pipeline cannot measure canopy
cover to a useful precision.** It can count relatively separable trees, give per-crown areas for
those it finds, and bound cover loosely.

Method notes:

- Lower bound: union of crown footprints, so overlaps count once. Too low by every missed crown.
- Upper bound: `2G − R − B > 0`. Too high because grass, shrubs and crops are green.
- **Otsu's method was tried and rejected.** It assumes a bimodal histogram; on a near-uniformly
  vegetated image it splits *within* the vegetation distribution (sunlit vs shaded crown) and
  reported 62% cover on the ~100%-closed Swiss scene. A fixed stated threshold is less clever
  and more honest.
- Threshold sensitivity is reported in the app, because it matters: on `bc_open_canopy` the
  upper bound moves from 92.6% (ExG > 0) to 65.7% (ExG > 20).

## F8 — Crown masks: bounding boxes overestimate crown area by 12–22%

SAM 2 (`facebook/sam2-hiera-small`, box-prompted) refines each detection into a crown mask.
Measured against the boxes that prompted them:

| Scene | Native GSD | Mask/box area | Mean crown (box → mask) | Cover lower bound |
| --- | --- | --- | --- | --- |
| `ch_closed_canopy` | 0.10 m | **0.777×** | 56.5 → 43.9 m² | 21.0% → 16.5% |
| `bc_open_canopy` | 0.49 m (resampled) | **0.876×** | 21.3 → 18.6 m² | 17.0% → 13.2% |

Per-crown ratios on the Swiss scene: mean 0.787, median 0.805, p10 0.627, p90 0.902.

**The ratio depends on native resolution, and that is the interesting part.** At a true 0.10 m
the masks pull well inside the boxes (0.78×) because there is real crown detail to follow. On
the BC scene, segmentation runs on the *source* 0.305 m raster where a 5 m crown spans ~16 px,
so masks hug the boxes (0.88×) — there is little genuine detail to refine against. Mask areas
on coarse imagery are therefore better than boxes but should not be read as precise crown
outlines.

Runtime is not the obstacle it was assumed to be: 0.12 s per crown on Apple MPS, so 7.2 s for
the whole Swiss scene and 18.1 s for 695 crowns on `bc_open_canopy`, detection included.
Segmentation is therefore **enabled by default** wherever SAM 2 is installed, and per-crown
areas are labelled `segmentation_mask` rather than `bounding_box_proxy`.

**This does not change the dominant error.** Correcting crown areas by ~20% is immaterial next
to missing 80% of the crowns in closed canopy (F4/F5). The cover lower bound moves from 21.0% to
16.5% on a ~100%-closed canopy — slightly *further* from the truth, because the bound is limited
by undetected crowns, not by box padding.

## F7 — Negative controls

Both fetched from the same event and settings as the forest scenes.

| Control | Trees | Trees/ha | Crown union | Green vegetation |
| --- | --- | --- | --- | --- |
| Open water (lake) | 2 | 0.2 | 0.0% | **94.3%** |
| Built-up (downtown Kelowna) | 125 | 12.8 | 3.1% | 31.0% |

- **Water passes the count test and breaks the vegetation index.** Two spurious detections over
  9.77 ha is effectively clean. But the greenness index reported 94.3% vegetation on open water,
  because turbid Okanagan lake water genuinely is green-dominant in RGB.
- **Attempted fix, rejected.** Texture was tested as a discriminator, since canopy is rough and
  water is smooth. Median local sigma: water 4.8, closed canopy 20.0 — but the open Okanagan
  stand is 6.3, overlapping water's range. Any threshold that removed the lake would also delete
  most of a legitimate forest scene. Rather than ship a heuristic that only looks right on one
  image, the app **flags** the condition: when vegetation-classified pixels are unusually smooth
  it warns that water or painted surfaces may be inflating the upper bound.
- **The urban scene tests specificity, not zero-detection.** Cities contain real street trees,
  and the overlay shows detections landing overwhelmingly on actual trees and landscaping, with
  large building roofs almost entirely clean. A handful of boxes on rooftop structures are
  genuine false positives. Read as a specificity check, this is a good result for the model.

## F9 — Channel order: the library docstring is wrong

`predict_tile`'s docstring says its `image` argument is "a numpy array in BGR channel order
following openCV convention". This pipeline passes RGB. Rather than assume, both were run on
DeepForest's own bundled NEON crop (`OSBS_029.tif`) — in-domain data the model demonstrably
handles:

| Channel order | Trees | Mean conf | Detections > 0.5 conf |
| --- | --- | --- | --- |
| **RGB (what we pass)** | **55** | **0.535** | **35** |
| BGR (as the docstring says) | 29 | 0.389 | 5 |

RGB nearly doubles the detections and lifts mean confidence markedly, and the high-confidence
count goes from 5 to 35. On `ch_closed_canopy` the same comparison gives 158 (RGB) against 116
(BGR). **RGB is the in-distribution ordering and the docstring is stale** — probably a leftover
from when the library read images with OpenCV. Had this gone the other way, every count in this
document would have been produced from swapped colour channels.

## F10 — Memory: detection is the cost, not the imagery

Peak resident memory measured in a clean process with streamlit imported, as in the deployed
app, on `bc_open_canopy` (1024² source, 3125² detection input after resampling):

| Path | Peak RSS | Detections |
| --- | --- | --- |
| In-memory tiling | ~1270 MB | 695 |
| **Windowed (default)** | **~1100 MB** | 695, identical boxes |

The windowed path writes the detection input to a temporary tiled GeoTIFF so DeepForest reads
one window at a time instead of holding the image and every crop at once. Equivalence was
checked, not assumed: identical tree count, identical total canopy area, identical box hash.

Notes on reading these numbers honestly:

- **Run-to-run variance is roughly ±150 MB** (the same configuration measured 934 MB and
  1107 MB on separate runs), so small differences between configurations mean nothing.
- The floor is ~1050 MB even on the smaller `ch_closed_canopy` scene, so the cost is torch plus
  the model's forward pass, not the image size.
- `torch.inference_mode()` made no reliable difference — DeepForest already disables gradients.
- `patch_size=400` did not reduce peak memory and **changed the results substantially** (1379
  trees, 0.67 ha against 695 trees, 1.48 ha). Tile size is a much bigger lever on the count than
  on memory. The validated 800 is kept.

Every run records its own `peak_rss_mb`, so the deployed app reports its real footprint instead
of relying on a host's documented limit.

## F13 — A semantic upper bound, and an exact lower bound

Two requested upgrades to the cover interval, both measured before adoption.

### Upper bound: SegFormer against the vegetation index

The Excess Green rule is fooled by anything green (F7: 94.3% "vegetation" on open water).
A SegFormer trained on ADE20K, whose label set contains `tree` and `plant`, was measured
against it. `transformers` already ships as a DeepForest dependency, so this adds no new
heavy requirement.

| Scene | Expectation | ExG | SegFormer |
| --- | --- | --- | --- |
| `ch_closed_canopy` | ~95–100% canopy | 93.9% | 93.2% |
| `bc_open_canopy` | well under 90% | 92.6% | 86.4% |
| `bc_dense_canopy` | ~70–90% | 96.3% | **100.0%** |
| Open water (control) | 0% | **94.3%** | **29.3%** |
| Urban (control) | street trees only | 31.0% | **1.7%** |

It is a large improvement on exactly the cases that defeat the index — open water 94.3%
→ 29.3%, urban 31.0% → 1.7% — and comparable on closed canopy. It is **not** adopted as
the default, for two measured reasons:

1. **It is scale-sensitive on nadir imagery.** The same open-canopy scene reads 86.2%
   whole-image and **1.6%** tiled at 512 px — a 54× swing from the feeding strategy
   alone. ADE20K is ground-level photography, so the model has no stable prior for forest
   seen from directly above. This is the same class of defect as F12, now in the cover
   estimator rather than the detector. Whole-image inference is fixed in code with the
   sensitivity recorded beside it.
2. **It still calls a quarter of open water "tree"** (29.3%), and it saturates at 100.0%
   on dense conifer where the visual estimate is 70–90%.

So both are offered, the vegetation index remains the default because it is scale-free
and explainable, and the run metadata records which produced the bound. Neither is a
measurement of canopy cover.

### Lower bound: `shapely.ops.unary_union` instead of a raster union

The lower bound is now the exact geometric union of crown footprints rather than a
rasterised one. This **changed two published figures**, and the direction matters:

| Scene | Raster union | Exact union | Δ |
| --- | --- | --- | --- |
| `bc_open_canopy` | 17.03% | **15.07%** | −1.96 pp |
| `bc_dense_canopy` | 15.1% | **13.3%** | −1.8 pp |
| `ch_closed_canopy` | 20.99% | 20.99% | 0.00 pp |

Rasterising a fractional box with floor/ceil counts every pixel the box touches, which
inflates a quantity that is meant to be a floor. The resampled scenes have fractional
box coordinates and so were inflated; `ch_closed_canopy` runs at scale 1.00× and is
unaffected, which is the control that confirms the mechanism. The exact figures are
lower, which widens the interval — the correct direction for a bound whose whole purpose
is not to overstate. Shapely is an optional import: absent it, the raster union is used
and the method name says so.

Not re-measured: the mask-based lower bounds in F8 (17.0% → 13.2%) were computed with the
raster union and are left as recorded, since they compare box against mask rather than
union method against union method.

## F12 — The tile-size control was silently changing the detector's scale

Reported symptom: many overlapping boxes on the same apparent crown, worst in dense canopy.
Investigated across five independent workstreams with adversarial cross-examination; the
mechanism below survived, and three competing hypotheses were measured and killed.

**DeepForest 2.1.0 leaves torchvision's `GeneralizedRCNNTransform` at its defaults**, verified
on the loaded model: `min_size=(800,)`, `max_size=1333`, with the checkpoint config carrying
`"transforms": null` so it is never overridden. Every window is therefore rescaled to an 800 px
short side before the network sees it, and

    ground metres per network pixel = patch_size × gsd / 800

ForestLens accounted for this nowhere. The tile-size slider was an undocumented *scale* control,
so the user's own mitigation — dropping the tile to 600 px — applied a further 1.33× zoom and
made the fragmentation worse.

Measured on `bc_open_canopy`, varying only the tile slider:

| Tile | Reported scale | Trees | Median crown | Real crowns |
| --- | --- | --- | --- | --- |
| 400 | 3.05× (unchanged) | 1379 | **2.1 m** | 4–8 m |
| 600 | 3.05× (unchanged) | 746 | 3.1 m | 4–8 m |
| 800 | 3.05× | 695 | 4.2 m | 4–8 m |
| 1200 | 3.05× | 404 | 6.2 m | 4–8 m |

At tile 400 each real crown was reported as roughly 2–4 side-by-side fragments, which is exactly
what the overlay showed.

**Fix:** divide the network's own resize back out — `scale *= patch_size / 800`. A strict no-op
at the shipped default, so every published figure stands. After it:

| Tile | Network GSD | Trees | Median crown |
| --- | --- | --- | --- |
| 400 | 0.1000 | 617 | 4.2 m |
| 600 | 0.1000 | 646 | 4.2 m |
| 800 | 0.1000 | **695** | 4.2 m |
| 1200 | 0.1353 (memory cap binds) | 479 | 5.7 m |

Median crown width is now tile-invariant across 400–800 (1.00× swing, was 2.00×) and the count
swing falls from 3.41× to 1.45×. On the reported non-georeferenced case the swing falls from
13.1× to 3.0×. **No tree is deleted**: counts fall at tile < 800 only because each crown stops
being reported as several fragments — the median box doubles from 2.1 m to 4.2 m.

### Post-processing cannot fix this, and three plausible fixes were rejected

- **Our IoU suppression is inert.** Measured on `bc_open_canopy`: 695 boxes in, **695 out** at
  0.40; maximum pairwise IoU among outputs is 0.1499, because DeepForest's own mosaic NMS at its
  un-passed 0.15 default already bounds every pair below that. The control cannot act above
  0.15. At its 0.10 minimum it removes 6 of 695.
- **No IoU threshold separates fragments from real trees.** Two fragments tiling one crown have
  IoU ≈ 0.059 — *lower* than the tightest genuinely adjacent crown pair on the scene, at 0.1499.
  Any threshold low enough to merge fragments merges real neighbours first. Pinned by
  `test_no_iou_threshold_separates_fragments_from_real_neighbours`.
- **Containment and centre-distance suppression were measured and rejected.** Pairs with
  intersection-over-smaller ≥ 0.70 number 1 of 695 on this scene and 0 of 158 on the closed
  scene, so containment has nothing to remove; centre-distance removes a *larger* fraction of
  genuine neighbours at correct scale than at wrong scale, i.e. it deletes real trees first.
- **Tile-boundary duplication was ruled out.** Window offsets are correct (the windowed and
  in-memory paths return bit-identical boxes, 435/435, max difference 0.0 px), and detections are
  not over-represented near seams (observed/expected 0.88–1.17 across bins).
- **Forwarding `iou_threshold` to `predict_tile` was rejected.** At our 0.40 default it *loosens*
  DeepForest's effective global NMS from 0.15 to 0.40: measured 695 → 728 kept and pairs above
  0.70 containment 1 → 19. It would manufacture the reported symptom.

## F11 — On imagery with no GSD, scale alone swings the count 7×

Reported symptom: on an uploaded stock photograph, many crowns went undetected while others
were boxed several times over. Both halves trace to one cause.

The detector looks for objects of a fixed apparent size. Measured: on a 0.10 m/px scene whose
crowns are ~85 px wide the mean detected box is 74 px — and **the mean detected box stays
47–74 px however far the image is zoomed**. So imagery whose crowns are much wider than that
has each crown split into several boxes.

Simulated by taking a 1024 px crop of `ch_closed_canopy`, stripping its GSD as an uploaded
photograph would, and zooming it:

| Zoom | Crown width | Scale applied | Trees | With crown width supplied |
| --- | --- | --- | --- | --- |
| 1× | 85 px | 1.00× | 41 | 41 (unchanged, already near target) |
| 2× | 170 px | 1.00× | **178** | **27** at 0.44× |
| 3× | 255 px | 1.00× | **311** | **27** at 0.29× |

The same forest patch yielded 41, 178 and 311 trees purely from zoom, because
`resample_for_detection` could only derive a scale from a GSD — and a photograph has none, so
it ran at native scale and said nothing.

**Fix.** The scale may now also be derived from a user-supplied *apparent crown width in
pixels*, which makes the count scale-invariant: 27 at both 2× and 3×, against 178 and 311
before. Where a raster supplies a GSD, the GSD still wins — it is measured, the crown width is
eyeballed. Where neither is available the app now says so explicitly rather than running
silently at native scale.

The residual 41-vs-27 gap is an artefact of the simulation, not of the fix: zooming real 0.10 m
data up and then back down loses high-frequency detail a real photograph never had.

**Not the cause: duplicate suppression.** Boxes ≥70% contained within another kept box are
0.1% on `bc_open_canopy` and 0.0% on `ch_closed_canopy`, and stay near zero even at 3× zoom —
the over-split boxes tile a crown side by side rather than nesting, so no IoU or containment
threshold removes them. Only scale does.

**Still not fixed by this.** Missed crowns in dense, uniformly dark canopy are the F4 closure
problem and scale does not address them. And a crown width is an assumption, not a measurement:
it is recorded in the run metadata as user-supplied, and it does **not** unlock physical area —
that still requires a GSD.

## Checks recorded

- **Tile-overlap duplicates:** the measured chain on `bc_open_canopy` is 1544 raw window
  predictions → 993 after DeepForest's own mosaic NMS (its un-passed 0.15 default) → 695 after
  confidence ≥ 0.25 → **695** after our IoU-0.40 suppression, which removes zero boxes. An
  earlier version of this document credited the 993 → 695 step to our suppression and said
  "suppression is doing real work"; that was wrong — see F12.
- **Edge clipping:** 30 of 695 crowns on `bc_open_canopy` and 20 of 158 on `ch_closed_canopy`
  touch the image boundary and are flagged `clipped_at_image_edge`. Their areas are truncated.
- **Unknown-GSD path:** with no GSD, physical areas are withheld and pixel areas reported
  (`test_pipeline_without_gsd_reports_pixels_and_withholds_area`).
- **Coarse-imagery path:** scenes coarser than 0.125 m/px trigger both the resampling note and
  the out-of-training-domain warning.

## Outstanding

- [ ] **Human expert reference counts** — the highest-value addition. The counts in F5 are by
      the AI assistant, not a human.
- [ ] Field or LiDAR-derived canopy cover, to replace the F6 bracket with a measurement.
- [x] Proxy-box vs segmentation-mask area comparison — done, see F8.
- [ ] A scene with genuinely separable crowns at 0.10 m, to isolate closure from structure.
- [ ] Peak memory measured on the deployed host, not just locally.
