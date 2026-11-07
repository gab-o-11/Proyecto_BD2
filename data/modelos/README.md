# Vocabularios multimedia entrenados

Estos modelos se distribuyen con el repositorio: no es necesario entrenarlos de
nuevo para cuantizar descriptores. Los datasets, caches y checkpoints no se versionan.

| Carpeta | Entrada | Extractor | Centroides | Componentes por centroide |
|---|---|---|---|---|
| `fotos/` | Imagen | `SiftExtractor()` | 256 | 128 |
| `audio_msd/` | HDF5 de Million Song Dataset | `MsdTimbreExtractor()` | 256 | 12 |
| `audio_mfcc/` | MP3/WAV de FMA Small | `MfccExtractor` configurado desde `training.json` | 256 | 12 |

Cada carpeta contiene `vocabulary.json` (centroides e identificadores) y
`training.json` (configuracion del extractor, muestra y metricas). Los informes
conservan las rutas del equipo de entrenamiento como procedencia; no se necesitan
esas rutas para cargar el vocabulario. Consulta `result.iterations` y
`result.converged` en cada informe para conocer el criterio de parada alcanzado.
`result.history` guarda por iteración la inercia de los centros de entrada, el
desplazamiento maximo y los grupos vacios (solo en entrenamientos posteriores a
este campo).

Para analizar el aprendizaje, la carpeta de entrenamiento (no versionada) tambien
deja `snapshots/iter_NNN.npy` con los centroides tras cada iteracion (`iter_000`
es la inicializacion K-Means++) y `sample-files.npy`, que indica, para cada fila
de `sample.npy`, su indice en `dataset.files` de `run.json`.

Las imagenes usan SIFT con lado maximo 512 y hasta 500 puntos, sin normalizacion
adicional. Audio MSD utiliza `analysis/segments_timbre`, sin normalizacion adicional.
Los HDF5 no contienen grabaciones: este vocabulario no admite directamente MP3/WAV
ni es intercambiable con MFCC extraidos con librosa. Para grabaciones reales usa
`audio_mfcc`: 22050 Hz, 13 coeficientes descartando c0, ventanas 2048, salto 512
(75 % de overlap), maximo 30 segundos y sin normalizacion adicional. El pipeline
reconstruye estos parametros desde el informe, sin reentrenar.

## Cargar los modelos

En un entorno con NumPy, OpenCV, h5py y librosa, ejecuta desde la raiz:

```python
from pathlib import Path
import sys
sys.path.insert(0, str(Path("backend").resolve()))

from engine.multimedia.quantization import load_vocabulary
from engine.multimedia.local_features import SiftExtractor
from engine.multimedia.audio_features import MsdTimbreExtractor
from engine.multimedia.extract_features import ExtractFeatures

fotos = ExtractFeatures(
    SiftExtractor(), load_vocabulary("data/modelos/fotos/vocabulary.json")
)
audio = ExtractFeatures(
    MsdTimbreExtractor(), load_vocabulary("data/modelos/audio_msd/vocabulary.json")
)
```

Usa `histograma(ruta)` con el extractor correspondiente. Los histogramas, el modelo
TF-IDF y el indice deben prepararse por coleccion; no estan incluidos en estos
archivos. La API registra automaticamente los vocabularios disponibles mediante
`FeaturePipeline`; la carga de cada tabla se solicita por su endpoint de features.
No se debe entrenar durante una consulta. Si cambias un vocabulario, reconstruye
sus histogramas, TF-IDF e indices para conservar la compatibilidad.

Para volver a entrenar, consulta los lanzadores `scripts/entrenar_fotos.ps1` y
`scripts/entrenar_audio.ps1`. La integracion con el servidor se explica en
[Pipeline multimedia](../../docs/13-multimedia.md).


Para usar tambien el vocabulario MFCC, utiliza el ensamblaje del motor:

```python
from engine.multimedia.pipeline import FeaturePipeline
pipeline = FeaturePipeline("data/multimedia", "data/modelos")
print(pipeline.modelos())
```

Las rutas de MP3 en las tablas son relativas a `data/multimedia` (`BD2_MULTIMEDIA_DIR`), por ejemplo
`audio/fma_small/000/000002.mp3`. Cada tabla debe ajustar y guardar su TF-IDF antes
de consultar. El vector final tiene 256 componentes; no debe mezclarse con los
vectores de otra modalidad aunque tenga la misma dimension.
