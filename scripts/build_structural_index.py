"""A second, independent priority ranking for DMQ zonas: structural profile,
not electoral margin.

Every ranking so far (build_zonal_opportunity.py's `indice_afinidad`, and
`build_urban_real_margin.py`/`name_zonas.py`'s inherited real margin) is
built from ONE signal: the Noboa-Gonzalez presidential runoff margin, real
or heredado. This script builds a second, genuinely independent ranking
from the variables that the *national clustering* (docs/paper_tendencias_
voto_parroquias.md) found actually separate ideological clusters --
poverty (NBI), youth-in-poverty, and unemployment -- WITHOUT touching any
electoral column. It answers a different question than the affinity index:
not "how did this territory vote", but "how much does this territory's own
demographic profile resemble the low-poverty, higher-opportunity archetype
(cluster 2 in the national paper) that empirically correlates with
derecha-liberal alignment nationwide" -- a proxy for opportunity built
before, not from, the vote.

Why these three variables and not the full cluster feature set: the
national paper's clustering also used satellite variables (VIIRS night
lights, NDVI) -- but those only exist at PARISH granularity (`datos22.xlsx`
is one row per parish, built from imagery, not census microdata), and this
script needs to score 751 ZONAS, a finer unit satellite data was never
attached to in this repo. Restricted to what census microdata actually
gives at zona level: `censo_nbi_pobreza_pct` (the single variable the
national paper's cluster profiles differ on most consistently),
`joven_pobre_pct` (not `censo_edad_15_29_pct` alone -- section 6.2 already
showed plain youth share is NOT the driver, youth-IN-poverty is), and
`tasa_desempleo_pea`. All three: lower is structurally closer to the
low-poverty/high-opportunity archetype.

WHAT THIS IS NOT: a second vote forecast. It never touches
`margen_usado`/`indice_afinidad`. Read together with those, it can flag
"disagreement" zonas -- structurally favorable but not (yet) reflected in a
strong real margin, or the reverse -- which is genuinely more informative
than either ranking alone, but the interpretation is directional, not causal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ZONAS = Path(__file__).resolve().parents[1] / "output" / "zonas_dmq_oportunidad.csv"
OUT_DIR = Path(__file__).resolve().parents[1] / "output"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# All three: lower value = structurally closer to the national "cluster 2"
# (low poverty, higher opportunity) archetype -- see module docstring.
STRUCTURAL_VARS = ["censo_nbi_pobreza_pct", "joven_pobre_pct", "tasa_desempleo_pea"]


def build() -> pd.DataFrame:
    z = pd.read_csv(ZONAS)

    z_scores = pd.DataFrame(index=z.index)
    for col in STRUCTURAL_VARS:
        mu, sd = z[col].mean(), z[col].std()
        z_scores[col] = (z[col] - mu) / sd

    # Average the three z-scores, then flip sign (lower raw value -> higher
    # score) and min-max normalize to [0, 1] so it reads on the same scale
    # as indice_afinidad.
    raw = -z_scores.mean(axis=1)
    lo, hi = raw.min(), raw.max()
    z["indice_estructural"] = ((raw - lo) / (hi - lo)).clip(0, 1)

    z["rank_estructural"] = z["indice_estructural"].rank(ascending=False, method="min").astype(int)
    z["rank_afinidad"] = z["indice_afinidad"].rank(ascending=False, method="min").astype(int)
    z["brecha_rank"] = z["rank_afinidad"] - z["rank_estructural"]  # positive: mejor perfil estructural que posicion electoral

    return z


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    z = build()

    corr = z["indice_estructural"].corr(z["indice_afinidad"])
    print(f"Correlacion indice_estructural vs. indice_afinidad (751 zonas): {corr:.3f}")
    print("(esperable positiva, por el mismo patron pobreza<->ideologia del paper nacional -- pero construida sin usar margen electoral)")
    print()

    cols = [
        "zona_id", "parroquia_sat", "poblacion_votante",
        "censo_nbi_pobreza_pct", "joven_pobre_pct", "tasa_desempleo_pea",
        "indice_estructural", "rank_estructural",
        "indice_afinidad", "rank_afinidad", "brecha_rank",
        "fuente_margen",
    ]
    result = z[cols].sort_values("rank_estructural").reset_index(drop=True)
    out_path = OUT_DIR / "zonas_dmq_indice_estructural.csv"
    result.to_csv(out_path, index=False, encoding="utf-8")

    print("Top 15 por indice_estructural (perfil mas parecido al arquetipo de baja pobreza/mayor oportunidad):")
    print(result.head(15).to_string(index=False))
    print()

    # Divergence: structurally favorable (top third) but electorally modest
    # (bottom two-thirds of affinity) -- possible under-the-radar opportunity.
    # Restricted to zonas with a minimally reliable population -- a 3-voter
    # zona hitting 0% on a rate is noise, not signal.
    MIN_VOTANTES = 300
    n = len(result)
    top_estructural = result[(result["rank_estructural"] <= n // 3) & (result["poblacion_votante"] >= MIN_VOTANTES)]
    oportunidad_oculta = top_estructural[top_estructural["rank_afinidad"] > n // 2].sort_values("brecha_rank", ascending=False)
    print(f"Zonas con perfil estructural favorable (top tercio, >= {MIN_VOTANTES} votantes) pero afinidad electoral modesta (mitad inferior): {len(oportunidad_oculta)}")
    print(oportunidad_oculta.head(15).to_string(index=False))
    print(f"\nTabla completa: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
