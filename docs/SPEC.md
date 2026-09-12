# ForestLens — Specification

Status: authored Sat 12 Sept, ~23:30 IST. Submission deadline **Mon 14 Sept, 23:59 IST**.

This document says what "done" means. `docs/PLAN.md` says in what order we get there.
Every requirement below is either **[MUST]** (no submission without it), **[SHOULD]**
(submission is materially weaker without it) or **[STRETCH]** (only if the phase gate is
already green).

---

## 1. Problem

Given high-resolution satellite imagery of a forest:

1. count the individual tree crowns, and
2. estimate the canopy area those crowns cover.

Judged on three things: does it run, can a stranger use it without the developer present,
and is it honest about its limitations. The organiser states a rough tool that admits its
limits beats a polished tool that invents figures.

## 2. The honesty contract

This is the product's main differentiator, so it is specified, not assumed. Each rule maps to
a test or a visible UI element.

| ID | Rule | Enforced by |
| --- | --- | --- |
| H1 | No GSD → no physical area. Pixel areas only, stated as such. | `metrics.to_physical_area` returns `None`; `test_unknown_gsd_yields_no_physical_area` |
| H2 | Box-derived area is labelled `bounding_box_proxy` in UI, CSV, GeoJSON and metadata. | `metrics.build_crowns`; `test_box_only_detection_is_labelled_proxy` |
| H3 | No detector installed → refuse to count, never fabricate. | `detection.load_detector` raises; UI `st.error` branch |
| H4 | Confidence is a model score, never an accuracy figure. | `metrics.quality_warnings`; `test_confidence_is_never_presented_as_accuracy` |
| H5 | Raster metadata GSD outranks user input; disagreements are logged, not silently resolved. | `pipeline.apply_gsd`; `test_metadata_gsd_is_not_overwritten_by_the_user` |
| H6 | Coverage > 100% is reported as invalid, not clipped. | `test_impossible_coverage_is_called_invalid` |
| H7 | Every run records image, GSD + its origin, model versions, thresholds, timestamp. | `Result.metadata()`; `test_run_metadata_records_the_assumptions` |
| H8 | **No published accuracy number without a real evaluation.** Validation reports observed counts on named crops, not a generalised accuracy claim. | `docs/VALIDATION.md` wording review (Phase 3 gate) |
| H9 | The model-domain mismatch (§4) is stated in the app, the README and the submission. | UI warning + writeup review |

## 3. Functional requirements

### Input
- **[MUST]** Accept GeoTIFF/TIF, PNG, JPEG upload.
- **[MUST]** Read GSD + CRS from a georeferenced raster when present; otherwise accept a
  user-entered GSD in m/px, recording that it came from the user.
- **[MUST]** Ship at least one bundled sample scene so a stranger can run the app with no file
  of their own.
- **[SHOULD]** Warn when a geographic (degree-based) CRS means pixel size is not in metres.
- **[SHOULD]** Reject or warn on imagery too coarse for individual-crown detection (see §4).

### Analysis
- **[MUST]** Tiled inference with a pretrained individual-tree detector; tile size and overlap
  configurable and recorded.
- **[MUST]** Duplicate suppression across tile overlaps (IoU NMS), threshold recorded.
- **[MUST]** Confidence filtering, threshold recorded and adjustable in the UI.
- **[MUST]** Flag detections clipped by the image edge.
- **[SHOULD]** Box-prompted segmentation producing per-crown masks; reject masks that barely
  fill their box and fall back to proxy for that crown only.
- **[STRETCH]** Simple sanity filters (implausible crown size for the given GSD).

### Outputs
- **[MUST]** Tree count.
- **[MUST]** Total canopy area — m² and ha when GSD is known, pixels otherwise.
- **[MUST]** Canopy coverage % when analysed ground area is known.
- **[MUST]** Annotated image showing every detected crown, displayed beside the source image.
- **[MUST]** Per-crown table: id, confidence, box, pixel area, area basis, physical area, flags.
- **[MUST]** CSV export; **[MUST]** run-metadata JSON export; **[MUST]** annotated PNG export.
- **[SHOULD]** GeoJSON export when georeferencing is reliable (disabled with an explanation
  otherwise).
- **[MUST]** A visible quality-and-limitations panel on the results screen.

### Area maths (normative)
With GSD `g` m/px and a crown of `N` pixels: `crown_area_m² = N × g²`.
`total_canopy_area = Σ accepted crown areas`.
`analysed_ground_area = image_pixels × g²`.
`coverage_% = total_canopy_area / analysed_ground_area × 100`.
If `g` is unknown, physical area is **withheld** — not estimated, not defaulted.

### Stranger-usability
- **[MUST]** First screen answers: what this does, what to upload, what you get back.
- **[MUST]** Units beside every physical number.
- **[MUST]** Primary path is one obvious sequence: upload → confirm GSD → run → inspect.
- **[MUST]** Sample scene runnable in one click, with its provenance visible.
- **[SHOULD]** Plain-language warnings, no jargon-only messages.

## 4. The model-domain problem (headline limitation)

The pretrained DeepForest tree model was trained on ~10 cm/px aerial RGB. High-resolution
*satellite* imagery is typically 30–50 cm/px, where a 5 m crown spans only ~10–17 px. Detection
recall degrades and small crowns disappear.

Requirements arising:
- **[MUST]** Report the analysed scene's GSD alongside the model's training GSD in the app.
- **[MUST]** Show a warning when scene GSD is coarser than ~0.2 m/px, stating that the detector
  is operating outside its training domain and the count is likely an undercount.
- **[MUST]** Evaluate two scenes (§5): one genuine satellite scene (the brief) and one ~10 cm
  aerial scene (the model's home turf), and report the difference.
- **[SHOULD]** Offer optional upsampling of coarse imagery to ~10 cm-equivalent before
  detection, labelled as resampling — it changes apparent crown pixel size, and any area
  computed after resampling must use the *resampled* GSD.

## 5. Imagery requirements

- **[MUST]** Two scenes analysed and recorded:
  - **S1 — satellite**, the brief's case. Candidate: Maxar Open Data (~30–50 cm). **Licence must
    be verified for the exact asset**; Maxar Open Data is generally CC BY-NC 4.0, so
    non-commercial terms and attribution have to be checked and stated before use.
  - **S2 — aerial ~10 cm**, the detector's training resolution. Candidates: NEON AOP RGB camera
    imagery (10 cm, GeoTIFF, free and open), or OpenAerialMap drone imagery (check per-asset
    licence, often CC BY 4.0).
- **[MUST]** `data/sample/PROVENANCE.md` completed per scene: provider, dataset, scene/area,
  acquisition date, GSD, CRS, licence terms as they actually read, and every processing step
  applied (crop, resample, stretch).
- **[MUST]** No consumer map screenshots.
- **[SHOULD]** Crowns visually separable by eye in at least part of the scene, so manual
  reference counting (§6) is possible.

## 6. Validation requirements

There is no labelled ground truth, so validation is observational and must be described that
way.

- **[MUST]** Three crops per scene, each containing roughly 30–100 trees, chosen to include one
  easy (open canopy), one hard (dense/closed canopy) and one edge case (shadow, haze, gap, or
  mixed vegetation).
- **[MUST]** A human reference count per crop, done by eye, with the counting rule written down
  (what counts as one tree, how clumps and partial crowns were handled).
- **[MUST]** Reported per crop: reference count, detected count, difference, and a note on the
  dominant error type observed (merges, misses, false positives on shrub/shadow).
- **[MUST]** Wording that keeps this an observation on named crops. No aggregate accuracy
  percentage, no precision/recall implied from eyeballing.
- **[SHOULD]** Proxy-vs-mask area comparison on the same crops when segmentation is available;
  a large systematic gap is itself a reportable finding.
- **[SHOULD]** Checks recorded for: tile-overlap duplicates, edge clipping, unknown-GSD path,
  coarse-imagery path, and a non-forest image as a negative control.
- Results live in `docs/VALIDATION.md` with the crops committed or reproducibly specified.

## 7. Deployment requirements

Target: **Hugging Face Spaces**, Streamlit SDK, free CPU tier (~16 GB RAM, 2 vCPU).

- **[MUST]** Public URL that works in a clean/incognito browser with no developer present.
- **[MUST]** CPU-only torch wheel pinned, so the image builds small and fast enough.
- **[MUST]** Model weights cached after first load (`@st.cache_resource` / module-level cache),
  so a second run is not a cold start.
- **[MUST]** Upload limit configured deliberately; oversized input rejected with a clear message.
- **[MUST]** A bundled sample small enough to run inside the free tier's memory and timeout.
- **[SHOULD]** First-load progress/spinner text that says weights are downloading, not that the
  app is broken.
- **[STRETCH]** Precomputed results for the sample scene, so a cold start or weight-download
  failure still demonstrates the product (clearly marked precomputed, never presented as a
  live run).

## 8. Submission requirements

- **[MUST]** Live demo link.
- **[MUST]** Two-page technical explanation: page 1 problem + system + how count and area are
  computed; page 2 validation + limitations + reproducibility + links.
- **[MUST]** Public repo, clean, no secrets, README that a stranger can follow.
- **[MUST]** Submitted before Mon 14 Sept 23:59 IST.
- **[SHOULD]** Rehearsed 90-second demo for demo day.

## 9. Explicitly out of scope

Authentication, user accounts, databases, training or fine-tuning a model, species
classification, biomass or carbon estimates, change detection, batch/multi-user processing,
animations or visual flourish beyond legibility.

**Carbon and biomass are deliberately excluded.** Canopy area is a geometric measurement;
converting it to carbon needs allometry, species and field calibration we do not have. Saying
so out loud is the correct move for a carbon-market company.

## 10. Acceptance criteria (the submission gate)

| ID | Criterion |
| --- | --- |
| A1 | Detector runs end-to-end on both S1 and S2 locally. |
| A2 | Counts are reproducible: same image + same thresholds → same count. |
| A3 | Area maths verified by test at known GSD; unknown-GSD path withholds area. |
| A4 | Area basis (mask vs proxy) correct and visible in all four outputs. |
| A5 | Annotated image shows crowns over the source; both visible together. |
| A6 | CSV, PNG, run-metadata downloads work; GeoJSON works for georeferenced input. |
| A7 | Limitations panel lists §4 domain mismatch plus every triggered warning. |
| A8 | `PROVENANCE.md` complete for both scenes, licences quoted as they read. |
| A9 | `VALIDATION.md` complete, with no generalised accuracy claim. |
| A10 | Public HF Spaces URL runs the sample scene in an incognito window. |
| A11 | `pytest` green; README setup steps work from a clean clone. |
| A12 | Two-page writeup complete and consistent with what the app actually does. |
