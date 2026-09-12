# Imagery provenance

Two scenes ship with the demo. Machine-readable records sit beside each raster as
`<name>.provenance.json`, written by `scripts/fetch_maxar_crop.py` at fetch time; this file is
the human summary. Both crops are reproducible — the script re-reads the exact window from the
public COG.

## Licence (applies to both scenes)

**CC BY-NC 4.0** — attribution required, **non-commercial use only**.
<https://creativecommons.org/licenses/by-nc/4.0/>

> Satellite imagery © Maxar/Vantor, released under the Open Data Program (CC BY-NC 4.0).

The non-commercial clause is a real constraint, stated here deliberately: this imagery is
suitable for a demonstration prototype, and **commercial deployment of this tool would require
separately licensed imagery**. Verified against the Maxar/Vantor Open Data Program terms for
this event on 12 Sept 2026.

## Common properties

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

Both crops predate the August 2023 McDougall Creek fire, so the canopy is intact.

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

The pair is deliberate: the same sensor, licence and processing at two canopy densities, so
differences in output are attributable to canopy structure rather than to imagery.

## Still outstanding

A ~0.10 m/px aerial scene (scene S2) at the detector's training resolution, for the comparison
required by `docs/SPEC.md` §4. Candidates: NEON AOP RGB camera imagery (CC0 1.0, public domain)
or OpenAerialMap (per-asset licence, often CC BY 4.0).

## Rules

- Verify the licence for the exact asset, not the dataset front page, and quote it as it reads.
- A consumer map screenshot is not measurement data and is not used here.
- If a GSD is assumed rather than read from metadata, say "assumed" and give the reasoning. The
  app records which of the two applied in every export.
