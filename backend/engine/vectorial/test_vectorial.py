import math

import numpy as np

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


def main():
    _metricas()
    print("OK: métricas")


if __name__ == "__main__":
    main()
