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

## Parte 3: búsqueda de texto

[parte3.ipynb](parte3.ipynb) compara TF-IDF + coseno y BM25 (índice SPIMI del motor)
con PostgreSQL GIN sobre 1 000, 10 000 y 100 000 documentos y consultas de 1, 3 y
5–7 palabras. Mide construcción, tiempo de consulta, Precision@10, Recall@10, memoria
y disco. El corpus y sus juicios de relevancia salen de
[`data/generate_text.py`](../data/generate_text.py): un documento es relevante si es
del mismo tema que la consulta. Los resultados quedan en `text_results/`.

Requiere PostgreSQL (`initdb`, `pg_ctl`, `pg_buffercache`) y `psycopg2`. Al igual que
`spatial.py`, crea un clúster privado temporal en `/tmp` con socket Unix y sin TCP.

```sh
rtk proxy micromamba run -n bd2 python -m jupyter nbconvert \
  --to notebook --execute --inplace benchmarks/parte3.ipynb \
  --ExecutePreprocessor.kernel_name=bd2 \
  --ExecutePreprocessor.timeout=3600
```

## Parte 4: búsqueda por similitud de imágenes

[parte4.ipynb](parte4.ipynb) compara IVF y HNSW (índices vectoriales del motor sobre
FAISS) con métrica euclidiana y coseno, sobre 1 000, 10 000 y 100 000 imágenes de
Tiny ImageNet con k = 10. Mide la construcción, el tiempo de consulta, el Recall@10
contra la búsqueda exacta del motor y la memoria del índice. Hace un barrido de
`PROBES` y `EF_SEARCH` e incluye una galería de aciertos y errores, además de una
tabla de recomendaciones. Los vectores salen del mismo pipeline que `SIMILAR_TO`:
SIFT, el vocabulario de `data/modelos/fotos` y TF-IDF por colección. Los resultados
quedan en `multimedia_results/`.

Antes hay que descargar el dataset con `python scripts/descargar_tiny_imagenet.py`.
La primera corrida extrae SIFT de las 110 000 imágenes, lo que toma unos minutos
con todos los núcleos. Los histogramas quedan en
`data/generated/tiny_imagenet_sift_histogramas.npz` y se reutilizan si el
manifiesto y el vocabulario no cambiaron.

```sh
rtk proxy micromamba run -n bd2 python -m jupyter nbconvert \
  --to notebook --execute --inplace benchmarks/parte4.ipynb \
  --ExecutePreprocessor.kernel_name=bd2 \
  --ExecutePreprocessor.timeout=3600
```
