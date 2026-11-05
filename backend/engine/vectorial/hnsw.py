import faiss

from .indice_faiss import IndiceFaiss

EF_SEARCH = 40


class IndiceHNSW(IndiceFaiss):
    tipo = "HNSW"

    def __init__(self, almacen, metrica, m=16, ef_construccion=64):
        super().__init__(almacen, metrica)
        if m < 2:
            raise ValueError("m debe ser mayor o igual a 2")
        if ef_construccion < 1:
            raise ValueError("ef_construccion debe ser un entero positivo")
        self.m = m
        self.ef_construccion = ef_construccion

    def _parametros(self):
        return [self.m, self.ef_construccion]

    def construir(self):
        grafo = faiss.IndexHNSWFlat(self.almacen.dimension, self.m, self._metrica_faiss())
        grafo.hnsw.efConstruction = self.ef_construccion
        self.indice = faiss.IndexIDMap(grafo)
        self.indexados = set()
        self.sincronizar()

    def buscar(self, consulta, k, ef_search=None):
        if k <= 0:
            raise ValueError("k debe ser un entero positivo")
        if ef_search is None:
            ef_search = EF_SEARCH
        if ef_search <= 0:
            raise ValueError("ef_search debe ser un entero positivo")
        if self.indice is None:
            return []
        selector = self._selector()
        parametros = faiss.SearchParametersHNSW(efSearch=max(ef_search, k))
        if selector is not None:
            parametros.sel = selector
        return self._consultar(consulta, k, parametros)

    def borrar(self, identificador):
        return
