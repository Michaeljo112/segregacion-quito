# Datos — procedencia y cómo regenerar lo que no está versionado

## Qué sí está en este repositorio

| Archivo | Qué es | Fuente |
|---|---|---|
| `Primera-Vuelta.sav`, `Segunda-Vuelta.sav` | Microdato crudo de resultados electorales por junta, primera y segunda vuelta presidencial 2025 (usado para extraer el margen real de las 32 parroquias urbanas del núcleo de Quito) | [CNE](https://www.cne.gob.ec/), datos públicos |
| `diccionario_parroquias.xlsx` | Cruce de codificación de parroquias | Elaboración propia sobre codificación INEC/CNE |
| `PiliticalCompass.xlsx` | Codebook de clasificación ideológica (ver repositorio hermano `voto-territorial-ecuador`, Apéndice A) | Codificación propia |
| `model/parroquia_clusters_pc_kmeans_k5.csv` | Tipología territorial nacional (clustering parroquial K-Means k=5) — insumo para resolver las 33 parroquias rurales/suburbanas de Quito | Repositorio hermano [voto-territorial-ecuador](https://github.com/Michaeljo112/voto-territorial-ecuador) — mismo pipeline, ver ese repo para regenerarlo |
| `model/census_indicator_features.csv` | Catálogo censal completo (1.057 indicadores) usado en la extrapolación de `indice_afinidad` | Ídem — repositorio hermano `voto-territorial-ecuador` |
| `maps/sectores_raw/extracted/dmq_sectores.gpkg` | Cartografía disuelta de sectores censales a nivel de zona para el DMQ (751 zonas) | Derivado de `CapaSectores.zip` (INEC), ver regeneración abajo |
| `../output/*.csv` | Las 9 salidas limpias del pipeline zona/sector (ver README.md principal para la lista y qué se excluyó) | Generadas por `scripts/`, ver abajo |

## Qué NO está versionado y por qué

### 1. Microdato censal a nivel sector (`data/censo_sector/`)

No se versiona: ~600 MB comprimido, regenerable de fuente pública INEC. Regenerar:

```bash
mkdir -p data/censo_sector/raw data/censo_sector/processed
curl -L -o data/censo_sector/raw/BDD_CPV2022_SECT_CSV.zip \
  https://www.ecuadorencifras.gob.ec/documentos/web-inec/bd-censo/sector/BDD_CPV2022_SECT_CSV.zip

cd data/censo_sector/raw
echo "I01;I02;I03;I04;I05;P02;P03;ESCOLA;ANALF;CONDACT1;NBI" > ../processed/poblacion_dmq.csv
unzip -p BDD_CPV2022_SECT_CSV.zip "1.2 BDD_CPV_2022_SECTOR_CSV/CPV_2022_Poblacion_Sector.csv" | \
  awk -F';' 'NR>1 && $1=="17" && $2=="01" {print $1";"$2";"$3";"$4";"$5";"$10";"$11";"$83";"$84";"$87";"$90}' \
  >> ../processed/poblacion_dmq.csv
```

Fuente: [censoecuador.gob.ec](https://www.censoecuador.gob.ec/data-censo-ecuador/#bddvdos) (nivel sector, formato CSV). El diccionario de variables se descarga del mismo portal.

Nota: `scripts/build_zonal_census_features.py` usa un set más amplio de esta misma fuente (tablas Población/Vivienda/Hogar) — no hay un script separado que produzca ese set ampliado; requiere adaptar el filtro `awk` de arriba a las columnas adicionales (ver docstring del script).

### 2. Cartografía de sectores INEC cruda (`CapaSectores.zip`) y sectores_anonimizados.gpkg

No se versiona (el zip descargado y el gpkg completo nacional son grandes); sí se versiona el recorte ya extraído a DMQ (`dmq_sectores.gpkg`, 36 MB). Para regenerar desde cero:

```bash
mkdir -p data/maps/sectores_raw
curl -L -o data/maps/sectores_raw/CapaSectores.zip \
  https://www.ecuadorencifras.gob.ec/documentos/web-inec/capa/CapaSectores.zip
python -c "import zipfile; zipfile.ZipFile('data/maps/sectores_raw/CapaSectores.zip').extract('sectores_anonimizados.gpkg', 'data/maps/sectores_raw/extracted')"
python -c "
import geopandas as gpd
gdf = gpd.read_file('data/maps/sectores_raw/extracted/sectores_anonimizados.gpkg', layer='sectores_anonimizados_indicadores_censo_2022', where=\"canton='1701'\")
gdf.to_file('data/maps/sectores_raw/extracted/dmq_sectores.gpkg', driver='GPKG')
"
```

### 3. Cartografía de parroquias CNE (`data/maps/CNE_parroquias_desde2013.shp`)

No se versiona: ~215 MB, excede el límite de 100 MB de GitHub. Es la cartografía de parroquias electorales del CNE (incluye las 65 parroquias de Quito con desagregación urbana desde 2013), necesaria para `scripts/name_zonas.py`. Fuente más probable: **[cne.gob.ec/download/parroquias-2021](https://www.cne.gob.ec/download/parroquias-2021/)** (descarga oficial de cartografía de parroquias del CNE). El archivo original de este pipeline se llama `CNE_parroquias_desde2013.shp` — **verificar que la versión descargada de ese enlace coincide** (mismo conteo de 65 parroquias urbanas/rurales de Quito) antes de depender de él; si el CNE actualizó la capa, los IDs de parroquia podrían no ser idénticos a los usados originalmente.

### 4. Variables satelitales por zona (VIIRS/NDVI/MNDWI)

`scripts/build_zonal_satellite_features.py` requiere una cuenta de [Google Earth Engine](https://earthengine.google.com/) autenticada (`earthengine-api`, `ee.Authenticate()`) — no es un dato descargable, es una consulta en vivo. La salida ya está incluida en `../output/zonas_dmq_satelital.csv`.

## Pipeline completo (orden — importante, ver comentarios)

```bash
pip install -r requirements.txt

# 1. Margen real del núcleo urbano (usa data/Primera-Vuelta.sav, Segunda-Vuelta.sav,
#    diccionario_parroquias.xlsx, PiliticalCompass.xlsx — ya incluidos)
python scripts/build_urban_real_margin.py

# 2. Nombre de barrio por zona (requiere dmq_sectores.gpkg, ya incluido, y
#    CNE_parroquias_desde2013.shp, ver sección 3 arriba)
python scripts/name_zonas.py

# 3. Zona por zona: hereda el margen real vía el cruce del paso 2
#    (requiere data/censo_sector/processed/poblacion_dmq.csv, ver sección 1 arriba;
#    y data/model/parroquia_clusters_pc_kmeans_k5.csv, data/model/census_indicator_features.csv,
#    ya incluidos desde el repo hermano)
python scripts/build_zonal_opportunity.py

# 4. Segundo ranking independiente del margen electoral
python scripts/build_structural_index.py

# 5. Variables censales y satelitales extendidas por zona
python scripts/build_zonal_census_features.py     # requiere paso 1 de la sección "censo_sector"
python scripts/build_zonal_satellite_features.py  # requiere cuenta Google Earth Engine

# 6. Clustering de perfiles socioeconómicos de zona
python scripts/cluster_zonal_features.py
```

Todas las salidas ya están en `../output/` — no hace falta re-ejecutar nada para verificar las tablas del paper, solo para regenerar desde la fuente cruda.

**No incluido, deliberadamente:**
- `build_opportunity_map.py` y `build_priority_list.py` (y sus salidas) — específicos de la carrera municipal 2026, fuera del enfoque académico del paper. Ver README.md principal.
- `build_sector_opportunity.py` y su salida `sectores_dmq_oportunidad.csv` — análisis alternativo a nivel de sector (~7.200 unidades) que usa el modelo predictivo de margen para el 66% de los sectores; el paper reporta clustering a nivel de zona (751 unidades), no este enfoque, así que queda fuera de alcance (confirmado por el autor, 2026-09-10).
