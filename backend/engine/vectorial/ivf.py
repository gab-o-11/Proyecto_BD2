import math

import faiss
import numpy as np

from .indice_faiss import IndiceFaiss
from .metricas import COSINE


def lists_por_defecto(filas):
    return max(1, round(math.sqrt(filas)))


class IndiceIVF(IndiceFaiss):
    tipo = "IVF"

    def __init__(self, almacen, metrica, lists=None):
        super().__init__(almacen, metrica)
        self.lists = lists

    def _parametros(self):
        return [self.lists]

    def construir(self):
        ids = self.almacen.ids_vivos()
        if ids.size == 0:
            raise ValueError("IVF necesita datos: crea el índice con la tabla ya cargada")
        lists = lists_por_defecto(len(ids)) if self.lists is None else self.lists
        if not 1 <= lists <= len(ids):
            raise ValueError(f"lists debe estar entre 1 y {len(ids)}")
        self.lists = lists
        cuantizador = faiss.IndexFlat(self.almacen.dimension, self._metrica_faiss())
        self.indice = faiss.IndexIVFFlat(cuantizador, self.almacen.dimension, lists, self._metrica_faiss())
        self.indice.cp.min_points_per_centroid = 1
        self.indice.cp.spherical = self.metrica == COSINE
        self.indice.train(self._preparar(self.almacen.matriz()[ids]))
        self.indexados = set()
        self._agregar(ids)

    def probes_por_defecto(self):
        return max(1, round(math.sqrt(self.lists)))

    def buscar(self, consulta, k, probes=None):
        if k <= 0:
            raise ValueError("k debe ser un entero positivo")
        if self.indice is None:
            return []
        probes = self.probes_por_defecto() if probes is None else probes
        if probes <= 0:
            raise ValueError("probes debe ser un entero positivo")
        selector = self._selector()
        parametros = faiss.SearchParametersIVF(nprobe=probes)
        if selector is not None:
            parametros.sel = selector
        return self._consultar(consulta, k, parametros)

    def borrar(self, identificador):
        if identificador in self.indexados:
            self.indice.remove_ids(np.array([identificador], dtype=np.int64))
            self.indexados.remove(identificador)

    def sincronizar(self):
        vivos = set(self.almacen.ids_vivos().tolist())
        for identificador in sorted(self.indexados - vivos):
            self.borrar(identificador)
        super().sincronizar()
