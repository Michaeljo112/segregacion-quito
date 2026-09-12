"""Assign a recognizable neighborhood name to each of the 751 DMQ census zonas.

`build_zonal_opportunity.py` and everything downstream identify zonas only by
their INEC code (e.g. "50-176") -- meaningless to a campaign team. This
script gives each zona a real name by:

1. Dissolving the INEC census-sector cartography (`CapaSectores.zip` ->
   `sectores_anonimizados.gpkg`, the finest geography INEC publishes, ~52.9k
   sectors nationally / 7.179 in DMQ) up to zona level (INEC code
   `sec_anm`: provincia(2) canton(2) parroquia(2) zona(3) sector(3)).
2. Taking each zona's representative point (guaranteed inside the polygon,
   unlike a centroid on an irregular/multipart shape).
3. Spatially joining that point against the CNE's own electoral parish
   cartography (`data/maps/CNE_parroquias_desde2013.shp` -- 65 named
   parishes for canton Quito: the 33 rural/suburban ones already used
   throughout this analysis, plus the 32 urban ones from
   `build_urban_real_margin.py`, e.g. Cotocollao, Chillogallo, La Mariscal).

For the 247 zonas inside the 33 already-known rural parishes this mostly
just confirms what `build_zonal_opportunity.py`'s crosswalk already says
(`parroquia_sat`) -- useful as a sanity check on the join itself. The real
payoff is the 504 urban zonas: INEC's own census geography treats all of
them as a single parish ("Quito"), but this join assigns each one to one of
the 32 named CNE urban parishes instead.

Caveat, stated plainly: this is a POINT-IN-POLYGON join between two
independently-drawn administrative systems (INEC census zonas vs. CNE
electoral parishes), not a boundary reconciliation. A zona whose
representative point sits near a CNE parish boundary could be assigned to
the neighboring parish. Treat the name as "the neighborhood this zona is
most likely part of", not a surveyed boundary -- exactly the same caveat
`build_urban_real_margin.py` already states about mixing these two systems.
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SECTORES_GPKG = ROOT / "data" / "maps" / "sectores_raw" / "extracted" / "dmq_sectores.gpkg"
CNE_PARROQUIAS = ROOT / "data" / "maps" / "CNE_parroquias_desde2013.shp"
ZONAS_OPORTUNIDAD = Path(__file__).resolve().parents[1] / "output" / "zonas_dmq_oportunidad.csv"
OUT_DIR = Path(__file__).resolve().parents[1] / "output"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

QUITO_CODPRO = "17"
QUITO_CODCAN = 60


def load_zona_points() -> gpd.GeoDataFrame:
    sectores = gpd.read_file(SECTORES_GPKG)
    sectores["zona_id"] = sectores["sec_anm"].str[4:6] + "-" + sectores["sec_anm"].str[6:9]
    sectores["I03"] = sectores["sec_anm"].str[4:6]

    zonas = sectores.dissolve(by="zona_id", as_index=False).loc[:, ["zona_id", "I03", "geometry"]]
    points = gpd.GeoDataFrame(
        zonas[["zona_id", "I03"]],
        geometry=zonas.geometry.representative_point(),
        crs=zonas.crs,
    )
    return points


def load_cne_parishes() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(CNE_PARROQUIAS)
    q = gdf[(gdf["CODPRO"] == QUITO_CODPRO) & (gdf["CODCAN"] == QUITO_CODCAN)].copy()
    q = q[["PARROQUIA", "ESTADO", "geometry"]].rename(columns={"PARROQUIA": "nombre_cne", "ESTADO": "tipo_cne"})
    q["nombre_cne"] = q["nombre_cne"].str.title()
    return q


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not SECTORES_GPKG.exists():
        raise SystemExit(
            f"No existe {SECTORES_GPKG}. Corre primero la extraccion/filtro de CapaSectores.zip a DMQ."
        )

    points = load_zona_points()
    print(f"Zonas censales en DMQ (sectores disueltos): {len(points)}")

    parishes = load_cne_parishes()
    print(f"Parroquias CNE (canton Quito): {len(parishes)}")

    points_proj = points.to_crs(parishes.crs)
    joined = gpd.sjoin(points_proj, parishes, how="left", predicate="within")

    # Fallback for points that land just outside every polygon (edge/precision cases): nearest parish.
    missing = joined["nombre_cne"].isna()
    if missing.any():
        print(f"Puntos sin match directo (within): {missing.sum()} -- usando parroquia mas cercana")
        nearest = gpd.sjoin_nearest(points_proj[missing], parishes, how="left")
        joined.loc[missing, "nombre_cne"] = nearest["nombre_cne"].values
        joined.loc[missing, "tipo_cne"] = nearest["tipo_cne"].values

    result = joined[["zona_id", "I03", "nombre_cne", "tipo_cne"]].copy()

    # Cross-check: for zonas inside the 33 already-known rural parishes, does
    # the spatial join's name roughly match what build_zonal_opportunity.py
    # already uses (parroquia_sat)? Purely a sanity check, printed not used.
    if ZONAS_OPORTUNIDAD.exists():
        known = pd.read_csv(ZONAS_OPORTUNIDAD)[["zona_id", "parroquia_sat"]]
        check = result.merge(known, on="zona_id", how="inner")
        check = check[check["tipo_cne"] == "RURAL"]
        mismatch = check[check["nombre_cne"].str.upper() != check["parroquia_sat"].str.upper()]
        print(f"Zonas rurales: {len(check)} -- coinciden con parroquia_sat: {len(check) - len(mismatch)}")
        if len(mismatch):
            print("Discrepancias (revisar):")
            print(mismatch.head(20).to_string(index=False))

    out_path = OUT_DIR / "zonas_dmq_nombres.csv"
    result.sort_values(["I03", "zona_id"]).to_csv(out_path, index=False, encoding="utf-8")

    print()
    print(f"Zonas urbanas (parroquia INEC 'Quito') nombradas: {(result['I03']=='50').sum()}")
    print("Distribucion de zonas urbanas por nombre CNE asignado:")
    print(result[result["I03"] == "50"]["nombre_cne"].value_counts().to_string())
    print(f"\nTabla completa: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
