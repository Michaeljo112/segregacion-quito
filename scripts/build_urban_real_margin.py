"""Real presidencial-2025 results for Quito's ~33 urban parishes (CNE, not INEC).

FINDING (2026-09-08): the rest of this repo's pipeline treats the urban core
of Quito ("Quito", parish 50 in the INEC/DPA administrative geography used by
`datos22.xlsx` and `diccionario_parroquias.xlsx`) as having no electoral
result. That is true of the INEC/DPA geography -- but it is NOT true of the
raw CNE source data (`data/Primera-Vuelta.sav`, `data/Segunda-Vuelta.sav`).
CNE runs its own, finer electoral zoning for Quito's urban area: 33 named
"parroquias urbanas" (Centro Historico, La Mariscal ["Mariscal Sucre"],
Cotocollao, Chillogallo, Quitumbe, Solanda, Carcelen, etc.), each with its
own PARROQUIA_CODIGO and full presidencial results, first and second round.

`diccionario_parroquias.xlsx` -- the CODPRO/CODCAN/CODPAR -> ADM3_PCODE
crosswalk this repo's national pipeline joins electoral results against --
only has rows for the 33 RURAL/SUBURBAN parishes of canton Quito (Conocoto,
Tumbaco, Calderon, ...). It has no rows for the 33 URBAN CNE parish codes,
because those don't correspond to an official INEC/DPA parish (INEC's
census geography still treats urban Quito as a single parish). So when
`scripts/build_parish_model_dataset.py` left-joins electoral results onto
the satellite base (`datos22.xlsx`, one row per DPA parish) by ADM3_PCODE,
the 33 urban CNE parishes' votes have no ADM3_PCODE to attach to and are
silently dropped -- NOT because CNE doesn't publish them (it does), but
because this repo's crosswalk never mapped them.

This script bypasses that crosswalk gap: it reads the raw CNE microdata
directly, keeps only the presidencial rows for canton Quito (17/60) whose
PARROQUIA_CODIGO is NOT one of the 33 already resolved via
`diccionario_parroquias.xlsx`, and aggregates first- and second-round
results per named urban parish -- giving REAL (not predicted) margins for
the part of Quito that `informe_estrategico.md` SS5-SS7 previously had to
model.

These 33 urban parishes are a CNE electoral zoning, not an INEC census
parish -- there is no `ADM3_PCODE` for them and no satellite/census row in
`datos22.xlsx` to attach directly. They get a synthetic id instead
(`URB-<PARROQUIA_CODIGO>`). Matching them to the 751 census zonas from
`build_zonal_opportunity.py` would need a spatial crosswalk between CNE's
urban parish boundaries and INEC's census zona boundaries, which does not
exist in this repo yet -- see the printed note at the end of `main()`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyreadstat

ROOT = Path(__file__).resolve().parents[2]
PRIMERA_SAV = ROOT / "data" / "Primera-Vuelta.sav"
SEGUNDA_SAV = ROOT / "data" / "Segunda-Vuelta.sav"
DICCIONARIO = ROOT / "data" / "diccionario_parroquias.xlsx"
POLITICAL_COMPASS = ROOT / "data" / "PiliticalCompass.xlsx"
OUT_DIR = Path(__file__).resolve().parents[1] / "output"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

QUITO_PROVINCIA = 17
QUITO_CANTON = 60


def _load_round(path: Path) -> pd.DataFrame:
    df, _meta = pyreadstat.read_sav(path, apply_value_formats=True)
    # pyreadstat returns labelled columns as pandas Categorical with the FULL
    # national category set. Left as categorical, a later groupby (even with
    # the frame filtered down to 66 rows) reintroduces every unobserved
    # national category into the group index -- decategorize up front.
    for col in df.select_dtypes(include=["category", "object"]).columns:
        df[col] = df[col].astype(str).str.strip("'\" ")
    # Label text for this dignidad differs between the two files
    # ("PRESIDENTE Y VICEPRESIDENTE" vs "PRESIDENTA/E Y VICEPRESIDENTA/E").
    df = df[df["DIGNIDAD_NOMBRE"].str.contains("PRESIDENT", case=False, na=False)].copy()
    df = df[(df["PROVINCIA_CODIGO"] == QUITO_PROVINCIA) & (df["CANTON_CODIGO"] == QUITO_CANTON)].copy()
    return df


def _urban_parish_codes() -> set[int]:
    """PARROQUIA_CODIGO values for canton Quito NOT already covered by the
    existing diccionario_parroquias.xlsx crosswalk (i.e. the 33 urban ones)."""
    dic = pd.read_excel(DICCIONARIO)
    known = set(dic[(dic["CODPRO"] == QUITO_PROVINCIA) & (dic["CODCAN"] == QUITO_CANTON)]["CODPAR"].astype(int))

    df = _load_round(PRIMERA_SAV)
    df = df[(df["PROVINCIA_CODIGO"] == QUITO_PROVINCIA) & (df["CANTON_CODIGO"] == QUITO_CANTON)]
    all_codes = set(df["PARROQUIA_CODIGO"].astype(int))

    return all_codes - known


def _aggregate_sufragantes_nulos_blancos(df: pd.DataFrame) -> pd.DataFrame:
    """Mirrors PrimeraVuelta.ipynb's logic: mean per (parish, junta_sexo)
    (SUFRAGANTES/NULOS/BLANCOS repeat per-candidate row, so mean recovers the
    true total), summed votes, then summed across junta_sexo to parish level."""
    by_junta = df.groupby(["PARROQUIA_CODIGO", "PARROQUIA_NOMBRE", "JUNTA_SEXO"], as_index=False).agg(
        sufragantes=("SUFRAGANTES", "mean"),
        nulos=("NULOS", "mean"),
        blancos=("BLANCOS", "mean"),
    )
    by_parish = by_junta.groupby(["PARROQUIA_CODIGO", "PARROQUIA_NOMBRE"], as_index=False).agg(
        sufragantes=("sufragantes", "sum"),
        nulos=("nulos", "sum"),
        blancos=("blancos", "sum"),
    )
    return by_parish


def build_round1(urban_codes: set[int]) -> pd.DataFrame:
    df = _load_round(PRIMERA_SAV)
    df = df[df["PARROQUIA_CODIGO"].astype(int).isin(urban_codes)].copy()

    base = _aggregate_sufragantes_nulos_blancos(df)
    base["nulos_blancos_v1_pct"] = (base["nulos"] + base["blancos"]) / base["sufragantes"]
    base["nulos_blancos_v1_n"] = (base["nulos"] + base["blancos"]).round()

    # Political Compass classification shares, mirroring PrimeraVuelta.ipynb.
    pc = pd.read_excel(POLITICAL_COMPASS)
    dfc = df.merge(pc[["CANDIDATO_NOMBRE", "Separación"]], on="CANDIDATO_NOMBRE", how="left")
    votos_validos = df.groupby("PARROQUIA_CODIGO")["VOTOS"].sum().rename("votos_validos_v1")
    dist = dfc.groupby(["PARROQUIA_CODIGO", "Separación"])["VOTOS"].sum().unstack("Separación").fillna(0)
    dist = dist.div(dist.sum(axis=1), axis=0)  # share of votos validos per ideological class
    dist.columns = [f"pc_{c.strip().lower().replace(' ', '_')}" for c in dist.columns]

    out = base.merge(votos_validos, on="PARROQUIA_CODIGO", how="left")
    out = out.merge(dist, on="PARROQUIA_CODIGO", how="left")
    return out


def build_round2(urban_codes: set[int]) -> pd.DataFrame:
    df = _load_round(SEGUNDA_SAV)
    df = df[df["PARROQUIA_CODIGO"].astype(int).isin(urban_codes)].copy()

    base = _aggregate_sufragantes_nulos_blancos(df)
    votos = df.groupby(["PARROQUIA_CODIGO", "CANDIDATO_NOMBRE"])["VOTOS"].sum().unstack("CANDIDATO_NOMBRE")
    votos_validos = votos.sum(axis=1).rename("votos_validos_v2")
    noboa_pct = (votos["DANIEL NOBOA AZIN"] / votos_validos).rename("elec_v2_noboa_pct")
    luisa_pct = (votos["LUISA GONZALEZ"] / votos_validos).rename("elec_v2_luisa_pct")
    margin = (noboa_pct - luisa_pct).rename("elec_v2_noboa_minus_luisa")

    out = base.merge(votos_validos, on="PARROQUIA_CODIGO", how="left")
    out = out.merge(noboa_pct, on="PARROQUIA_CODIGO", how="left")
    out = out.merge(luisa_pct, on="PARROQUIA_CODIGO", how="left")
    out = out.merge(margin, on="PARROQUIA_CODIGO", how="left")
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    urban_codes = _urban_parish_codes()

    r1 = build_round1(urban_codes)
    r2 = build_round2(urban_codes)

    merged = r1.merge(
        r2.drop(columns=["PARROQUIA_NOMBRE", "sufragantes", "nulos", "blancos"]),
        on="PARROQUIA_CODIGO", how="outer", validate="one_to_one",
    )
    merged["zona_id_cne"] = "URB-" + merged["PARROQUIA_CODIGO"].astype(int).astype(str)
    merged = merged.rename(columns={"PARROQUIA_NOMBRE": "parroquia_urbana_cne", "sufragantes": "sufragantes_v1"})
    merged = merged.sort_values("elec_v2_noboa_minus_luisa", ascending=False).reset_index(drop=True)

    out_path = OUT_DIR / "dmq_nucleo_urbano_margen_real.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8")

    print(f"Parroquias urbanas CNE encontradas (Quito, canton 17/60): {len(urban_codes)}")
    print(f"Con resultado real 1ra y 2da vuelta: {len(merged)}")
    print(f"Sufragantes 2da vuelta, suma nucleo urbano: {merged['votos_validos_v2'].sum() + merged['nulos'].sum() + merged['blancos'].sum():,.0f}")
    print()
    cols = ["parroquia_urbana_cne", "sufragantes_v1", "elec_v2_noboa_pct", "elec_v2_luisa_pct", "elec_v2_noboa_minus_luisa", "nulos_blancos_v1_pct"]
    print(merged[cols].to_string(index=False))
    print(f"\nTabla completa: {out_path}")
    print()
    print(
        "NOTA: estas 33 parroquias son un zonificado electoral del CNE, no una parroquia\n"
        "censal del INEC -- no tienen ADM3_PCODE ni fila propia en datos22.xlsx, y por lo\n"
        "tanto no se pueden fusionar directo con las 751 zonas censales del INEC de\n"
        "build_zonal_opportunity.py sin un cruce espacial (shapefile) entre los limites\n"
        "electorales del CNE y los limites censales del INEC, que este repositorio no\n"
        "tiene todavia. Lo que SI se puede hacer ya: usar el margen real de estas 33\n"
        "parroquias como un segundo nivel de tabla, con nombre de barrio reconocible,\n"
        "reemplazando el promedio predicho del nucleo urbano en las secciones 2, 5, 6 y 7\n"
        "del informe -- ver README de esta carpeta."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
