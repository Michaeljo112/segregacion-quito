# Segregación política y socioeconómica intraurbana en Quito

Repositorio de datos y código reproducible para estudiar la asociación entre estructura socioeconómica y clivaje político a nivel de zona/sector censal (751 zonas, ~7.200 sectores) en el Distrito Metropolitano de Quito.
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
