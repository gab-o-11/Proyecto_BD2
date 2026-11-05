# Vocabularios multimedia entrenados

Estos modelos se distribuyen con el repositorio: no es necesario entrenarlos de
nuevo para cuantizar descriptores. Los datasets, caches y checkpoints no se versionan.

| Carpeta | Entrada | Extractor | Centroides | Componentes por centroide |
|---|---|---|---|---|
| `fotos/` | Imagen | `SiftExtractor()` | 256 | 128 |
| `audio_msd/` | HDF5 de Million Song Dataset | `MsdTimbreExtractor()` | 256 | 12 |

Cada carpeta contiene `vocabulary.json` (centroides e identificadores) y
`training.json` (configuracion del extractor, muestra y metricas). Los informes
conservan las rutas del equipo de entrenamiento como procedencia; no se necesitan
esas rutas para cargar el vocabulario. Ambos modelos terminaron tras 50 iteraciones
sin alcanzar la tolerancia de convergencia configurada.

Las imagenes usan SIFT con lado maximo 512 y hasta 500 puntos, sin normalizacion
adicional. Audio MSD utiliza `analysis/segments_timbre`, sin normalizacion adicional.
Los HDF5 no contienen grabaciones: este vocabulario no admite directamente MP3/WAV
ni es intercambiable con MFCC extraidos con librosa.

## Cargar los modelos

En un entorno con NumPy, OpenCV y h5py, ejecuta desde la raiz:

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
