import json
import os

import numpy as np

TAMANO_LOTE = 2048


def _matrices(descriptores, centroides):
    centroides = np.asarray(centroides, dtype=np.float32)
    if centroides.ndim != 2 or centroides.shape[0] == 0:
        raise ValueError("el vocabulario debe ser una matriz (K, D) con al menos una palabra")
    descriptores = np.asarray(descriptores, dtype=np.float32)
    if descriptores.size == 0:
        descriptores = descriptores.reshape(0, centroides.shape[1])
    if descriptores.ndim != 2 or descriptores.shape[1] != centroides.shape[1]:
        raise ValueError(f"se esperaban descriptores (N, {centroides.shape[1]}) y llegó {descriptores.shape}")
    return descriptores, centroides


def asignar_palabras(descriptores, centroides):
    descriptores, centroides = _matrices(descriptores, centroides)
    normas = np.einsum("ij,ij->i", centroides, centroides)
    palabras = np.empty(len(descriptores), dtype=np.int64)
    for inicio in range(0, len(descriptores), TAMANO_LOTE):
        lote = descriptores[inicio:inicio + TAMANO_LOTE]
        palabras[inicio:inicio + len(lote)] = np.argmin(normas - 2.0 * (lote @ centroides.T), axis=1)
    return palabras


def construir_histograma(descriptores, centroides):
    centroides = np.asarray(centroides, dtype=np.float32)
    return np.bincount(asignar_palabras(descriptores, centroides), minlength=centroides.shape[0])


class ModeloTfIdf:
    def __init__(self, documentos, frecuencias, sublineal=False, vocabulario_id=None):
        self.documentos = int(documentos)
        self.frecuencias = np.asarray(frecuencias, dtype=np.int64)
        self.sublineal = bool(sublineal)
        self.vocabulario_id = vocabulario_id
        self.idf = np.zeros(len(self.frecuencias), dtype=np.float64)
        presentes = self.frecuencias > 0
        self.idf[presentes] = np.log(self.documentos / self.frecuencias[presentes])

    @classmethod
    def ajustar(cls, histogramas, sublineal=False, vocabulario_id=None):
        histogramas = np.asarray(histogramas)
        if histogramas.ndim != 2 or histogramas.shape[0] == 0:
            raise ValueError("se necesita una matriz (N, K) con al menos un histograma")
        if (histogramas < 0).any():
            raise ValueError("un histograma no admite conteos negativos")
        return cls(histogramas.shape[0], (histogramas > 0).sum(axis=0), sublineal, vocabulario_id)

    def transformar(self, histograma):
        histograma = np.asarray(histograma, dtype=np.float64)
        if histograma.shape != self.idf.shape:
            raise ValueError(f"se esperaba un histograma de dimensión {len(self.idf)} y llegó {histograma.shape}")
        if (histograma < 0).any():
            raise ValueError("un histograma no admite conteos negativos")
        if self.sublineal:
            frecuencia = np.log1p(histograma)
        else:
            total = histograma.sum()
            frecuencia = histograma / total if total > 0 else histograma
        return (frecuencia * self.idf).astype(np.float32)

    def guardar(self, ruta):
        temporal = ruta + ".tmp"
        with open(temporal, "w", encoding="utf-8") as archivo:
            json.dump({
                "documentos": self.documentos,
                "frecuencias": self.frecuencias.tolist(),
                "sublineal": self.sublineal,
                "vocabulario_id": self.vocabulario_id,
            }, archivo)
        os.replace(temporal, ruta)

    @classmethod
    def abrir(cls, ruta):
        with open(ruta, encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return cls(datos["documentos"], datos["frecuencias"], datos["sublineal"], datos["vocabulario_id"])
