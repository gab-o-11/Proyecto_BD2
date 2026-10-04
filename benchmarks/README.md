# Benchmarks del minigestor

[benchmark.ipynb](benchmark.ipynb) integra almacenamiento, índices relacionales,
algoritmos externos, resultados del R-Tree en disco y capturas de la interfaz.
Incluye pruebas de regresión y directas, consultas con recuperación de filas,
gráficas con unidades explícitas y análisis calculado desde la ejecución.

## Ejecutar

Desde la raíz del proyecto, con un entorno Python que tenga el backend y las
dependencias del notebook. En esta máquina se utiliza el entorno micromamba `bd2`;
`backend/.venv` no contiene las dependencias de Jupyter y gráficas.

```sh
rtk proxy micromamba run -n bd2 python -m jupyter nbconvert \
  --to notebook --execute --inplace benchmarks/benchmark.ipynb \
  --ExecutePreprocessor.kernel_name=bd2 \
  --ExecutePreprocessor.timeout=2400
```

Para otro entorno, instalar las dependencias en ese entorno y usar su kernel:

```sh
rtk proxy python -m pip install -r benchmarks/requirements.txt
rtk proxy python -m ipykernel install --user --name bd2 --display-name "Python 3 (bd2)"
```

Los CSV de entrada se generan automáticamente cuando faltan. Se valida su
contenido y se conservan hashes SHA-256; archivos existentes no se sobrescriben.
Parámetros al inicio: `SIZES`, `REPEATS`, `SEED`, `PAGE_SIZE` y `BLOCK_FACTOR`.
La batería completa puede tardar decenas de minutos. Para una comprobación corta,
usar `SIZES = (1_000,)` y `REPEATS = 1`, y restaurarlos antes de publicar resultados.

El notebook importa los resultados espaciales ya guardados. Para actualizarlos
primero, seguir [README_espacial.md](README_espacial.md). Esa ejecución requiere
PostgreSQL y crea un clúster privado temporal; el notebook no lo inicia.

## Qué se compara

- Heap y secuencial: carga con inserciones individuales, igualdad sin índice,
  espacio y compactación del secuencial después de borrar 20 %.
- B+ agrupado, B+ no agrupado y Hash: construcción sobre datos existentes,
  igualdad de referencias y filas, rangos de 0,1/1/10 %, orden por clave y
  tres ciclos de borrado/reinserción de 10 % con datos e índice.
- Hash responde rangos con barrido y orden con barrido + mezcla externa;
  estas operaciones no se presentan como capacidades nativas del índice.
- ORDER BY, GROUP BY y JOIN externos, contrastados con referencia en RAM
  sin el mismo presupuesto de memoria.
- Búsqueda secuencial, R-Tree paginado con STR y PostgreSQL GiST, mediante
  los CSV, gráficas y planes de la corrida espacial.

Cada medición valida resultados fuera del cronómetro. Un fallo detiene la corrida
y conserva el error en el notebook. Las cargas tienen el mismo límite de 300 s,
comprobado cada 1 000 inserciones; no se extrapolan corridas incompletas.

## Evidencia

`relational_results/` conserva CSV crudo/resumen, pruebas, entorno, hashes del
motor y de los datos, análisis y figuras. Las consultas usan ms por consulta;
las escrituras, µs por registro; carga/construcción/orden, segundos completos.
Las medianas se acompañan de bandas mínimo–máximo, sin inferencia estadística.
El espacio inicial se separa en datos e índice; el CSV crudo vuelve a medirlo
después de cada lote de modificaciones.

Las páginas instrumentadas son accesos lógicos, no E/S física. Se usa la caché
disponible del SO, sin vaciarla ni forzar `fsync`, sin consultas concurrentes y
con registros pequeños. La generación de datos, las copias para aislar cada
índice y las validaciones quedan fuera del tiempo medido. Ejecutar en un equipo
sin otras cargas mejora la estabilidad de los tiempos.

Las capturas de `documents/visual_spatial/` son evidencia funcional sobre tres
puntos de prueba; no son mediciones sobre los datasets del benchmark.
