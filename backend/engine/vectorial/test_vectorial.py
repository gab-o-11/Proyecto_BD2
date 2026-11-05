import math
import os
import tempfile

import numpy as np

from .exacta import knn_exacto, recall_at_k
from .almacen import AlmacenVectores
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


def _almacen():
    with tempfile.TemporaryDirectory(prefix="test_vectorial_") as carpeta:
        ruta = os.path.join(carpeta, "t_embedding")
        almacen = AlmacenVectores(ruta, 4)
        datos = _vectores(300, 4)
        ids = [almacen.agregar(vector, (1, i)) for i, vector in enumerate(datos)]
        assert ids == list(range(300)) and len(almacen) == 300
        assert np.array_equal(almacen.vector(120), datos[120])
        assert almacen.rid(120) == (1, 120) and almacen.id_de((1, 120)) == 120
        assert almacen.borrar((1, 120)) == 120 and almacen.borrar((1, 120)) is None
        assert not almacen.vivo(120) and almacen.id_de((1, 120)) is None and len(almacen) == 299
        assert almacen.agregar(datos[0], (1, 120)) == 300
        assert almacen.rid(300) == (1, 120) and 120 not in almacen.ids_vivos().tolist()
        _falla(lambda: almacen.agregar(datos[0], (1, 120)), "RID repetido")
        _falla(lambda: almacen.agregar([1, 2], (2, 0)), "dimensión incorrecta")
        _falla(lambda: almacen.agregar([1, 2, 3, float("nan")], (2, 0)), "valor no finito")
        assert almacen.agregar_lote(datos[:2], [(3, 0), (3, 1)]) == [301, 302]
        almacen.cerrar()
        reabierto = AlmacenVectores(ruta, 4)
        assert reabierto.total == 303 and len(reabierto) == 302
        assert np.array_equal(reabierto.vector(5), datos[5]) and reabierto.id_de((3, 1)) == 302
        assert not reabierto.vivo(120) and reabierto.id_de((1, 120)) == 300
        _falla(lambda: AlmacenVectores(ruta, 8), "dimensión distinta al reabrir")
        reabierto.destruir()
        assert os.listdir(carpeta) == []
        _falla(lambda: AlmacenVectores(ruta, 0), "dimensión no positiva")


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
    _almacen()
    print("OK: métricas, búsqueda exacta y almacén de vectores")


if __name__ == "__main__":
    main()
