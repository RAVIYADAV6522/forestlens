# ForestLens — 3-Phase Execution Plan

Clock: written Sat 12 Sept ~23:30 IST. Deadline **Mon 14 Sept 23:59 IST** (~48 h).
Budget: 20+ hours hands-on. Requirements and gate criteria live in `docs/SPEC.md`.

## Status as of Sun 13 Sept, ~00:45 IST

| Phase | Gate | Status |
| --- | --- | --- |
| **1. Truthful baseline** | Detector on real licensed satellite imagery, honest numbers | **done**, except the live URL |
| **2. Crown masks + evidence** | Second scene, validation counts, cover bracketing, SAM 2 | **done** |
| **3. Freeze, prove, submit** | Writeup, QA, repo hygiene, demo script | **done**, except deploy and submission |

**Blocked:** deployment needs a Hugging Face write token (`hf auth login`). Everything downstream
of a live URL — the incognito test, the app screenshot in the submission, the submission itself —
waits on that.

**Substituted:** the reference counts in `docs/VALIDATION.md` were made by the AI assistant by
eye, not by a human expert. The substitution is stated everywhere those numbers appear. Replacing
them is the highest-value remaining work.

**Ran ahead of plan:** resampling to the model's training GSD was a Phase 2 "should" and became
Phase 1 core, because without it the detector simply does not work on satellite imagery. Cover
bracketing was not in the original plan at all; it was added after measurement showed summed
crown boxes report 13–21% cover on canopy that is 70–100% closed.

| Phase | Window | Goal | Gate |
| --- | --- | --- | --- |
| **1. Truthful baseline, deployed** | Sat 23:30 → Sun ~15:00 | Real detector on real satellite imagery, honest numbers, **live public URL** | G1 |
| **2. Crown masks + evidence** | Sun ~15:00 → Mon ~13:00 | Second scene, validation with human reference counts, SAM 2 if it earns its place | G2 |
| **3. Freeze, prove, submit** | Mon ~13:00 → 23:59 | No new features. Writeup, QA, rehearsal, submission | G3 |

The ordering principle: **deployment risk is retired first, quality is added second, nothing is
added on day three.** From the end of Phase 1 onward there is always a submittable artifact.

---

## Phase 1 — Truthful baseline, deployed

**Definition of done (Gate G1):** a stranger can open a public URL, run the bundled satellite
scene, and get a tree count plus a canopy area that is either GSD-backed or explicitly labelled
a pixel/proxy figure — produced by real inference, with provenance visible.

### Tasks

| # | Task | Box | Notes |
| --- | --- | --- | --- |
| 1.1 | Install detector stack | 60 m | `uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu` then `uv pip install deepforest`. Verify weights load and `predict_image` returns boxes on a throwaway array. Py 3.12 venv already exists. |
| 1.2 | Source scene S1 (satellite) + licence | 90 m | Maxar Open Data first. Read the licence for **the exact asset**, not the programme page; if the terms are non-commercial, record that and decide whether a hiring submission is compatible. Fall back to another provider rather than fudge it. |
| 1.3 | First real run | 60 m | Crop ~1000×1000 px from S1. `predict_tile` at patch 800 / overlap 0.15. Look at the annotated PNG with your own eyes before believing any number. |
| 1.4 | Wire the real pipeline | 45 m | Sample scene into `data/sample/`, provenance filled, GSD from raster metadata, exports written to `outputs/`. Mostly already built — this is verification, not construction. |
| 1.5 | Git + GitHub | 20 m | `git init`, first commit, public repo pushed. |
| 1.6 | **Deploy to HF Spaces** | 90 m | Streamlit SDK Space. Root `README.md` YAML header (`sdk: streamlit`, `app_file: app/app.py`, `sdk_version`), CPU-pinned torch, `.streamlit/config.toml` with a deliberate `maxUploadSize`, module-level/`cache_resource` model cache. Confirm first-load weight download completes inside the free tier. |
| 1.7 | Gate check | 15 m | Open the URL in incognito. If it works, Phase 1 is banked. |

### Sleep plan
Sat 23:30–01:30 → tasks 1.1 and 1.2 only (install is slow and unattended; imagery hunting is
reading, which suits a tired brain). Sleep. Sun 08:00 → 1.3 onward. Do **not** attempt the
deploy at 03:00.

### Risks

| Risk | Fallback |
| --- | --- |
| DeepForest/torch install fails on Py 3.12 + M2 | Drop the venv to 3.11 (`uv venv --python 3.11`); the code is version-agnostic. |
| 8 GB RAM thrashes on a large raster | Work on crops; tile at 600 px; never load the full scene into the detector in one call. |
| No satellite scene with usable licence found in 90 m | Ship S2-style aerial imagery as the primary scene **and say so plainly** in the app and writeup — a stated deviation beats an unlicensed image. Keep hunting in Phase 2. |
| HF Spaces build times out or OOMs | Detector-only requirements (no SAM 2), smaller sample, and if needed the precomputed-sample fallback from SPEC §7. |

### Do not do in Phase 1
Segmentation. Styling. Extra export formats. Multi-scene UI. Refactoring code that already
passes its tests.

---

## Phase 2 — Crown masks + evidence

**Definition of done (Gate G2):** both scenes analysed, `docs/VALIDATION.md` written with human
reference counts on six named crops, the domain-mismatch warning live in the app, and SAM 2
either deployed and working or explicitly cut with the proxy labelling standing.

### Tasks

| # | Task | Box | Priority |
| --- | --- | --- | --- |
| 2.1 | Source scene S2 (~10 cm aerial) + provenance | 45 m | MUST — NEON AOP RGB or OpenAerialMap. This is the detector's training resolution. |
| 2.2 | Domain-mismatch surfacing | 30 m | MUST — show scene GSD vs model training GSD; warn above ~0.2 m/px that the count is likely an undercount (SPEC §4). |
| 2.3 | **Validation** | 3 h | MUST — 3 crops per scene (easy / dense / degraded), human count by eye, written counting rule, detected vs reference per crop, dominant error type. No aggregate accuracy figure. |
| 2.4 | Negative + edge-path checks | 45 m | MUST — non-forest image as negative control, unknown-GSD path, oversized upload, tile-overlap duplicates, edge clipping. |
| 2.5 | UX hardening | 90 m | MUST — units everywhere, provenance panel on the sample tab, plain-language warnings, sane empty/error states. |
| 2.6 | SAM 2 crown masks | 2–3 h | STRETCH — install, run box-prompted masks on a crop, watch peak memory. Masks must stay cropped per crown (already implemented that way). |
| 2.7 | Optional resampling path | 45 m | SHOULD — upsample coarse imagery toward 10 cm, label it resampling, and compute area with the resampled GSD. |
| 2.8 | Redeploy + decide on SAM 2 | 45 m | MUST — if SAM 2 pushes the Space over memory or cold-start limits, ship detector-only. A working proxy beats a broken mask. |

### The SAM 2 go/no-go rule
Attempt it only after 2.1–2.5 are done. Cut it without hesitation if, by **Mon 09:00**, it is
not producing sane masks on a crop within memory. Proxy area is already honest and already
labelled; segmentation is an upgrade, not a requirement.

### Risks

| Risk | Fallback |
| --- | --- |
| SAM 2 unstable / no Py 3.13 wheels / heavy on 8 GB | Cut per the rule above. Repo keeps the module and the README explains why it is off. |
| Detection is poor on satellite GSD | That is a *finding*, not a failure. Report it with the aerial comparison as evidence. Do not tune thresholds until the count merely looks plausible. |
| Validation reveals large errors | Report them. This is the highest-value section of the submission. |
| Time overrun | Cut in order: 2.7 → 2.6 → depth of 2.5. Never cut 2.3. |

---

## Phase 3 — Freeze, prove, submit

**Hard freeze at Mon 13:00.** After that: no new features, no dependency changes, no
refactors. Bug fixes only if they break a gate criterion.

### Tasks

| # | Task | Box | Notes |
| --- | --- | --- | --- |
| 3.1 | Two-page writeup | 2.5 h | Page 1: problem, imagery + provenance, pipeline diagram, models and why, count method, area method (`N × GSD²`), app screenshot. Page 2: validation setup and per-crop results, failure modes, assumptions, how a stranger runs it, runtime/deploy details, links, what more time/data would buy. Assembled from Phase 2 evidence — nothing invented here. |
| 3.2 | README + repo hygiene | 60 m | Clean clone → setup steps actually work. No secrets. `pytest` green. Provenance and validation docs linked. |
| 3.3 | Clean-browser test | 30 m | Incognito on laptop **and** phone. Sample scene end-to-end. Every download opens. |
| 3.4 | Demo rehearsal | 60 m | The 90-second flow, out loud, three times: pitch → sample + provenance/GSD → run → crowns + count → area method → one limitation you chose to show. |
| 3.5 | Final QA against A1–A12 | 45 m | Tick every acceptance criterion in SPEC §10 explicitly. |
| 3.6 | **Submit** | by 22:00 | Two hours of buffer before 23:59. Non-negotiable. |

### Gate G3 — submission checklist
Live URL works incognito · count reproducible · area basis labelled everywhere · limitations
panel truthful · both provenance records complete · validation doc has no accuracy claim ·
exports work · tests green · README followable · two pages consistent with the app · submitted
with buffer.

---

## Cut list (in order, when time runs short)

1. Optional resampling path (2.7)
2. SAM 2 masks (2.6) — proxy area is already honest
3. GeoJSON export polish
4. Second scene S2 — but then the domain-mismatch section becomes an argument instead of
   evidence, which is a real loss
5. Third validation crop per scene (keep at least easy + dense)

**Never cut:** the live URL, the human reference counts, the limitations panel, provenance, or
the two pages.

## Standing rules

- Any number on screen must be traceable to `N × GSD²` or to a pixel count. If it is not,
  delete it.
- Look at the annotated image before trusting a count. Every time.
- Commit at each gate, so there is always a working state to fall back to.
- When a choice is between *looking* better and *being* auditable, pick auditable — that is
  the stated hiring signal.
