#!/usr/bin/env python
"""Fetch a crop from a SWISSIMAGE 10 cm tile as a georeferenced GeoTIFF.

SWISSIMAGE DOP10 is 0.10 m/px orthoimagery — the resolution the pretrained DeepForest
tree model was trained on — over European mixed forest, which is outside the NEON
training distribution. That combination is what makes it a useful second scene: it
separates the effect of resolution from the effect of the model having seen NEON.

Reads only the requested window from the public COG.

Licence: swisstopo free geodata. Free use including commercial, source citation
required ("© swisstopo"). Verify the current terms before relying on this.

    python scripts/fetch_swissimage_crop.py --tile swissimage-dop10_2022_2683-1235 \
        --x 2000 --y 2000 --size 3072 --out data/sample/ch_closed_canopy.tif
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

import rasterio
from rasterio.windows import Window

STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissimage-dop10/items"
LICENCE = (
    "swisstopo free geodata (open government data). Free use, including commercial, "
    "with mandatory source citation. https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices"
)
ATTRIBUTION = "Orthoimagery © swisstopo (SWISSIMAGE 10 cm)"


def load_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=90) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tile", required=True, help="STAC item id, e.g. swissimage-dop10_2022_2683-1235")
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--y", type=int, required=True)
    parser.add_argument("--size", type=int, default=3072)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    item = load_json(f"{STAC}/{args.tile}")
    asset = next(
        (a for a in item["assets"].values() if a.get("eo:gsd") == 0.1),
        None,
    )
    if asset is None:
        raise SystemExit(f"No 0.1 m asset on item {args.tile}")

    window = Window(args.x, args.y, args.size, args.size)
    with rasterio.open(asset["href"]) as dataset:
        if args.x + args.size > dataset.width or args.y + args.size > dataset.height:
            raise SystemExit(f"Window exceeds tile bounds ({dataset.width}x{dataset.height})")
        data = dataset.read([1, 2, 3], window=window)
        profile = {
            "driver": "GTiff",
            "height": args.size,
            "width": args.size,
            "count": 3,
            "dtype": data.dtype.name,
            "crs": dataset.crs,
            "transform": dataset.window_transform(window),
            "compress": "deflate",
            "predictor": 2,
            "tiled": True,
        }
        grid = dataset.res[0]
        crs = str(dataset.crs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(args.out, "w", **profile) as destination:
        destination.write(data)

    provenance = {
        "label": args.label,
        "file": args.out.name,
        "source_provider": "swisstopo (Federal Office of Topography)",
        "dataset": "ch.swisstopo.swissimage-dop10 (SWISSIMAGE 10 cm)",
        "stac_item": f"{STAC}/{args.tile}",
        "asset": asset["href"],
        "scene_id": args.tile,
        "platform": "airborne digital sensor (orthophoto mosaic)",
        "acquisition_datetime": item["properties"].get("datetime"),
        "native_sensor_gsd_m": asset.get("eo:gsd"),
        "delivered_grid_spacing_m": grid,
        "crs": crs,
        "window": {"col_off": args.x, "row_off": args.y, "width": args.size, "height": args.size},
        "processing": [
            "windowed read of the public COG",
            "no resampling, no stretch, no reprojection",
            "re-encoded to deflate; pixel values unchanged",
        ],
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "note": (
            "Acquisition year is precise to the SWISSIMAGE flight year; the STAC datetime is "
            "the year boundary, not the exact flight date. swisstopo notes that some 2018+ "
            "products incorporate RapidEye material (© Planet) over Switzerland's 20 largest "
            "lakes; this is an inland forest tile, so that does not apply here."
        ),
    }
    sidecar = args.out.with_suffix(".provenance.json")
    sidecar.write_text(json.dumps(provenance, indent=2))
    print(f"wrote {args.out} ({args.out.stat().st_size/1e6:.2f} MB)")
    print(f"native GSD {asset.get('eo:gsd')} m | grid {grid} m | {crs}")


if __name__ == "__main__":
    main()
