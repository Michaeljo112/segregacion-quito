"""Satellite variables (VIIRS night lights, NDVI, MNDWI) per DMQ zona,
via Google Earth Engine -- replicating the exact methodology of the user's
own repo (github.com/Michaeljo112/Estimando-la-pobreza-parroquial /
local C:/Users/Michael/Documents/ml_zc), which computed these at PARISH
level for `datos22.xlsx`. This script applies the identical queries to the
751 zona polygons instead, closing the gap flagged repeatedly in this
project: `datos22.xlsx`'s satellite variables never existed below parish
granularity, so `build_structural_index.py` could only use census
variables.

Methodology (copied from ndvi.ipynb / mndwi .ipynb / razonamiento_base_
viirs.ipynb, year 2022 to match the census):

  - VIIRS: NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG, band `avg_rad`, per-pixel
    MAX across the 12 months of 2022 (captures peak night-light activity,
    not average), then mean-reduced over each zona polygon at 500m scale.
    NOTE: 500m is coarser than most zonas (751 zonas over ~1,785 km2 of DMQ
    -> ~2.4 km2 average, i.e. comparable to a handful of VIIRS pixels at
    best, sometimes smaller than one) -- neighboring small zonas can come
    back with identical or near-identical values because they share
    underlying pixels. Real satellite signal, but coarser than the zona
    grid itself.
  - NDVI / MNDWI: Sentinel-2 (COPERNICUS/S2_HARMONIZED, matching the
    original notebooks -- top-of-atmosphere, not surface reflectance).
    NDVI = normalizedDifference(B8, B4) / MNDWI = normalizedDifference(B3,
    B11), computed per image then averaged across 2022's collection,
    mean-reduced over each zona polygon at 10m scale (Sentinel-2's native
    optical resolution -- no coarseness issue here, unlike VIIRS above).

    DEVIATION FROM THE ORIGINAL NOTEBOOKS, disclosed: those filtered to
    `CLOUDY_PIXEL_PERCENTAGE < 20` (a whole-SCENE cloud estimate, ~100x100
    km) before averaging. That works for a PARISH-sized polygon, which
    tends to straddle several Sentinel-2 scenes so at least one scene/date
    combination clears 20% somewhere. A single zona (average ~2.4 km2)
    sits inside exactly one scene's footprint, and in 2022 several zonas'
    covering scenes never dropped under 20% cloud on ANY date all year --
    the whole-scene filter would silently return zero images and a blank
    value for those zonas, not a real absence of data. Fixed with PIXEL-
    level cloud masking (Sentinel-2's QA60 bitmask, bits 10/11) instead of
    discarding whole scenes: every image contributes its actually-clear
    pixels to the yearly mean, and masked (cloudy) pixels are excluded
    from the mean at that pixel, not from the whole image.

Resumable: appends to the output CSV and skips zona_id already present, so
an interrupted run can just be restarted.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import ee
import geopandas as gpd
import pandas as pd
from google.oauth2.credentials import Credentials
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[2]
SECTORES_GPKG = ROOT / "data" / "maps" / "sectores_raw" / "extracted" / "dmq_sectores.gpkg"
EE_CREDENTIALS = Path.home() / ".config" / "earthengine" / "credentials"
EE_PROJECT = "maximal-osprey-287122"
OUT_DIR = Path(__file__).resolve().parents[1] / "output"
OUT_PATH = OUT_DIR / "zonas_dmq_satelital.csv"

YEAR = 2022

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def init_earth_engine() -> None:
    import ee.oauth as oauth

    with open(EE_CREDENTIALS) as f:
        d = json.load(f)
    creds = Credentials(
        None,
        refresh_token=d["refresh_token"],
        token_uri=oauth.TOKEN_URI,
        client_id=oauth.CLIENT_ID,
        client_secret=oauth.CLIENT_SECRET,
        scopes=d["scopes"],
    )
    ee.Initialize(credentials=creds, project=EE_PROJECT)


def load_zona_polygons() -> gpd.GeoDataFrame:
    sectores = gpd.read_file(SECTORES_GPKG)
    sectores["zona_id"] = sectores["sec_anm"].str[4:6] + "-" + sectores["sec_anm"].str[6:9]
    zonas = sectores.dissolve(by="zona_id", as_index=False)[["zona_id", "geometry"]]
    return zonas.to_crs(epsg=4326)


def viirs_for(geom: ee.Geometry) -> float | None:
    start = ee.Date.fromYMD(YEAR, 1, 1)
    end = ee.Date.fromYMD(YEAR, 12, 31)
    img = (
        ee.ImageCollection("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG")
        .filterDate(start, end)
        .filterBounds(geom)
        .select("avg_rad")
        .max()
    )
    val = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=500, maxPixels=1e8, bestEffort=True).getInfo()
    return val.get("avg_rad")


def _mask_s2_clouds(image: ee.Image) -> ee.Image:
    """Pixel-level cloud/cirrus mask from the QA60 bitmask -- see module
    docstring for why this replaces the original notebooks' whole-scene
    CLOUDY_PIXEL_PERCENTAGE filter."""
    qa = image.select("QA60")
    cloud_bit = 1 << 10
    cirrus_bit = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit).eq(0).And(qa.bitwiseAnd(cirrus_bit).eq(0))
    return image.updateMask(mask)


def _s2_index_for(geom: ee.Geometry, band_a: str, band_b: str, out_name: str) -> float | None:
    start = ee.Date.fromYMD(YEAR, 1, 1)
    end = ee.Date.fromYMD(YEAR, 12, 31)
    coll = (
        ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
        .filterBounds(geom)
        .filterDate(start, end)
        .map(_mask_s2_clouds)
    )
    if coll.size().getInfo() == 0:
        return None
    idx = coll.map(lambda img: img.normalizedDifference([band_a, band_b]).rename(out_name))
    mean_img = idx.mean()
    val = mean_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=10, maxPixels=1e8, bestEffort=True).getInfo()
    return val.get(out_name)


def ndvi_for(geom: ee.Geometry) -> float | None:
    return _s2_index_for(geom, "B8", "B4", "NDVI")


def mndwi_for(geom: ee.Geometry) -> float | None:
    return _s2_index_for(geom, "B3", "B11", "MNDWI")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not SECTORES_GPKG.exists():
        raise SystemExit(f"No existe {SECTORES_GPKG}. Corre primero name_zonas.py (usa el mismo dmq_sectores.gpkg).")

    init_earth_engine()
    print("Earth Engine inicializado.")

    zonas = load_zona_polygons()
    print(f"Zonas a procesar: {len(zonas)}")

    done = set()
    if OUT_PATH.exists():
        done = set(pd.read_csv(OUT_PATH)["zona_id"].astype(str))
        print(f"Ya procesadas (se saltan): {len(done)}")
    else:
        OUT_PATH.write_text("zona_id,viirs,ndvi,mndwi\n", encoding="utf-8")

    pending = zonas[~zonas["zona_id"].isin(done)]
    t0 = time.time()
    for i, row in enumerate(pending.itertuples(), start=1):
        geom = ee.Geometry(mapping(row.geometry))
        try:
            viirs = viirs_for(geom)
            ndvi = ndvi_for(geom)
            mndwi = mndwi_for(geom)
        except Exception as e:
            print(f"[{i}/{len(pending)}] {row.zona_id}: ERROR {e}")
            continue

        with open(OUT_PATH, "a", encoding="utf-8") as f:
            f.write(f"{row.zona_id},{viirs if viirs is not None else ''},{ndvi if ndvi is not None else ''},{mndwi if mndwi is not None else ''}\n")

        if i % 10 == 0 or i == len(pending):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta_min = (len(pending) - i) / rate / 60 if rate > 0 else float("nan")
            print(f"[{i}/{len(pending)}] {row.zona_id} viirs={viirs} ndvi={ndvi} mndwi={mndwi} -- {rate:.2f} zonas/s, ETA {eta_min:.1f} min")

    print(f"\nListo. Tabla: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
