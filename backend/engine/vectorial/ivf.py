import math

import numpy as np

from .exacta import knn_exacto
from .kmeans import _asignar, centroides_cercanos, kmeans
from .metricas import COSINE, EUCLIDEAN, validar_metrica

MUESTRAS_POR_LISTA = 50


def lists_por_defecto(filas):
    return max(1, round(math.sqrt(filas)))


class IndiceIVF:
    tipo = "IVF"

    def __init__(self, almacen, metrica, lists=None, semilla=0):
        self.almacen = almacen
        self.metrica = validar_metrica(metrica)
        self.lists = lists
        self.semilla = semilla
        self.centroides = None
        self.listas = []

    def _metrica_kmeans(self):
        return COSINE if self.metrica == COSINE else EUCLIDEAN

    def construir(self):
        ids = self.almacen.ids_vivos()
        if ids.size == 0:
            raise ValueError("IVF necesita datos: crea el índice con la tabla ya cargada")
        lists = lists_por_defecto(len(ids)) if self.lists is None else self.lists
        if not 1 <= lists <= len(ids):
            raise ValueError(f"lists debe estar entre 1 y {len(ids)}")
        self.lists = lists
        azar = np.random.default_rng(self.semilla)
        cantidad = min(len(ids), lists * MUESTRAS_POR_LISTA)
        muestra = np.sort(azar.choice(ids, cantidad, replace=False))
        matriz = self.almacen.matriz()
        self.centroides, _ = kmeans(np.asarray(matriz[muestra]), lists, self._metrica_kmeans(), semilla=self.semilla)
        asignaciones, _ = _asignar(np.asarray(matriz[ids]), self.centroides, self._metrica_kmeans())
        self.listas = [[] for _ in range(lists)]
        for identificador, lista in zip(ids.tolist(), asignaciones.tolist()):
            self.listas[lista].append(identificador)

    def probes_por_defecto(self):
        return max(1, round(math.sqrt(self.lists)))

    def buscar(self, consulta, k, probes=None):
        if self.centroides is None:
            return []
        probes = self.probes_por_defecto() if probes is None else probes
        if probes <= 0:
            raise ValueError("probes debe ser un entero positivo")
        elegidas = centroides_cercanos(consulta, self.centroides, self.metrica, probes)
        candidatos = [self.listas[i] for i in elegidas.tolist()]
        ids = np.fromiter((i for lista in candidatos for i in lista), dtype=np.int64)
        ids = ids[self.almacen.mascara_vivos()[ids]]
        return knn_exacto(consulta, self.almacen.matriz(), k, self.metrica, ids)
