"""Zonal (INEC "zona censal") opportunity map for the DMQ mayoral race.

Same "esperanza matematica" framing as `build_sector_opportunity.py`:

    E[votos afines, z] = poblacion_votante(z) * indice_afinidad(z)

but at a coarser, more actionable geography (~751 zonas vs. 7,204 sectores --
INEC's hierarchy is provincia > canton > parroquia (I03) > zona (I04) >
sector (I05) > manzana), AND with a richer `indice_afinidad` predictor: where
`build_sector_opportunity.py` predicted the missing urban-core margin from
five MARGINAL rates (poverty, three separate age brackets, sex ratio), this
script predicts it from CROSS/joint distributions -- age x sex and age x
poverty(NBI) -- using real national census cross-tabulation tables (INEC
tables "2.1 Poblacion por sexo al nacer ... y grupos quinquenales de edad"
and "3.2 Poblacion ... por condicion de pobreza por NBI y sexo al nacer ...
y grupos quinquenales de edad"), not independent marginals. This directly
tests whether the youth/poverty/sex correlations flagged in
docs/paper_tendencias_voto_parroquias.md (SS5.1: young, poor, unemployed ->
lower affinity, each checked one at a time) are actually driven by a specific
INTERACTION (e.g. "young AND poor" vs. "young AND not poor") rather than by
each marginal independently -- which changes where campaign effort should
concentrate.

Zona was chosen over sector as the target geography for this analysis
because (a) 751 zonas is a tractable number for a campaign team to actually
plan against, unlike 7,204 anonymous sector codes, and (b) coarser
aggregation gives more stable cross-tabulated rates per unit than sector
(some sectors have very small populations for four-way splits).

UPDATE (2026-09-08): the cross-tab model above predicts the urban core's
margin because, when this script was first written, no real electoral
result existed at any geography finer than "Quito, one row" for the urban
core. That's no longer true. `build_urban_real_margin.py` recovered the
real presidencial-2025 margin for the 32 named CNE urban parishes (straight
from CNE microdata this repo already had), and `name_zonas.py` built a
point-in-polygon crosswalk from each zona to the CNE parish it most likely
sits inside. This script now uses that crosswalk to INHERIT the real
parish-level margin into each zona it can reach, and falls back to the
cross-tab model's prediction only for the small residue with no crosswalk
match (2 zonas with no sector geometry, `61-888` / `63-888`). The model
itself, its national validation, and the "young x poverty, not young alone"
finding (SS6.2 of the report) are kept exactly as before -- they were never
about the urban core's real margin, they were an independent, useful result
in their own right. What changes is which number actually lands in
`margen_usado`/`indice_afinidad`/`e_votos_afines` for the ~502 zonas the
crosswalk now reaches.

Same caveats as the rest of this repo: `indice_afinidad` is a RELATIVE
priority weight normalized within DMQ, not a calibrated vote-share forecast.
The inherited real margin carries the same caveat as `name_zonas.py`'s
crosswalk itself: a zona near a CNE parish boundary could inherit its
neighbor's margin instead of its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_score

ROOT = Path(__file__).resolve().parents[2]
NATIONAL_CLUSTERS = ROOT / "data" / "model" / "parroquia_clusters_pc_kmeans_k5.csv"
NATIONAL_INDICATORS = ROOT / "data" / "model" / "census_indicator_features.csv"
SECTOR_DIR = ROOT / "data" / "censo_sector" / "processed"
POBLACION_DMQ = SECTOR_DIR / "poblacion_dmq.csv"
CROSSWALK = SECTOR_DIR / "dmq_parroquia_crosswalk.csv"
OUT_DIR = Path(__file__).resolve().parents[1] / "output"
NOMBRES_ZONAS = OUT_DIR / "zonas_dmq_nombres.csv"
URBAN_MARGIN_REAL = OUT_DIR / "dmq_nucleo_urbano_margen_real.csv"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# --- Marginal-only baseline (same features as build_sector_opportunity.py),
# kept here purely so the cross-tab model's validation can be reported
# side-by-side against it, not swapped in blind.
BASELINE_FEATURES = [
    "censo_nbi_pobreza_pct",
    "censo_edad_de_15_19_pct",
    "censo_edad_de_20_24_pct",
    "censo_edad_de_25_29_pct",
    "censo_hombres_pct",
]

# --- Cross/joint features: age x sex (table 2.1) and age x poverty (table 3.2).
YOUTH_BRACKETS = ["de_15_19", "de_20_24", "de_25_29"]

CROSS_FEATURES = [
    "censo_nbi_pobreza_pct",  # overall poverty level, kept as a control
    "censo_hombres_pct",  # overall sex ratio, kept as a control
    "joven_hombre_pct",  # age 15-29 AND male
    "joven_mujer_pct",  # age 15-29 AND female
    "joven_pobre_pct",  # age 15-29 AND NBI-poor
    "joven_no_pobre_pct",  # age 15-29 AND NOT NBI-poor
]


def _sex_age_cols(sex: str) -> list[str]:
    return [
        f"censo_ind_estructura_poblacional_2_1_{b}_sexo_al_nacer_{sex}" for b in YOUTH_BRACKETS
    ]


def _poverty_age_cols(pobre_token: str) -> list[str]:
    return [
        f"censo_ind_pobreza_nbi_3_2_{b}_condicion_de_pobreza_por_necesidades_basicas_"
        f"insatisfechas_nbi_{pobre_token}_sexo_al_nacer_{sex}"
        for b in YOUTH_BRACKETS
        for sex in ("hombres", "mujeres")
    ]


def load_national_with_cross_features() -> pd.DataFrame:
    """National parish table with cross-tabulated age x sex x poverty rates attached."""
    clusters = pd.read_csv(NATIONAL_CLUSTERS)
    ind = pd.read_csv(NATIONAL_INDICATORS)

    hombre_cols = _sex_age_cols("hombres")
    mujer_cols = _sex_age_cols("mujeres")
    pobre_cols = _poverty_age_cols("pobres")
    no_pobre_cols = _poverty_age_cols("no_pobres")

    needed = ["ADM3_PCODE"] + hombre_cols + mujer_cols + pobre_cols + no_pobre_cols
    ind = ind[needed].copy()

    df = clusters.merge(ind, on="ADM3_PCODE", how="left")
    pop = df["censo_personas"].replace(0, np.nan)

    df["joven_hombre_pct"] = df[hombre_cols].sum(axis=1) / pop
    df["joven_mujer_pct"] = df[mujer_cols].sum(axis=1) / pop
    df["joven_pobre_pct"] = df[pobre_cols].sum(axis=1) / pop
    df["joven_no_pobre_pct"] = df[no_pobre_cols].sum(axis=1) / pop
    return df


def _fit_and_validate(df: pd.DataFrame, features: list[str], label: str) -> tuple[LinearRegression, pd.DataFrame, pd.DataFrame]:
    train = df.dropna(subset=["pc_economic_right_minus_left"] + features).copy()
    X = train[features]
    y = train["pc_economic_right_minus_left"]

    model = LinearRegression().fit(X, y)
    cv = cross_val_score(model, X, y, cv=KFold(5, shuffle=True, random_state=42), scoring="r2")

    dmq = df[df["canton_sat"].astype(str).str.contains("Metropolitano de Quito", case=False, na=False)].copy()
    dmq = dmq[dmq["parroquia_sat"] != "Quito"]
    Xq = dmq[features].fillna(dmq[features].median())
    dmq["pred_" + label] = model.predict(Xq)

    validation = pd.DataFrame(
        [
            {"modelo": label, "check": "n_features", "value": len(features)},
            {"modelo": label, "check": "r2_in_sample_nacional", "value": model.score(X, y)},
            {"modelo": label, "check": "r2_cv5_nacional", "value": cv.mean()},
            {
                "modelo": label,
                "check": "corr_pred_vs_real_econ_dmq",
                "value": dmq["pred_" + label].corr(dmq["pc_economic_right_minus_left"]),
            },
            {
                "modelo": label,
                "check": "corr_pred_vs_real_noboa_margin_dmq",
                "value": dmq["pred_" + label].corr(dmq["elec_v2_noboa_minus_luisa"]),
            },
        ]
    )
    return model, dmq, validation


def fit_and_validate_model() -> tuple[LinearRegression, pd.DataFrame]:
    df = load_national_with_cross_features()

    _, dmq_base, val_base = _fit_and_validate(df, BASELINE_FEATURES, "baseline_marginal")
    model_cross, dmq_cross, val_cross = _fit_and_validate(df, CROSS_FEATURES, "cruzado_edad_sexo_pobreza")

    print("--- Comparacion: modelo marginal (baseline) vs. modelo con cruces edad x sexo x pobreza ---")
    print(pd.concat([val_base, val_cross]).to_string(index=False))
    print()

    # Independent check: within the 33 known DMQ parishes, which single cross
    # cell tracks the real margin best? (Descriptive, not used for prediction.)
    corr_rows = []
    for feat in CROSS_FEATURES:
        corr_rows.append(
            {"feature": feat, "corr_con_margen_noboa_real_dmq": dmq_cross[feat].corr(dmq_cross["elec_v2_noboa_minus_luisa"])}
        )
    print("--- Que cruce individual se asocia mas con el margen real, dentro de las 33 parroquias conocidas de Quito ---")
    print(pd.DataFrame(corr_rows).sort_values("corr_con_margen_noboa_real_dmq").to_string(index=False))
    print()

    return model_cross, df


def load_zone_population() -> pd.DataFrame:
    df = pd.read_csv(POBLACION_DMQ, sep=";", dtype=str)
    df["P02"] = pd.to_numeric(df["P02"], errors="coerce")  # 1 hombre, 2 mujer
    df["P03"] = pd.to_numeric(df["P03"], errors="coerce")  # edad
    df["NBI"] = pd.to_numeric(df["NBI"], errors="coerce")  # 1 pobre, 2 no pobre
    df["CONDACT1"] = pd.to_numeric(df["CONDACT1"], errors="coerce")
    df["zona_id"] = df["I03"] + "-" + df["I04"]
    df["es_joven"] = df["P03"].between(15, 29)
    return df


def aggregate_zones(pop: pd.DataFrame) -> pd.DataFrame:
    g = pop.groupby(["I03", "zona_id"])
    out = g.agg(
        poblacion_total=("P02", "size"),
        poblacion_votante=("P03", lambda s: (s >= 16).sum()),
        censo_hombres_pct=("P02", lambda s: (s == 1).mean()),
        censo_edad_15_29_pct=("es_joven", "mean"),
    ).reset_index()

    nbi = pop.dropna(subset=["NBI"]).groupby("zona_id")["NBI"].apply(lambda s: (s == 1).mean())
    pea = pop[pop["CONDACT1"].isin([2, 3])]
    desempleo = pea.groupby("zona_id")["CONDACT1"].apply(lambda s: (s == 3).mean())
    out = out.merge(nbi.rename("censo_nbi_pobreza_pct"), on="zona_id", how="left")
    out = out.merge(desempleo.rename("tasa_desempleo_pea"), on="zona_id", how="left")

    # Cross/joint shares -- computed directly from person-level microdata, no
    # model needed here (these are the same TARGET-side quantities the
    # national regression's cross features are trying to predict where no
    # real vote margin exists).
    n_total = pop.groupby("zona_id")["P02"].transform("size")
    pop = pop.assign(n_total=n_total)

    def _share_joven(subset: pd.DataFrame) -> pd.Series:
        return subset.groupby("zona_id").apply(
            lambda d: d["es_joven"].sum() / d["n_total"].iloc[0], include_groups=False
        )

    joven_hombre = _share_joven(pop[pop["P02"] == 1])
    joven_mujer = _share_joven(pop[pop["P02"] == 2])
    joven_pobre = _share_joven(pop[pop["NBI"] == 1])
    joven_no_pobre = _share_joven(pop[pop["NBI"] == 2])

    out = out.merge(joven_hombre.rename("joven_hombre_pct"), on="zona_id", how="left")
    out = out.merge(joven_mujer.rename("joven_mujer_pct"), on="zona_id", how="left")
    out = out.merge(joven_pobre.rename("joven_pobre_pct"), on="zona_id", how="left")
    out = out.merge(joven_no_pobre.rename("joven_no_pobre_pct"), on="zona_id", how="left")
    for col in ["joven_hombre_pct", "joven_mujer_pct", "joven_pobre_pct", "joven_no_pobre_pct"]:
        out[col] = out[col].fillna(0.0)
    return out


def load_inherited_urban_margin() -> pd.Series | None:
    """Zona -> real margin, inherited via name_zonas.py's zona->CNE-parish
    crosswalk from build_urban_real_margin.py's real parish-level results.
    Returns None (caller falls back to the model for every urban zona) if
    either input hasn't been generated yet."""
    if not (NOMBRES_ZONAS.exists() and URBAN_MARGIN_REAL.exists()):
        return None

    nombres = pd.read_csv(NOMBRES_ZONAS, dtype={"I03": str})
    urbano = pd.read_csv(URBAN_MARGIN_REAL)
    urbano["_key"] = urbano["parroquia_urbana_cne"].str.strip().str.upper()
    margin_by_name = urbano.set_index("_key")["elec_v2_noboa_minus_luisa"]

    nombres["_key"] = nombres["nombre_cne"].astype(str).str.strip().str.upper()
    nombres = nombres[nombres["I03"] == "50"].copy()  # only the urban parish, "Quito"
    nombres["margen_real_urbano"] = nombres["_key"].map(margin_by_name)
    matched = nombres["margen_real_urbano"].notna().sum()
    print(f"Zonas urbanas con margen real heredado via nombre de barrio: {matched} de {len(nombres)}")
    return nombres.set_index("zona_id")["margen_real_urbano"]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not POBLACION_DMQ.exists():
        raise SystemExit(f"No existe {POBLACION_DMQ}. Corre primero la extraccion desde el CSV nacional del INEC.")

    model, national = fit_and_validate_model()

    pop = load_zone_population()
    zones = aggregate_zones(pop)

    crosswalk = pd.read_csv(CROSSWALK, dtype={"I03": str})
    crosswalk["I03"] = crosswalk["I03"].str.zfill(2)
    zones = zones.merge(crosswalk, on="I03", how="left")

    dmq_resolved = national[
        national["canton_sat"].astype(str).str.contains("Metropolitano de Quito", case=False, na=False)
    ].copy()
    dmq_resolved = dmq_resolved[dmq_resolved["parroquia_sat"] != "Quito"]
    real_margin = dmq_resolved.set_index(dmq_resolved["ADM3_PCODE"].str[-2:])["elec_v2_noboa_minus_luisa"]
    zones["margen_real_parroquia"] = zones["I03"].map(real_margin)

    Xz = zones[CROSS_FEATURES].copy()
    for col in CROSS_FEATURES:
        Xz[col] = Xz[col].fillna(Xz[col].median())
    zones["margen_predicho"] = model.predict(Xz)

    inherited = load_inherited_urban_margin()
    if inherited is not None:
        zones["margen_real_urbano"] = zones["zona_id"].map(inherited)
    else:
        zones["margen_real_urbano"] = np.nan

    # Priority: real margin of the 33 known rural/suburban parishes (direct,
    # highest confidence) > real margin inherited from the CNE urban parish
    # via name_zonas.py's crosswalk (one join away, same caveat as that
    # script) > cross-tab model prediction (last resort, ~2 zonas with no
    # crosswalk match).
    zones["margen_usado"] = zones["margen_real_parroquia"].fillna(zones["margen_real_urbano"]).fillna(zones["margen_predicho"])
    zones["fuente_margen"] = np.select(
        [zones["margen_real_parroquia"].notna(), zones["margen_real_urbano"].notna()],
        ["real_parroquia", "real_barrio_cne"],
        default="modelo_predicho_cruzado",
    )

    lo, hi = zones["margen_usado"].min(), zones["margen_usado"].max()
    zones["indice_afinidad"] = ((zones["margen_usado"] - lo) / (hi - lo)).clip(0, 1)
    zones["e_votos_afines"] = zones["poblacion_votante"] * zones["indice_afinidad"]

    cols = [
        "zona_id", "parroquia_sat", "fuente_margen",
        "poblacion_total", "poblacion_votante",
        "censo_nbi_pobreza_pct", "tasa_desempleo_pea",
        "censo_edad_15_29_pct", "censo_hombres_pct",
        "joven_hombre_pct", "joven_mujer_pct", "joven_pobre_pct", "joven_no_pobre_pct",
        "margen_usado", "indice_afinidad", "e_votos_afines",
    ]
    result = zones[cols].sort_values("e_votos_afines", ascending=False).reset_index(drop=True)

    out_path = OUT_DIR / "zonas_dmq_oportunidad.csv"
    result.to_csv(out_path, index=False, encoding="utf-8")

    summary = (
        result.groupby("fuente_margen")
        .agg(zonas=("zona_id", "count"), poblacion_votante=("poblacion_votante", "sum"), e_votos_afines=("e_votos_afines", "sum"))
        .reset_index()
    )
    summary_path = OUT_DIR / "zonas_dmq_resumen_por_fuente.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8")

    print(f"Zonas censales en DMQ: {len(result)}")
    print(f"  -> en las 33 parroquias rurales/suburbanas (margen real directo): {(result['fuente_margen']=='real_parroquia').sum()}")
    print(f"  -> en el nucleo urbano, margen real heredado via barrio CNE: {(result['fuente_margen']=='real_barrio_cne').sum()}")
    print(f"  -> en el nucleo urbano, sin crosswalk -> modelo predicho cruzado: {(result['fuente_margen']=='modelo_predicho_cruzado').sum()}")
    print()
    print("Top 20 zonas por E[votos afines]:")
    print(result.head(20).to_string(index=False))
    print(f"\nTabla completa: {out_path}")
    print(f"Resumen por fuente de margen: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
