"""K-Means clustering of DMQ zonas by demographic/socioeconomic profile --
the zona-level analogue of `scripts/cluster_vote_patterns.py`'s national
parish clustering (see docs/paper_tendencias_voto_parroquias.md).

Same spirit as that paper: an UNSUPERVISED typology built from structural
variables, not from the electoral margin -- `indice_afinidad` /
`e_votos_afines` are attached to the cluster profile afterward, as a
post-hoc check, never as a clustering input. This keeps it independent of
`build_structural_index.py`'s single composite score (poverty, youth-in-
poverty, unemployment): that script collapses variables into ONE ranked
axis, this one finds GROUPS of zonas that share a whole multivariate
profile, which two zonas can land in even if their `indice_estructural`
scalar looks different, or vice versa.

32 input variables total: `build_zonal_opportunity.py`'s 8 (poverty,
unemployment, youth x sex/poverty cross-tabs), `build_zonal_census_
features.py`'s 21 (ethnicity, education, occupation, digital access,
housing quality, tenure, overcrowding), and `build_zonal_satellite_
features.py`'s 3 (VIIRS night lights, NDVI, MNDWI -- via Google Earth
Engine, replicating the methodology of the user's own repo,
github.com/Michaeljo112/Estimando-la-pobreza-parroquial, at zona instead
of parish granularity). This is the first run with satellite included; an
earlier census-only run (29 variables) exists in git history / the
conversation that produced this file for comparison.

Zonas with no sector geometry (61-888, 63-888 -- both under 10 voters)
have no satellite value and are excluded from the fit anyway by
MIN_VOTANTES_CLUSTER.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import davies_bouldin_score, silhouette_score
from sklearn.preprocessing import StandardScaler

OUT_DIR = Path(__file__).resolve().parents[1] / "output"
ZONAS = OUT_DIR / "zonas_dmq_oportunidad.csv"
EXTENDED = OUT_DIR / "zonas_dmq_features_extended.csv"
NOMBRES = OUT_DIR / "zonas_dmq_nombres.csv"
SATELITAL = OUT_DIR / "zonas_dmq_satelital.csv"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_FEATURES = [
    "censo_nbi_pobreza_pct", "tasa_desempleo_pea", "censo_edad_15_29_pct", "censo_hombres_pct",
    "joven_hombre_pct", "joven_mujer_pct", "joven_pobre_pct", "joven_no_pobre_pct",
]
EXTENDED_FEATURES = [
    "censo_internet_pct", "censo_analf_digital_pct", "censo_discapacidad_pct",
    "censo_educ_superior_pct", "censo_ocupacion_directiva_pct", "censo_ocupacion_elemental_pct",
    "censo_etnia_indigena_pct", "censo_etnia_afro_pct", "censo_etnia_montubio_pct",
    "censo_etnia_mestizo_pct", "censo_etnia_blanco_pct", "censo_etnia_otro_pct",
    "censo_agua_red_pct", "censo_alcantarillado_pct", "censo_electricidad_pct",
    "censo_deficit_habitacional_pct", "censo_vivienda_propia_pct", "censo_internet_fijo_pct",
    "censo_computadora_pct", "censo_auto_pct", "censo_hacinamiento_pct",
]
SATELLITE_FEATURES = ["viirs", "ndvi", "mndwi"]
FEATURES = BASE_FEATURES + EXTENDED_FEATURES + SATELLITE_FEATURES

RANDOM_STATE = 42

# Same threshold as build_structural_index.py / build_priority_list.py's
# "oportunidad" flag: below this, a zona's percentages are artifacts of a
# tiny denominator, not signal. Left out of the clustering fit and
# assignment entirely -- a 3-voter zona (61-888) turned into its own
# singleton k=5 cluster on the first run, because with n=3 every rate is a
# multiple of 33%, making it an extreme outlier on every axis at once.
MIN_VOTANTES_CLUSTER = 300


def load_data() -> pd.DataFrame:
    z = pd.read_csv(ZONAS)
    e = pd.read_csv(EXTENDED)
    df = z.merge(e, on="zona_id", how="inner", validate="one_to_one")

    if not SATELITAL.exists():
        raise SystemExit(f"No existe {SATELITAL} -- corre build_zonal_satellite_features.py primero.")
    sat = pd.read_csv(SATELITAL)
    df = df.merge(sat, on="zona_id", how="left")
    # The 2 zonas with no sector geometry (61-888, 63-888, <10 voters each)
    # have no satellite value either -- already below MIN_VOTANTES_CLUSTER
    # so they get excluded from the fit regardless; leave their satellite
    # columns as NaN here rather than inventing a value.

    if NOMBRES.exists():
        n = pd.read_csv(NOMBRES, dtype={"I03": str})[["zona_id", "nombre_cne"]]
        df = df.merge(n, on="zona_id", how="left")
        df["barrio"] = df["nombre_cne"].where(df["parroquia_sat"] == "Quito", df["parroquia_sat"])
        df = df.drop(columns="nombre_cne")
    else:
        df["barrio"] = df["parroquia_sat"]

    return df


def compare_k(X: np.ndarray, ks: range) -> pd.DataFrame:
    rows = []
    for k in ks:
        km = KMeans(n_clusters=k, n_init=25, random_state=RANDOM_STATE).fit(X)
        labels = km.labels_
        rows.append({
            "k": k,
            "silhouette": silhouette_score(X, labels),
            "davies_bouldin": davies_bouldin_score(X, labels),
            "tamano_min": pd.Series(labels).value_counts().min(),
            "tamano_max": pd.Series(labels).value_counts().max(),
        })
    return pd.DataFrame(rows)


def main() -> int:
    df = load_data()
    print(f"Zonas: {len(df)}  |  variables de entrada: {len(FEATURES)} (incluye VIIRS/NDVI/MNDWI)")

    excluidas = df[df["poblacion_votante"] < MIN_VOTANTES_CLUSTER]
    print(f"Zonas excluidas del clustering por poblacion < {MIN_VOTANTES_CLUSTER} votantes: {len(excluidas)}")
    fit_df = df[df["poblacion_votante"] >= MIN_VOTANTES_CLUSTER].copy()

    X = fit_df[FEATURES].values
    Xs = StandardScaler().fit_transform(X)

    print("\n--- Comparacion de k (3 a 8) ---")
    comparison = compare_k(Xs, range(3, 9))
    print(comparison.to_string(index=False))
    comparison.to_csv(OUT_DIR / "zonas_dmq_cluster_comparacion_k.csv", index=False, encoding="utf-8")

    K = 5  # consistente con el resto del proyecto (cluster nacional y de parroquia usan k=5); ver comparacion arriba
    km = KMeans(n_clusters=K, n_init=25, random_state=RANDOM_STATE).fit(Xs)
    fit_df["cluster"] = km.labels_

    df = df.merge(fit_df[["zona_id", "cluster"]], on="zona_id", how="left")
    df["cluster"] = df["cluster"].astype("Int64")  # nullable int -- excluidas quedan <NA>, no un cluster inventado

    print(f"\n--- Perfil de clusters (k={K}, sobre {len(fit_df)} zonas con >= {MIN_VOTANTES_CLUSTER} votantes) ---")
    profile_cols = FEATURES + ["indice_afinidad", "poblacion_votante", "e_votos_afines"]
    profile = fit_df.groupby("cluster")[profile_cols].mean()
    profile["n_zonas"] = fit_df.groupby("cluster").size()
    print(profile[["n_zonas", "indice_afinidad", "censo_nbi_pobreza_pct", "censo_educ_superior_pct", "censo_ocupacion_directiva_pct", "viirs", "ndvi", "mndwi"]].round(3).to_string())

    profile.to_csv(OUT_DIR / "zonas_dmq_cluster_perfil.csv", encoding="utf-8")

    out_cols = ["zona_id", "barrio", "parroquia_sat", "cluster", "indice_afinidad", "e_votos_afines", "poblacion_votante"] + FEATURES
    df[out_cols].to_csv(OUT_DIR / "zonas_dmq_clusters.csv", index=False, encoding="utf-8")

    print(f"\nTablas: {OUT_DIR / 'zonas_dmq_clusters.csv'}, {OUT_DIR / 'zonas_dmq_cluster_perfil.csv'}, {OUT_DIR / 'zonas_dmq_cluster_comparacion_k.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
