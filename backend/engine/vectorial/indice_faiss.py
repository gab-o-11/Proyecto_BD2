import os

import faiss
import numpy as np

from .metricas import COSINE, EUCLIDEAN, distancias, validar_metrica


class IndiceFaiss:
    def __init__(self, almacen, metrica):
        self.almacen = almacen
        self.metrica = validar_metrica(metrica)
        self.indice = None
        self.indexados = set()

    def _metrica_faiss(self):
        if self.metrica == EUCLIDEAN:
            return faiss.METRIC_L2
        return faiss.METRIC_INNER_PRODUCT

    def _preparar(self, vectores):
        vectores = np.array(vectores, dtype=np.float32)
        if self.metrica == COSINE:
            faiss.normalize_L2(vectores)
        return vectores

    def _agregar(self, ids):
        ids = np.array(ids, dtype=np.int64)
        self.indice.add_with_ids(self._preparar(self.almacen.matriz()[ids]), ids)
        for identificador in ids.tolist():
            self.indexados.add(identificador)

    def _selector(self):
        muertos = np.flatnonzero(~self.almacen.mascara_vivos())
        if muertos.size == 0:
            return None
        return faiss.IDSelectorNot(faiss.IDSelectorBatch(muertos.astype(np.int64)))

    def _consultar(self, consulta, k, parametros):
        consulta = np.asarray(consulta, dtype=np.float32)
        _, vecinos = self.indice.search(self._preparar(consulta.reshape(1, -1)), k, params=parametros)
        ids = []
        for identificador in vecinos[0].tolist():
            if identificador >= 0:
                ids.append(identificador)
        if not ids:
            return []
        valores = distancias(consulta, self.almacen.matriz()[ids], self.metrica)
        pares = []
        for valor, identificador in zip(valores.tolist(), ids):
            pares.append((valor, identificador))
        pares.sort()
        return pares

    def insertar(self, identificador):
        if self.indice is None:
            raise ValueError(f"el índice {self.tipo} todavía no está construido")
        if identificador not in self.indexados:
            self._agregar([identificador])

    def sincronizar(self):
        nuevos = []
        for identificador in self.almacen.ids_vivos().tolist():
            if identificador not in self.indexados:
                nuevos.append(identificador)
        if nuevos:
            self._agregar(nuevos)

    def guardar(self, ruta):
        temporal = ruta + ".tmp"
        with open(temporal, "wb") as archivo:
            np.savez(
                archivo,
                indice=faiss.serialize_index(self.indice),
                indexados=np.array(sorted(self.indexados), dtype=np.int64),
                parametros=np.array(self._parametros()),
                metrica=np.array(self.metrica),
            )
        os.replace(temporal, ruta)

    @classmethod
    def abrir(cls, almacen, ruta):
        with np.load(ruta) as datos:
            indice = cls(almacen, str(datos["metrica"]), *datos["parametros"].tolist())
            indice.indice = faiss.deserialize_index(datos["indice"])
            indice.indexados = set(datos["indexados"].tolist())
        indice.sincronizar()
        return indice
