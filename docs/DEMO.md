# Demo-day script

90 seconds, then questions. The goal is not to impress with a number — it is to show that every
number on screen can be traced, and to name the one that cannot be trusted before anyone asks.

## The 90 seconds

**0–15 s — what it is**
> "ForestLens takes high-resolution forest imagery and returns individual tree crowns, a count,
> crown areas, and a canopy-cover estimate — with the assumptions and the failure cases on
> screen rather than in a footnote."

**15–35 s — the imagery**
Load `bc_open_canopy`. Point at the provenance line.
> "Maxar Open Data, WorldView-2, 0.49 metre native resolution delivered on a 0.305 metre grid,
> pre-fire Okanagan. CC BY-NC — attribution, non-commercial, which means productizing this would
> need different imagery. The GSD comes from the raster metadata, not from me."

**35–55 s — run it, and explain the resampling**
> "695 trees. Note it resampled 3× first: this detector was trained on 10 centimetre imagery, and
> at native satellite resolution it returned 57 trees with 15-metre crowns — nonsense. Resampling
> doesn't add information, it just presents crowns at the pixel size the model expects. The 3×
> is pinned to the model's training resolution, not chosen because the number looked better."

**55–70 s — the area, and the honest refusal**
> "Crown area is pixel count times GSD squared. Canopy cover, though, is a range: 17% to 93%.
> The low end is the union of detected crowns, the high end is anything green. They're 76 points
> apart, so the app refuses to report a single figure — the midpoint would be meaningless."

**70–90 s — lead with the failure**
Switch to `ch_closed_canopy`.
> "This is the honest part. This scene is 10 centimetre imagery — exactly what the model was
> trained on — and it's the worst result of the three. It finds about one crown in five and
> reports 21% cover on a canopy that's visibly closed. So the limiting factor isn't resolution,
> it's canopy closure. I'd rather show you that than a polished number from the easy scene."

## Questions to expect

| Question | Answer |
| --- | --- |
| How did you count trees? | Pretrained DeepForest, tiled at 800 px with 0.15 overlap, confidence ≥ 0.25. DeepForest's own NMS takes 1544 raw window predictions to 993; the confidence filter takes that to 695. My own IoU control removes nothing — DeepForest already bounds every pair below 0.15. Every threshold is in the run metadata. |
| How did you get canopy area? | Mask or box pixel count × GSD². Masks where SAM 2 ran, boxes labelled proxy otherwise. Cover comes from the crown *union*, not the sum, so overlaps aren't double counted. |
| How accurate is it? | I don't publish an accuracy figure — there's no labelled ground truth for these scenes. What I do have: counted crops. Open canopy the detector runs 19–28% high; closed canopy it finds ~19% of crowns. Those counts are mine by eye, not a field survey. |
| Why is the count 695 and not 57? | Input scale. 57 came from running a 0.10 m model on 0.305 m imagery. Neither number is verified — the counted crops say 695 is the right order of magnitude, ±25%. |
| Isn't upsampling cheating? | It adds no information and I say so on screen. It's matching the model's training scale. What would be cheating is picking 4× because 836 looked better — the count never plateaus, so I anchored to the documented training GSD instead. |
| Where did the imagery come from? | Maxar/Vantor Open Data (CC BY-NC 4.0) and swisstopo SWISSIMAGE (open, commercial use permitted). Provenance and licence per scene in the repo, fetch scripts included so the exact crops are reproducible. |
| Why not just segment the canopy? | That is the right instrument for cover, and it's my first recommendation. Crown detection answers "how many trees"; a canopy-vs-ground classifier answers "how much cover". I shipped the bracket rather than pretend one tool does both. |
| Why no carbon estimate? | Canopy area is geometry. Carbon needs allometry, species and field calibration I don't have. Guessing it for a carbon-markets company seemed like the wrong instinct. |
| What would you do next? | Human reference counts, then fine-tune on closed canopy — that's the 80% error, and no threshold fixes it. Then a segmentation model for cover, and height data to separate trees from grass. |
| Would this work on Indian forests? | Untested, and I'd expect it to struggle. Closed moist-deciduous canopy looks structurally more like the Swiss scene, which was the failure case. It would need fine-tuning and local validation before anyone trusted a number from it. |

## The one-liner if they ask why they should trust it

> "Because I can show you every detected crown, where the resolution came from, the arithmetic
> behind the area, and the scene where it fails worst — and none of those are hidden behind a
> single confident number."

## Before demoing

- [ ] Open <https://forestlens-cujmcn43y5s8ev8vguauez.streamlit.app> in an incognito window; confirm cold start completes
      and that it does **not** ask for a login (app sharing must be Public).
- [ ] Download the CSV and annotated PNG from the app beforehand, as a fallback if the
      network fails mid-demo.
- [ ] Know the three headline numbers cold: 695 / 71.2 per ha, 17–93% cover, ~1 in 5 in closed canopy.
- [ ] Be ready to say "I don't know" about generalisation. It's the true answer.
