"""Ensamblaje de los modelos entrenados para cargar y consultar colecciones.

La extraccion, cuantizacion y TF-IDF viven en sus modulos existentes. Esta capa
solo carga vocabularios y registra los extractores; nunca entrena al consultar.
"""
import logging
from pathlib import Path

from .extract_features import ColeccionesMultimedia
from .quantization import load_vocabulary

logger = logging.getLogger(__name__)


class FeaturePipeline(ColeccionesMultimedia):
    def __init__(self, carpeta, carpeta_modelos):
        super().__init__(str(Path(carpeta).resolve()))
        self.carpeta_modelos = Path(carpeta_modelos).resolve()
        self._modelos = []
        for nombre in ("fotos", "audio_msd"):
            ruta = self.carpeta_modelos / nombre / "vocabulary.json"
            if not ruta.is_file():
                logger.warning("Vocabulario multimedia no disponible: %s", ruta)
                continue
            if nombre == "fotos":
                from .local_features import SiftExtractor
                extractor = SiftExtractor()
            else:
                from .audio_features import MsdTimbreExtractor
                extractor = MsdTimbreExtractor()
            vocabulario = load_vocabulary(ruta)
            self.registrar(extractor, vocabulario)
            self._modelos.append({
                "name": nombre,
                "descriptor_id": extractor.descriptor_id,
                "vocabulary_id": vocabulario.vocabulary_id,
                "dimension": vocabulario.size,
                "descriptor_dimension": vocabulario.dimension,
            })

    def modelos(self):
        """Configuracion necesaria para elegir un extractor al cargar una tabla."""
        return [dict(modelo) for modelo in self._modelos]
