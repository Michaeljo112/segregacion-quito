"""Wider census feature set per zona, from tables of `BDD_CPV2022_SECT_CSV.zip`
this repo already had but only used 6 of 92 population columns from.

`build_zonal_opportunity.py` computes indice_afinidad from a narrow set
(sex, age, poverty NBI, unemployment) pulled from the Poblacion_Sector
table alone. This script pulls a wider, curated set from all three
person/dwelling/household tables in the same zip (Poblacion, Vivienda,
Hogar -- Emigracion and Mortalidad are not used here), aggregated to zona
level, for use as INPUT to a richer structural/swing model -- it does not
itself change indice_afinidad or e_votos_afines.

Variables, and why each was picked (see `data/censo_sector/raw/
DICCIONARIO_BDD_SECTOR.xlsx` for the full catalog of ~180 columns this
still leaves on the table):

  Poblacion (person-level):
    - P11R etnia -- indigena/afro/montubio/mestizo/blanco/otro. Ecuadorian
      correismo has an identifiable ethnic base; this repo's models so far
      have no ethnicity variable at all.
    - P17R nivel de instruccion -- bucketed to "educacion superior o mas"
      (tecnica/tecnologica superior, universidad, maestria, PHD).
    - P2102 uso de internet (ultimos 3 meses) -- literally where a digital
      campaign (redes, WhatsApp) reaches people and where it doesn't.
    - ANALF_DIG analfabetismo digital -- inverse framing of the same thing.
    - DFUNC dificultad funcional permanente (discapacidad).
    - GRUPO1 grupo de ocupacion -- bucketed to "directivo/profesional"
      (grupos 1-3) vs. "elemental/manual" (grupos 6-9), a class proxy finer
      than the unemployment rate alone.

  Vivienda (dwelling-level, filtered to V0201R==1 "Ocupada"):
    - V09 agua por tuberia dentro de la vivienda.
    - V11 servicio higienico conectado a red publica de alcantarillado.
    - DEF_HAB deficit habitacional (cualitativo o cuantitativo).

  Hogar (household-level):
    - H09 tenencia de vivienda -- bucketed to "propia" (totalmente pagada,
      pagandola, o por herencia/donacion) vs. "arrendada u otra". Owners
      and renters are a classic political-behavior split this repo never
      had a variable for.
    - H1004 internet fijo en el hogar.
    - H1005 dispone de computadora.
    - H1011 dispone de automovil o camioneta.
    - HAC hacinamiento.

All three tables carry I03/I04/I05 directly -- no person->hogar->vivienda
join is needed to reach zona level, each table is aggregated independently
and merged on zona_id.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SECTOR_DIR = Path(__file__).resolve().parents[2] / "data" / "censo_sector" / "processed"
POBLACION = SECTOR_DIR / "poblacion_dmq_extended.csv"
VIVIENDA = SECTOR_DIR / "vivienda_dmq.csv"
HOGAR = SECTOR_DIR / "hogar_dmq.csv"
OUT_DIR = Path(__file__).resolve().parents[1] / "output"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EDUCACION_SUPERIOR = {8, 9, 10, 11}
OCUPACION_DIRECTIVA = {1, 2, 3}
OCUPACION_ELEMENTAL = {6, 7, 8, 9}
ETNIA_LABELS = {1: "indigena", 2: "afro", 3: "montubio", 4: "mestizo", 5: "blanco", 6: "otro"}


def _zona_id(df: pd.DataFrame) -> pd.Series:
    return df["I03"].astype(str) + "-" + df["I04"].astype(str)


def poblacion_features() -> pd.DataFrame:
    df = pd.read_csv(POBLACION, sep=";", dtype=str)
    for col in ["P11R", "P17R", "P2101", "P2102", "DFUNC", "ANALF_DIG", "GRUPO1"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["zona_id"] = _zona_id(df)

    g = df.groupby("zona_id")
    out = g.agg(
        censo_internet_pct=("P2102", lambda s: (s == 1).mean()),
        censo_analf_digital_pct=("ANALF_DIG", lambda s: (s == 1).mean()),
        censo_discapacidad_pct=("DFUNC", lambda s: (s == 1).mean()),
        censo_educ_superior_pct=("P17R", lambda s: s.isin(EDUCACION_SUPERIOR).mean()),
        censo_ocupacion_directiva_pct=("GRUPO1", lambda s: s.isin(OCUPACION_DIRECTIVA).mean()),
        censo_ocupacion_elemental_pct=("GRUPO1", lambda s: s.isin(OCUPACION_ELEMENTAL).mean()),
    ).reset_index()

    etnia = df.dropna(subset=["P11R"]).groupby("zona_id")["P11R"].value_counts(normalize=True).unstack(fill_value=0)
    etnia.columns = [f"censo_etnia_{ETNIA_LABELS.get(int(c), c)}_pct" for c in etnia.columns]
    out = out.merge(etnia.reset_index(), on="zona_id", how="left")
    return out


def vivienda_features() -> pd.DataFrame:
    df = pd.read_csv(VIVIENDA, sep=";", dtype=str)
    for col in ["V09", "V11", "V12", "V0201R", "DEF_HAB"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["V0201R"] == 1]  # occupied dwellings only -- unoccupied ones have no service data
    df["zona_id"] = _zona_id(df)

    g = df.groupby("zona_id")
    return g.agg(
        censo_agua_red_pct=("V09", lambda s: (s == 1).mean()),
        censo_alcantarillado_pct=("V11", lambda s: (s == 1).mean()),
        censo_electricidad_pct=("V12", lambda s: (s == 1).mean()),
        censo_deficit_habitacional_pct=("DEF_HAB", lambda s: s.isin([2, 3]).mean()),
    ).reset_index()


def hogar_features() -> pd.DataFrame:
    df = pd.read_csv(HOGAR, sep=";", dtype=str)
    for col in ["H09", "H1004", "H1005", "H1011", "HAC"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["zona_id"] = _zona_id(df)

    g = df.groupby("zona_id")
    return g.agg(
        censo_vivienda_propia_pct=("H09", lambda s: s.isin([1, 2, 3]).mean()),
        censo_internet_fijo_pct=("H1004", lambda s: (s == 1).mean()),
        censo_computadora_pct=("H1005", lambda s: (s == 1).mean()),
        censo_auto_pct=("H1011", lambda s: (s == 1).mean()),
        censo_hacinamiento_pct=("HAC", lambda s: (s == 1).mean()),
    ).reset_index()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not (POBLACION.exists() and VIVIENDA.exists() and HOGAR.exists()):
        raise SystemExit("Faltan poblacion_dmq_extended.csv / vivienda_dmq.csv / hogar_dmq.csv en data/censo_sector/processed/")

    pob = poblacion_features()
    viv = vivienda_features()
    hog = hogar_features()

    result = pob.merge(viv, on="zona_id", how="outer").merge(hog, on="zona_id", how="outer")

    out_path = OUT_DIR / "zonas_dmq_features_extended.csv"
    result.to_csv(out_path, index=False, encoding="utf-8")

    print(f"Zonas con features extendidas: {len(result)}")
    print(f"Variables nuevas: {len(result.columns) - 1}")
    print()
    print("Promedio DMQ de cada variable nueva:")
    print(result.drop(columns="zona_id").mean(numeric_only=True).sort_values(ascending=False).to_string())
    print(f"\nTabla completa: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
