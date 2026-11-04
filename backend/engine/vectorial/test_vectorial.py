import math

import numpy as np

from .exacta import knn_exacto, recall_at_k
from .metricas import COSINE, DOT, EUCLIDEAN, distancia, distancias, score, validar_metrica


def _cerca(a, b, tolerancia=1e-5):
    assert abs(a - b) <= tolerancia, (a, b)


def _falla(funcion, caso):
    try:
        funcion()
    except ValueError:
        return
    raise AssertionError(f"debía fallar: {caso}")


def _metricas():
    a = [1.0, 1.0]
    b = [10.0, 10.0]
    _cerca(distancia(a, b, EUCLIDEAN), math.sqrt(162), 1e-4)
    _cerca(distancia(a, b, COSINE), 0.0)
    _cerca(distancia(a, b, DOT), -20.0)
    _cerca(distancia([1, 0], [0, 1], COSINE), 1.0)
    _cerca(distancia([1, 0], [-1, 0], COSINE), 2.0)
    _cerca(distancia([0, 0], [1, 1], COSINE), 1.0)
    lote = distancias([1, 0], np.array([[1, 0], [0, 1], [3, 4]]), EUCLIDEAN)
    for valor, esperado in zip(lote, [0.0, math.sqrt(2), math.sqrt(20)]):
        _cerca(float(valor), esperado)
    _cerca(score(0.0, EUCLIDEAN), 1.0)
    _cerca(score(1.0, EUCLIDEAN), 0.5)
    _cerca(score(3.0, EUCLIDEAN), 0.25)
    _cerca(score(0.25, COSINE), 0.75)
    _cerca(score(-20.0, DOT), 20.0)
    _falla(lambda: validar_metrica("manhattan"), "métrica desconocida")
    _falla(lambda: distancias([1], [[1]], "manhattan"), "métrica desconocida en distancias")


def _vectores(n, dimension, grupos=8, semilla=0):
    azar = np.random.default_rng(semilla)
    centros = azar.random((grupos, dimension)) * 4
    return (centros[azar.integers(0, grupos, n)] + azar.normal(0, 0.25, (n, dimension))).astype(np.float32)


def _exacta():
    datos = _vectores(5000, 16)
    for metrica in (EUCLIDEAN, COSINE, DOT):
        for k in (1, 10, 5000, 7000):
            consulta = datos[17]
            valores = distancias(consulta, datos, metrica)
            orden = sorted(zip(valores.tolist(), range(len(datos))))[:k]
            resultado = knn_exacto(consulta, datos, k, metrica)
            assert [i for _, i in resultado] == [i for _, i in orden], (metrica, k)
    ids = np.array([3, 9, 12, 40])
    assert {i for _, i in knn_exacto(datos[0], datos, 10, EUCLIDEAN, ids)} == {3, 9, 12, 40}
    assert knn_exacto(datos[0], datos, 3, EUCLIDEAN, np.array([], dtype=np.int64)) == []
    _falla(lambda: knn_exacto(datos[0], datos, 0, EUCLIDEAN), "k no positivo")
    _cerca(recall_at_k([1, 2, 3, 4, 5], [1, 2, 3, 8, 9]), 0.6)
    _cerca(recall_at_k([], []), 1.0)


def main():
    _metricas()
    _exacta()
    print("OK: métricas, búsqueda exacta")


if __name__ == "__main__":
    main()
