"""Choropleth map of the DMQ zona-level K-Means clustering (5 structural profiles).

Dissolves the sector-level cartography (dmq_sectores.gpkg) up to zona_id —
same encoding `name_zonas.py` uses (provincia+canton+parroquia+zona+sector in
`sec_anm`, zona_id = parroquia(2) + "-" + zona(3)) — and joins the cluster
assignment from zonas_dmq_clusters.csv. Same colorblind-validated 5-hue
palette as scripts/build_cluster_map.py (paper 1), for visual consistency
across both papers.

Output: papers/02_quito_microdatos_segregacion/figures/mapa_clusters_quito.png
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SECTORES_GPKG = ROOT / "data" / "maps" / "sectores_raw" / "extracted" / "dmq_sectores.gpkg"
CLUSTERS = ROOT / "output" / "zonas_dmq_clusters.csv"
OUT_DIR = ROOT / "papers" / "02_quito_microdatos_segregacion" / "figures"

# Same validated palette as the nacional map (scripts/build_cluster_map.py):
# blue, yellow, aqua, violet, red -- all-pairs PASS on normal vision, CVD in
# the legal-with-secondary-encoding 6-8 band, mitigated with a white stroke
# between polygons (the "gaps" option).
CLUSTER_COLORS = {
    0: "#2a78d6",  # blue
    1: "#eda100",  # yellow
    2: "#1baf7a",  # aqua
    3: "#4a3aa7",  # violet
    4: "#e34948",  # red
}

# Short profile tag per cluster, matching paper section 5.2's table (ordered
# best-to-worst structural position: 1, 3, 0, 2, 4).
CLUSTER_LABELS = {
    1: "Más aventajado (menor pobreza)",
    3: "Intermedio-alto",
    0: "Intermedio",
    2: "Intermedio-bajo",
    4: "Mayor vulnerabilidad (pobreza 58,8%)",
}


def _plot_clusters(ax, gdf) -> None:
    no_cluster = gdf[gdf["cluster"].isna()]
    if len(no_cluster):
        no_cluster.plot(ax=ax, color="#e1e0d9", edgecolor="white", linewidth=0.1)
    for cluster_id, color in CLUSTER_COLORS.items():
        subset = gdf[gdf["cluster"] == cluster_id]
        if len(subset):
            subset.plot(ax=ax, color=color, edgecolor="white", linewidth=0.15)
    ax.set_axis_off()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sectores = gpd.read_file(SECTORES_GPKG)
    sectores["zona_id"] = sectores["sec_anm"].str[4:6] + "-" + sectores["sec_anm"].str[6:9]
    zonas_geo = sectores.dissolve(by="zona_id", as_index=False)[["zona_id", "geometry"]]
    zonas_geo["area_km2"] = zonas_geo.geometry.area / 1e6

    clusters = pd.read_csv(CLUSTERS)[["zona_id", "cluster"]]
    clusters["cluster"] = clusters["cluster"].astype("Int64")

    merged = zonas_geo.merge(clusters, on="zona_id", how="left")
    matched = merged["cluster"].notna().sum()
    print(f"Zonas con geometría + cluster: {matched} / {len(merged)} (gpkg); {len(clusters)} en el CSV de clusters")

    # Rural parishes in DMQ often collapse to a single catch-all zona (no real
    # INEC subdivision below parish level there), which are geographically
    # enormous compared to the finely-subdivided urban/suburban core -- so a
    # single full-extent map would visually bury the intraurban pattern this
    # paper is actually about. Zoom panel: zonas under 2 km^2 (the genuinely
    # subdivided core), ~92% of zonas by count.
    core = merged[merged["area_km2"] < 2]
    minx, miny, maxx, maxy = core.total_bounds

    fig = plt.figure(figsize=(13, 9.5), dpi=200)
    ax_main = fig.add_axes([0.03, 0.15, 0.44, 0.78])
    ax_zoom = fig.add_axes([0.50, 0.15, 0.47, 0.78])

    _plot_clusters(ax_main, merged)
    ax_main.set_title("Cantón completo (DMQ)", fontsize=10, color="#52514e", pad=6)
    # Outline the zoom extent on the full-canton panel for orientation.
    ax_main.plot(
        [minx, maxx, maxx, minx, minx], [miny, miny, maxy, maxy, miny],
        color="#0b0b0b", linewidth=0.8,
    )

    _plot_clusters(ax_zoom, merged)
    ax_zoom.set_xlim(minx, maxx)
    ax_zoom.set_ylim(miny, maxy)
    ax_zoom.set_title("Núcleo urbano/suburbano (zoom)", fontsize=10, color="#52514e", pad=6)

    fig.suptitle(
        "Perfiles socioeconómicos de zona censal — K-Means k=5, DMQ",
        fontsize=13,
        color="#0b0b0b",
        y=0.98,
    )

    no_cluster = merged[merged["cluster"].isna()]
    handles = [
        plt.Line2D([0], [0], marker="s", linestyle="", markersize=10, markerfacecolor=c, markeredgecolor="none")
        for c in CLUSTER_COLORS.values()
    ]
    labels = [f"{cid} — {CLUSTER_LABELS[cid]} (n={(merged['cluster'] == cid).sum()})" for cid in CLUSTER_COLORS]
    if len(no_cluster):
        handles.append(plt.Line2D([0], [0], marker="s", linestyle="", markersize=10, markerfacecolor="#e1e0d9", markeredgecolor="none"))
        labels.append(f"Sin cluster asignado (n={len(no_cluster)})")

    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.11),
        ncol=3,
        fontsize=8,
        frameon=False,
        title="Cluster (perfil estructural, ver tabla 5.2 del paper)",
        title_fontsize=9,
    )
    fig.text(
        0.03, 0.01,
        "Fuente: elaboración propia — INEC 2022 (censo, sectores), Google Earth Engine (VIIRS/NDVI/MNDWI). "
        "Cartografía: sectores INEC (CapaSectores) disueltos a zona censal. "
        "Recuadro negro en el panel izquierdo = extensión del zoom derecho.",
        fontsize=6.5,
        color="#898781",
    )

    out_path = OUT_DIR / "mapa_clusters_quito.png"
    fig.savefig(out_path, dpi=200, facecolor="white")
    print(f"Guardado: {out_path}")


if __name__ == "__main__":
    main()
