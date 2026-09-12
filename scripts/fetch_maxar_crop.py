#!/usr/bin/env python
"""Fetch a crop from a Maxar/Vantor Open Data ARD tile as a georeferenced GeoTIFF.

Reads only the requested window out of the remote COG, so a 1024 px crop costs a
few hundred KB rather than the 17408 px tile. Writes a provenance sidecar next to
the image recording the STAC item, native sensor GSD, grid spacing, CRS, licence
and the exact window — everything `docs/SPEC.md` §5 requires.

Licence: Maxar/Vantor Open Data is CC BY-NC 4.0 (attribution, non-commercial).
Verify the terms for the event you use before relying on this output.

    python scripts/fetch_maxar_crop.py --event McDougallCreekWildfire-BC-Canada-Aug-23 \
        --quadkey 013331213300 --x 16320 --y 9180 --size 1024 --out data/sample/bc_open.tif
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

import rasterio
from rasterio.windows import Window

ROOT = "https://maxar-opendata.s3.amazonaws.com/events"
LICENCE = "CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/) — attribution required, non-commercial use only"
ATTRIBUTION = "Satellite imagery © Maxar/Vantor, released under the Open Data Program (CC BY-NC 4.0)"


def load_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=90) as response:
        return json.load(response)


def find_item(event: str, quadkey: str) -> tuple[str, dict]:
    """Locate the STAC item for a quadkey by walking the event's acquisitions."""
    collection = load_json(f"{ROOT}/{event}/collection.json")
    acquisitions = [
        link["href"].lstrip("./")
        for link in collection["links"]
        if link.get("rel") == "child"
    ]
    for acquisition in acquisitions:
        data = load_json(f"{ROOT}/{event}/{acquisition}")
        for link in data["links"]:
            if link.get("rel") != "item":
                continue
            relative = link["href"].replace("../", "")
            if f"/{quadkey}/" in f"/{relative}":
                url = f"{ROOT}/{event}/ard/{relative}"
                return url, load_json(url)
    raise SystemExit(f"No item found for quadkey {quadkey} in event {event}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--quadkey", required=True)
    parser.add_argument("--x", type=int, required=True, help="window column offset in the tile")
    parser.add_argument("--y", type=int, required=True, help="window row offset in the tile")
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--label", default="", help="short human label, e.g. 'open canopy'")
    args = parser.parse_args()

    item_url, item = find_item(args.event, args.quadkey)
    properties = item["properties"]
    visual = item_url.rsplit("/", 1)[0] + "/" + item["assets"]["visual"]["href"].lstrip("./")

    window = Window(args.x, args.y, args.size, args.size)
    with rasterio.open(visual) as dataset:
        if args.x + args.size > dataset.width or args.y + args.size > dataset.height:
            raise SystemExit(
                f"Window exceeds tile bounds ({dataset.width}x{dataset.height})"
            )
        data = dataset.read([1, 2, 3], window=window)
        # Built from scratch rather than inherited: the source COG is JPEG/YCbCr, and those
        # keys are incompatible with the lossless deflate we want for a measurement input.
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
        grid_spacing = dataset.res[0]
        crs = str(dataset.crs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(args.out, "w", **profile) as destination:
        destination.write(data)

    provenance = {
        "label": args.label,
        "file": args.out.name,
        "source_provider": "Maxar/Vantor Open Data Program",
        "dataset": f"events/{args.event}",
        "stac_item": item_url,
        "visual_asset": visual,
        "scene_id": item["id"],
        "platform": properties.get("platform"),
        "acquisition_datetime": properties.get("datetime"),
        "native_sensor_gsd_m": properties.get("gsd"),
        "delivered_grid_spacing_m": grid_spacing,
        "crs": crs,
        "off_nadir_deg": properties.get("view:off_nadir"),
        "sun_elevation_deg": properties.get("view:sun_elevation"),
        "cloud_percent_tile": properties.get("tile:clouds_percent"),
        "window": {"col_off": args.x, "row_off": args.y, "width": args.size, "height": args.size},
        "processing": [
            "windowed read of the ARD 'visual' COG (pansharpened 8-bit RGB)",
            "no resampling, no stretch, no reprojection applied by this script",
            "re-encoded losslessly from JPEG/YCbCr to deflate; pixel values unchanged",
        ],
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "note": (
            "Delivered grid spacing is finer than the native sensor GSD. Areas computed from "
            "the grid are geometrically correct for the delivered raster, but the detectable "
            "detail is limited by the native sensor GSD."
        ),
    }
    sidecar = args.out.with_suffix(".provenance.json")
    sidecar.write_text(json.dumps(provenance, indent=2))

    print(f"wrote {args.out} ({args.out.stat().st_size/1e6:.2f} MB)")
    print(f"wrote {sidecar}")
    print(f"native GSD {provenance['native_sensor_gsd_m']} m | grid {grid_spacing} m | {crs}")


if __name__ == "__main__":
    main()
