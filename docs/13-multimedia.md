# Pipeline multimedia

El ensamblaje vive en `backend/engine/multimedia/pipeline.py`. `FeaturePipeline`
reutiliza `ColeccionesMultimedia`: carga una vez los vocabularios entrenados y
registra SIFT para imagenes y el lector de timbre MSD para audio HDF5. La API lo
crea al arrancar y entrega `pipeline.vectorizar` al ejecutor SQL.

```text
Preparacion de una tabla:
filas con rutas -> extractor -> palabras -> histogramas -> ajustar TF-IDF
    -> guardar vectores y TF-IDF de la coleccion -> crear IVF/HNSW

Consulta por archivo:
archivo -> mismo extractor y vocabulario -> histograma -> TF-IDF guardado
    -> indice de la tabla -> recuperar filas y scores
```

No se entrena K-Means ni se recalcula IDF durante una consulta. Cada tabla usa su
propio TF-IDF. No se deben mezclar vocabularios de fotos y audio aunque ambos
produzcan histogramas de 256 componentes.

## Configuracion

- `BD2_MODELS_DIR`: carpeta de vocabularios; por defecto `data/modelos` del proyecto.
- `BD2_MULTIMEDIA_DIR`: carpeta que contiene los archivos consultables; por defecto
  `data/datasets` del proyecto. Las rutas de las filas y consultas son relativas a ella.
- `BD2_DATA_DIR`: catalogo y almacenamiento; por defecto `data/runtime`.

El inicio carga `fotos/vocabulary.json` y `audio_msd/vocabulary.json`. Un vocabulario
incompatible o corrupto produce un error; uno ausente se registra como advertencia
y esa modalidad no esta disponible. No se recorren ni vectorizan datasets al arrancar.

Con el entorno de entrenamiento ya preparado, instala las dependencias del backend:

```powershell
.\.venv-entrenamiento\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv-entrenamiento\Scripts\python.exe -m uvicorn api.main:app --app-dir backend
```

## Usar el flujo

1. `GET /api/multimedia/models` devuelve los modelos disponibles, sus `descriptor_id`
   y la dimension del vector final. Los valores predeterminados son:
   - fotos: `sift:gray:max512:nf500`, VECTOR(256).
   - audio: `msd:segments_timbre:12:raw:v1`, VECTOR(256).
2. Crea una tabla e inserta rutas mediante `POST /api/query`, cuyo cuerpo es
   `{"sql": "..."}`. Por ejemplo, con las fotos locales:

```sql
CREATE TABLE imagenes (id INT PRIMARY KEY, ruta VARCHAR(200), v VECTOR(256));
INSERT INTO imagenes (id, ruta) VALUES
(1, 'imagenes/101_ObjectCategories/accordion/image_0001.jpg'),
(2, 'imagenes/101_ObjectCategories/accordion/image_0002.jpg');
```

3. `POST /api/tables/imagenes/features` con este JSON extrae los descriptores,
   ajusta TF-IDF a esas filas, guarda los vectores y persiste TF-IDF:

```json
{"path_column": "ruta", "descriptor_id": "sift:gray:max512:nf500"}
```

4. Crea el indice y consulta mediante `/api/query`:

```sql
CREATE INDEX idx_imagenes ON imagenes (v) USING HNSW WITH (METRIC=cosine);
SELECT id, ruta, SIMILARITY_SCORE() AS score FROM imagenes
WHERE SIMILAR_TO('imagenes/101_ObjectCategories/accordion/image_0001.jpg', k=2)
USING HNSW WITH METRIC=cosine ORDER BY score DESC;
```

Para audio, crea otra tabla VECTOR(256), inserta rutas como
`audio/MillionSongSubset/A/A/A/TRAAAAW128F429D538.h5` y carga sus caracteristicas con
`descriptor_id` igual a `msd:segments_timbre:12:raw:v1`. Puedes crear IVF con
`CREATE INDEX idx_audio ON audios (v) USING IVF WITH (METRIC=cosine, LISTS=1);`
para una coleccion pequena. Escoge mas listas al trabajar con colecciones grandes.

El dataset MSD contiene descriptores precalculados, no grabaciones: este modelo
no permite consultar MP3/WAV. Para eso hace falta otro extractor y vocabulario MFCC.
El dataset debe estar disponible en el servidor aunque los vocabularios vengan en Git.
Cuando agregues o cambies archivos/filas, vuelve a cargar las caracteristicas de la
tabla para recalcular TF-IDF e indices. Cambiar de vocabulario exige el mismo proceso.
No se ha anadido un control de carga en la interfaz: estas operaciones usan la API.

## Verificacion

Desde `backend/`:

```powershell
..\.venv-entrenamiento\Scripts\python.exe -B -m engine.multimedia.test_pipeline
```

Prueba ambos vocabularios con imagenes y HDF5 sinteticos, carga por API, busqueda
SEQ/IVF/HNSW, rutas fuera de la carpeta permitida, recarga desde disco y preservacion
de los vocabularios. No requiere descargar los datasets completos ni reentrenar.
