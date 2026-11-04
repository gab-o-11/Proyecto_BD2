import heapq

import numpy as np

from .metricas import distancias

TAMANO_LOTE = 4096


def knn_exacto(consulta, matriz, k, metrica, ids=None):
    if k <= 0:
        raise ValueError("k debe ser un entero positivo")
    if ids is None:
        ids = np.arange(len(matriz))
    mejores = []
    for inicio in range(0, len(ids), TAMANO_LOTE):
        bloque = ids[inicio:inicio + TAMANO_LOTE]
        valores = distancias(consulta, matriz[bloque], metrica)
        if len(mejores) == k:
            utiles = valores <= -mejores[0][0]
            bloque, valores = bloque[utiles], valores[utiles]
        for valor, identificador in zip(valores.tolist(), bloque.tolist()):
            par = (-valor, -identificador)
            if len(mejores) < k:
                heapq.heappush(mejores, par)
            elif par > mejores[0]:
                heapq.heapreplace(mejores, par)
    resultado = []
    for valor, identificador in mejores:
        resultado.append((-valor, -identificador))
    resultado.sort()
    return resultado


def recall_at_k(exactos, aproximados):
    if not exactos:
        return 1.0
    return len(set(exactos) & set(aproximados)) / len(exactos)
