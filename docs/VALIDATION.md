# Validation

**Status: in progress.** Findings below are observations on named crops, recorded as they were
made. Human reference counts (`docs/SPEC.md` §6) are not yet done, so **no count in this
document is established as correct** — where a number is only "plausible", it says so.

No accuracy figure is published anywhere in this project. There is no labelled ground truth for
these scenes, and eyeballing a detection overlay does not produce precision or recall.

---

## F1 — Pretrained DeepForest fails at native satellite resolution

**Setup:** `bc_open_canopy.tif` (Maxar WV-02, 0.49 m native GSD, 0.305 m grid, 9.77 ha),
pretrained `weecology/deepforest-tree`, confidence ≥ 0.25, tile 800 px / overlap 0.15.

**Observed at native scale:** 57 detections = **5.8 trees/ha**, mean detected "crown"
179 m² (≈15 m across).

The scene visibly contains several hundred crowns, and ponderosa/Douglas-fir crowns here are
4–8 m across, not 15 m. Boxes landed on clumps and shadow patches; large dense areas went
entirely undetected. **The pretrained model does not work on this imagery at native scale.**

**Cause:** the model was trained on ~0.10 m/px NEON airborne RGB. At 0.305 m/px a 5 m crown
spans ~16 px, well below the apparent scale the detector learned.

## F2 — Resampling to the training GSD changes the result by an order of magnitude

Same crop and settings, varying only the detection input scale:

| Scale | Effective GSD | Trees | Trees/ha | Mean crown | Mean conf |
| --- | --- | --- | --- | --- | --- |
| 1× | 0.305 m | 57 | 5.8 | 179 m² (15.1 m) | 0.315 |
| 2× | 0.153 m | 392 | 40.1 | 49.0 m² (7.9 m) | 0.345 |
| **3.05×** | **0.100 m** | **695** | **71.2** | **21.3 m² (5.2 m)** | **0.328** |
| 4× | 0.076 m | 836 | 85.6 | 12.1 m² (3.9 m) | 0.313 |

At 3.05× the effective GSD equals the model's training resolution and crown sizes become
ecologically plausible for this stand type.

**Why 3.05× and not the scale with the "best" count:** the count rises monotonically with
scale and never plateaus, so there is no empirical optimum to pick. The only defensible anchor
is the model's documented training GSD (~0.10 m/px), which is what the pipeline uses. Choosing
4× because 836 looked better would be tuning to a preferred answer.

**What resampling does not do:** it adds no information. Lanczos upsampling of 0.49 m imagery
cannot recover sub-0.49 m structure. It only presents crowns at the pixel size the detector
expects. The jump from 57 to 695 is evidence that the *input scale* was wrong, **not** evidence
that 695 is correct. Confirming 695 requires the human reference counts.

**Residual errors visible in the 3.05× overlay:** some boxes sit on shadow rather than crown;
some crowns receive two boxes; the darkest closed patches remain under-detected.

## F3 — Summed crown boxes are not a canopy-cover measurement in closed canopy

Same settings, both scenes, at 3.05×:

| Scene | Canopy | Trees | Trees/ha | Coverage from summed boxes | Visual cover (by eye) |
| --- | --- | --- | --- | --- | --- |
| `bc_open_canopy` | open | 695 | 71.2 | 15.1% | broadly consistent |
| `bc_dense_canopy` | near-closed | 705 | 72.2 | **13.3%** | **roughly 70–90%** |

Two problems, both underestimates:

1. **Canopy area.** The dense scene is near-closed canopy, yet summed crown boxes report 13.3%
   cover. The detector fires on separable crown apexes, so the union of its boxes does not
   cover interlocking canopy. **Detection-summed area is only defensible in open canopy.**
2. **Count saturation.** Per-hectare counts are nearly identical (71.2 vs 72.2) across
   visibly very different stand densities. A closed stand should carry more stems per hectare.
   The detector appears to saturate once crowns stop being individually separable.

**Consequence for the product:** counting trees and measuring canopy cover are different
measurements needing different methods. Crown detection answers the first; a canopy-vs-ground
classification would answer the second. Reporting the detection-summed area as canopy cover in
closed canopy would be wrong, and the app must not do it unqualified.

---

## Outstanding (SPEC §6)

- [ ] Human reference counts, 3 crops per scene, with the counting rule written down.
- [ ] Scene S2 at ~0.10 m/px (detector's native domain) for comparison.
- [ ] Independent canopy-cover cross-check, to quantify the F3 gap.
- [ ] Proxy-box vs segmentation-mask area comparison.
- [ ] Negative control on a non-forest image.
- [ ] Tile-overlap duplicate and edge-clipping checks recorded.
