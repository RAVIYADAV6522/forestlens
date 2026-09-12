# Imagery provenance

Three scenes ship with the demo. Machine-readable records sit beside each raster as
`<name>.provenance.json`, written by `scripts/fetch_maxar_crop.py` at fetch time; this file is
the human summary. Both crops are reproducible — the script re-reads the exact window from the
public COG.

## Scenes S1a/S1b — licence (Maxar/Vantor)

**CC BY-NC 4.0** — attribution required, **non-commercial use only**.
<https://creativecommons.org/licenses/by-nc/4.0/>

> Satellite imagery © Maxar/Vantor, released under the Open Data Program (CC BY-NC 4.0).

The non-commercial clause is a real constraint, stated here deliberately: this imagery is
suitable for a demonstration prototype, and **commercial deployment of this tool would require
separately licensed imagery**. Verified against the Maxar/Vantor Open Data Program terms for
this event on 12 Sept 2026.

### Common properties

| Field | Value |
| --- | --- |
| Provider | Maxar/Vantor Open Data Program |
| Dataset | `events/McDougallCreekWildfire-BC-Canada-Aug-23` (ARD) |
| Area | Okanagan valley near West Kelowna, British Columbia, Canada |
| Platform | WorldView-2 |
| Native sensor GSD | **0.49 m/px** |
| Delivered grid spacing | **0.305 m/px** |
| CRS | EPSG:32611 (UTM 11N) |
| Product | ARD `visual` asset — pansharpened 8-bit RGB |
| Processing | Windowed read, no resampling/stretch/reprojection; re-encoded losslessly from JPEG/YCbCr to deflate |

Both BC crops predate the August 2023 McDougall Creek fire, so the canopy is intact.

### Native GSD vs delivered grid spacing

These are different numbers and the distinction matters. The raster is delivered on a 0.305 m
grid, but the sensor resolved ~0.49 m. Areas computed from the grid are geometrically correct
for the delivered raster; the **detectable detail is limited by the 0.49 m native GSD**. The app
reads 0.305 m from the raster transform and computes area with it, which is right — but no
amount of grid refinement recovers sub-0.49 m structure.

## Scene S1a — open canopy

| Field | Value |
| --- | --- |
| File | `bc_open_canopy.tif` |
| Acquisition | 2022-07-14 |
| Tile / window | quadkey `013331213300`, window (16320, 9180), 1024 × 1024 px |
| Ground extent | ~312 × 312 m (9.77 ha) |
| Cloud (tile) | 0% |
| Character | Open, dry ponderosa/Douglas-fir stand over grass and bare soil; crowns individually separable by eye |

## Scene S1b — dense canopy

| Field | Value |
| --- | --- |
| File | `bc_dense_canopy.tif` |
| Acquisition | 2022-05-18 |
| Tile / window | quadkey `013331213212`, window (13260, 11220), 1024 × 1024 px |
| Ground extent | ~312 × 312 m (9.77 ha) |
| Character | Near-closed conifer canopy on a slope; crowns interlock and are hard to separate by eye |

The BC pair is deliberate: the same sensor, licence and processing at two canopy densities, so
differences in output are attributable to canopy structure rather than to imagery.

## Scene S2 — closed canopy at the detector's training resolution

| Field | Value |
| --- | --- |
| File | `ch_closed_canopy.tif` |
| Provider | swisstopo (Federal Office of Topography) |
| Dataset | `ch.swisstopo.swissimage-dop10` (SWISSIMAGE 10 cm) |
| Area | Swiss plateau near Zürich; closed mixed beech/conifer forest |
| Tile / window | `swissimage-dop10_2022_2683-1235`, window (4560, 6080), 2048 × 2048 px |
| Acquisition | 2022 (SWISSIMAGE flight year; the STAC datetime is a year boundary, not the flight date) |
| Native GSD | **0.10 m/px** |
| Grid spacing | 0.10 m/px |
| CRS | EPSG:2056 (LV95) |
| Ground extent | ~205 × 205 m (4.19 ha) |
| Processing | Windowed read, no resampling/stretch/reprojection; re-encoded to deflate |

**Licence:** swisstopo free geodata (open government data). Free use **including commercial**,
with mandatory source citation. Verified 13 Sept 2026.
<https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices>

> Orthoimagery © swisstopo (SWISSIMAGE 10 cm)

swisstopo notes that some 2018+ SWISSIMAGE products incorporate RapidEye material (© Planet)
over Switzerland's 20 largest lakes. This is an inland forest tile, so that does not apply.

### Why this scene exists

DeepForest's pretrained model was trained on ~0.10 m/px NEON airborne imagery. A NEON crop would
have been the quickest second scene, but NEON is the program the model trained on — possibly
including the very tiles — so it could show behaviour at native resolution without ever testing
generalisation. SWISSIMAGE is the same resolution over structurally different forest (closed
European mixed, not open North American conifer/savanna), which separates the effect of
resolution from the effect of familiarity. That separation is what produced finding F4: resolution
was not the problem.

Its licence is also materially better than the Maxar scenes': commercial use is permitted, which
matters for any productization question.

## Rules

- Verify the licence for the exact asset, not the dataset front page, and quote it as it reads.
- A consumer map screenshot is not measurement data and is not used here.
- If a GSD is assumed rather than read from metadata, say "assumed" and give the reasoning. The
  app records which of the two applied in every export.
