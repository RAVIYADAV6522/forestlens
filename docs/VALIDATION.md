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

Since resolution is optimal here, the binding constraint is **canopy closure** — and,
secondarily, **structural domain**: DeepForest's NEON training data is largely open North
American conifer/savanna, structurally unlike closed European mixed forest. Finer imagery is
not sufficient, and in this case not even helpful.

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
| `bc_open_canopy` | 17.0% | 92.6% | 76 pts |
| `bc_dense_canopy` | 15.1% | 96.3% | 81 pts |
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

## Checks recorded

- **Tile-overlap duplicates:** `predict_tile` produced 993 raw predictions on
  `bc_open_canopy`, reduced to 695 after IoU-0.4 suppression. Suppression is doing real work;
  the threshold is recorded in every run's metadata.
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
- [ ] Proxy-box vs segmentation-mask area comparison (needs SAM 2; see README status).
- [ ] A scene with genuinely separable crowns at 0.10 m, to isolate closure from structure.
