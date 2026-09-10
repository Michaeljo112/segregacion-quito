# Segregación política y socioeconómica intraurbana en Quito

Repositorio de datos y código reproducible para un artículo académico en preparación sobre la asociación entre estructura socioeconómica y clivaje político a nivel de zona/sector censal (751 zonas, ~7.200 sectores) en el Distrito Metropolitano de Quito. El manuscrito no se publica aquí — este repositorio cubre solo los datos y el pipeline, para que el análisis sea auditable y reproducible independientemente del estado de revisión del artículo.

## Nota sobre el origen del pipeline

Parte del pipeline de datos aquí incluido nace de un ejercicio personal del autor de análisis territorial de la carrera municipal de Quito 2026 — **no un encargo ni trabajo de consultoría contratado**. Aun así, este repositorio **excluye deliberadamente** todo componente de ese pipeline dedicado a priorización o mensaje de campaña — no incluye ranking de prioridad, framing de "oportunidad" para ningún candidato, ni el nombre de campaña o movimiento alguno, por mantener el enfoque académico del trabajo.

**Qué se excluyó específicamente:** los scripts `build_opportunity_map.py` y `build_priority_list.py` del pipeline original, y todas sus salidas — la única parte de ese pipeline que nombra al candidato/movimiento y codifica framing de campaña (p. ej. notas de texto libre tipo "mensaje de seguridad/empleo" o etiquetas de tier tipo "Bastión a consolidar"). También se excluyó `build_sector_opportunity.py` y su salida por ser un análisis alternativo a nivel de sector (modelo predictivo de margen) que no corresponde al enfoque de clustering a nivel de zona de este trabajo. Todo lo que sí está en este repositorio (7 scripts, 9 tablas de salida) fue verificado el 2026-09-10 para confirmar que ninguna columna nombra candidato o campaña.

## Estructura

```
scripts/   — los 7 scripts del pipeline zona/sector verificados como limpios de framing de campaña, más el script del mapa de clusters
output/    — las 9 salidas limpias correspondientes (CSV)
data/      — datos fuente pequeños + dependencias del repo hermano `voto-territorial-ecuador`; ver data/README.md
```

## Cómo reproducir

```bash
pip install -r requirements.txt
```

Ver [data/README.md](data/README.md) para el pipeline completo paso a paso, qué datos ya están incluidos y cómo regenerar lo que no se versiona por tamaño (microdato censal a nivel sector, ~600MB; cartografía de parroquias CNE, ~215MB) o que requiere credenciales propias (variables satelitales vía Google Earth Engine).

Para solo verificar las tablas de este repositorio sin re-ejecutar nada: todas las salidas ya están en `output/`.

## Relación con el repositorio nacional

Este análisis reutiliza dos insumos del repositorio hermano [voto-territorial-ecuador](https://github.com/Michaeljo112/voto-territorial-ecuador) (mismo autor, investigación nacional de tipología territorial): la tipología de clustering parroquial (para resolver las 33 parroquias rurales/suburbanas de Quito) y el catálogo censal completo del INEC. Ambos ya están copiados en `data/model/` de este repositorio; para regenerarlos desde cero, ver ese repositorio.

## Datos

Fuentes públicas: [INEC](https://www.ecuadorencifras.gob.ec/) (censo 2022, a nivel de sector) y [CNE](https://www.cne.gob.ec/) (resultados electorales, cartografía de parroquias). Ver [data/README.md](data/README.md) para procedencia detallada.

## Licencia

El código (scripts/) se distribuye bajo licencia MIT — ver [LICENSE](LICENSE). Los datos redistribuidos en `data/` y `output/` provienen de fuentes públicas de gobierno (INEC, CNE); revisar sus términos de uso antes de reutilizar o redistribuir.

## Cita

Citación formal pendiente hasta contar con versión sometida/publicada.
