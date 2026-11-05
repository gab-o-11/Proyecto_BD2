import hashlib
import os

import numpy as np

from .histograma import ModeloTfIdf, construir_histograma


def resolver_archivo(carpeta, ruta):
    base = os.path.realpath(carpeta)
    completa = os.path.realpath(os.path.join(base, ruta))
    if completa != base and not completa.startswith(base + os.sep):
        raise ValueError(f"la ruta '{ruta}' está fuera de la carpeta multimedia")
    if not os.path.isfile(completa):
        raise ValueError(f"el archivo '{ruta}' no existe")
    return completa


class ExtractFeatures:
    def __init__(self, extractor, vocabulario):
        descriptor_id = extractor.descriptor_id
        if getattr(vocabulario, "descriptor_id", descriptor_id) != descriptor_id:
            raise ValueError(f"el vocabulario no se entrenó con descriptores '{descriptor_id}'")
        centroides = np.asarray(getattr(vocabulario, "centroids", vocabulario), dtype=np.float32)
        if centroides.ndim != 2 or centroides.shape[0] == 0 or centroides.shape[1] != extractor.dimension:
            raise ValueError(f"el vocabulario debe ser una matriz (K, {extractor.dimension}) y llegó {centroides.shape}")
        self.extractor = extractor
        self.descriptor_id = descriptor_id
        self.centroides = centroides
        self.dimension = centroides.shape[0]
        self.vocabulario_id = hashlib.sha256(descriptor_id.encode("utf-8") + centroides.tobytes()).hexdigest()

    def histograma(self, ruta):
        lote = self.extractor.extract(ruta)
        if lote.descriptor_id != self.descriptor_id:
            raise ValueError(f"el extractor entregó descriptores '{lote.descriptor_id}' y se esperaban '{self.descriptor_id}'")
        return construir_histograma(lote.values, self.centroides)

    def ajustar(self, histogramas):
        return ModeloTfIdf.ajustar(histogramas, vocabulario_id=self.vocabulario_id)

    def vector(self, ruta, modelo):
        if modelo.vocabulario_id != self.vocabulario_id:
            raise ValueError("el modelo TF-IDF se ajustó con otro vocabulario; carga de nuevo la colección")
        return modelo.transformar(self.histograma(ruta))


class ColeccionesMultimedia:
    def __init__(self, carpeta):
        self.carpeta = carpeta
        self.extracciones = {}

    def registrar(self, extractor, vocabulario):
        extraccion = ExtractFeatures(extractor, vocabulario)
        self.extracciones[extraccion.descriptor_id] = extraccion
        return extraccion

    def _columna_vector(self, tabla):
        columnas = list(getattr(tabla, "almacenes", {}))
        if len(columnas) != 1:
            raise ValueError(f"'{tabla.name}' debe tener exactamente una columna VECTOR")
        return columnas[0]

    def cargar(self, tabla, columna_ruta, descriptor_id):
        if descriptor_id not in self.extracciones:
            raise ValueError(f"no hay un extractor registrado para '{descriptor_id}'")
        extraccion = self.extracciones[descriptor_id]
        columna = self._columna_vector(tabla)
        dimension = tabla.almacenes[columna].dimension
        if extraccion.dimension != dimension:
            raise ValueError(f"el vocabulario tiene {extraccion.dimension} palabras y la columna '{columna}' es VECTOR({dimension})")
        if dict(tabla.schema).get(columna_ruta) != "str":
            raise ValueError(f"'{columna_ruta}' debe ser una columna de texto de '{tabla.name}'")
        rids = []
        histogramas = []
        for fila in tabla.scan():
            ruta = fila.get(columna_ruta)
            if ruta is None:
                continue
            rids.append(fila["__rid__"])
            histogramas.append(extraccion.histograma(resolver_archivo(self.carpeta, ruta)))
        if not rids:
            raise ValueError(f"'{tabla.name}' no tiene archivos para cargar")
        modelo = extraccion.ajustar(histogramas)
        vectores = []
        for histograma in histogramas:
            vectores.append(modelo.transformar(histograma))
        tabla.cargar_vectores(columna, rids, vectores)
        modelo.guardar(tabla.ruta_modelo(columna))
        return len(rids)

    def vectorizar(self, tabla, ruta):
        modelo = self._modelo(tabla)
        for extraccion in self.extracciones.values():
            if extraccion.vocabulario_id == modelo.vocabulario_id:
                return extraccion.vector(resolver_archivo(self.carpeta, ruta), modelo)
        raise ValueError(f"el vocabulario con el que se cargó '{tabla.name}' ya no está registrado")

    def _modelo(self, tabla):
        ruta_modelo = tabla.ruta_modelo(self._columna_vector(tabla))
        if not os.path.exists(ruta_modelo):
            raise ValueError(f"'{tabla.name}' no tiene características cargadas; usa SIMILAR_TO(VECTOR(...), k=...)")
        return ModeloTfIdf.abrir(ruta_modelo)
