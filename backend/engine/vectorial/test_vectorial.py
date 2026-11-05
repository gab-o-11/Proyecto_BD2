import math
import os
import tempfile

import numpy as np

from .exacta import knn_exacto, recall_at_k
from .almacen import AlmacenVectores
from .kmeans import centroides_cercanos, kmeans
from .ivf import IndiceIVF, lists_por_defecto
from .hnsw import IndiceHNSW
from .metricas import COSINE, DOT, EUCLIDEAN, distancia, distancias, distancias_entre, score, validar_metrica


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


def _kmeans():
    azar = np.random.default_rng(1)
    centros = np.array([[0, 0], [20, 0], [0, 20], [20, 20]], dtype=np.float32)
    datos = (centros[np.repeat(np.arange(4), 50)] + azar.normal(0, 0.5, (200, 2))).astype(np.float32)
    centroides, asignaciones = kmeans(datos, 4, semilla=3)
    grupos = [set(asignaciones[i * 50:(i + 1) * 50].tolist()) for i in range(4)]
    if all(len(g) == 1 for g in grupos):
        for i, grupo in enumerate(grupos):
            assert np.linalg.norm(centroides[grupo.pop()] - centros[i]) < 1
    assert len(set(asignaciones.tolist())) == 4
    uno, solo = kmeans(datos, 1)
    assert set(solo.tolist()) == {0} and np.allclose(uno[0], datos.mean(axis=0), atol=1e-3)
    tope, _ = kmeans(datos, 4, iteraciones=1)
    assert tope.shape == (4, 2)
    iguales, grupos_iguales = kmeans(np.ones((10, 2), dtype=np.float32), 3)
    assert iguales.shape == (3, 2) and len(grupos_iguales) == 10
    _, angulos = kmeans(np.array([[1, 0], [50, 1], [0, 1], [1, 50]], dtype=np.float32), 2, COSINE, semilla=2)
    assert angulos[0] == angulos[1] and angulos[2] == angulos[3] and angulos[0] != angulos[2]
    assert centroides_cercanos([0, 0], centros, EUCLIDEAN, 2).tolist() == [0, 1]
    _falla(lambda: kmeans(datos, 0), "k no positivo")
    _falla(lambda: kmeans(datos, 500), "k mayor que los datos")
    _falla(lambda: kmeans(np.empty((0, 2)), 1), "sin datos")
    _falla(lambda: kmeans(datos, 2, DOT), "producto punto")


def _cargar_almacen(carpeta, datos, nombre="t_e"):
    almacen = AlmacenVectores(os.path.join(carpeta, nombre), datos.shape[1])
    almacen.agregar_lote(datos, [(1, i) for i in range(len(datos))])
    return almacen


def _ivf():
    datos = _vectores(2000, 16)
    consultas = _vectores(40, 16, semilla=9)
    with tempfile.TemporaryDirectory(prefix="test_vectorial_") as carpeta:
        for metrica in (EUCLIDEAN, COSINE, DOT):
            almacen = _cargar_almacen(carpeta, datos, "t_" + metrica)
            indice = IndiceIVF(almacen, metrica)
            indice.construir()
            assert indice.lists == lists_por_defecto(2000) == 45 and indice.probes_por_defecto() == 7
            assert sum(len(lista) for lista in indice.listas) == 2000
            exactos = [knn_exacto(q, datos, 10, metrica) for q in consultas]
            for q, exacto in zip(consultas, exactos):
                assert indice.buscar(q, 10, probes=indice.lists) == exacto
            bajo = np.mean([recall_at_k([i for _, i in e], [i for _, i in indice.buscar(q, 10, probes=1)]) for q, e in zip(consultas, exactos)])
            alto = np.mean([recall_at_k([i for _, i in e], [i for _, i in indice.buscar(q, 10, probes=15)]) for q, e in zip(consultas, exactos)])
            assert alto >= bajo and alto >= 0.8, (metrica, bajo, alto)
            assert indice.buscar(consultas[0], 10, probes=9999) == exactos[0]
            _falla(lambda: indice.buscar(consultas[0], 10, probes=0), "probes no positivo")
        vacio = AlmacenVectores(os.path.join(carpeta, "vacio"), 16)
        _falla(IndiceIVF(vacio, COSINE).construir, "tabla sin datos")
        assert IndiceIVF(vacio, COSINE).buscar(consultas[0], 3) == []
        _falla(IndiceIVF(_cargar_almacen(carpeta, datos[:5], "pocos"), COSINE, lists=6).construir, "lists mayor que los datos")
        _falla(lambda: IndiceIVF(vacio, "manhattan"), "métrica desconocida")


def _ivf_mantenimiento():
    datos = _vectores(800, 8)
    with tempfile.TemporaryDirectory(prefix="test_vectorial_") as carpeta:
        almacen = _cargar_almacen(carpeta, datos)
        indice = IndiceIVF(almacen, COSINE)
        _falla(lambda: indice.insertar(0), "insertar sin construir")
        indice.construir()
        todas = indice.lists
        nuevo = almacen.agregar(datos[3] * 2, (2, 0))
        indice.insertar(nuevo)
        indice.insertar(nuevo)
        assert sum(len(lista) for lista in indice.listas) == 801
        assert nuevo in {i for _, i in indice.buscar(datos[3], 3, probes=todas)}
        rid = almacen.rid(3)
        almacen.borrar(rid)
        indice.borrar(3)
        indice.borrar(3)
        assert sum(len(lista) for lista in indice.listas) == 800
        assert 3 not in {i for _, i in indice.buscar(datos[3], 5, probes=todas)}
        almacen.borrar(almacen.rid(4))
        assert 4 not in {i for _, i in indice.buscar(datos[4], 5, probes=todas)}
        ruta = os.path.join(carpeta, "indice.ivf")
        indice.guardar(ruta)
        posterior = almacen.agregar(datos[9], (2, 1))
        almacen.borrar(almacen.rid(10))
        reabierto = IndiceIVF.abrir(almacen, ruta)
        assert reabierto.metrica == COSINE and reabierto.lists == todas
        assert posterior in reabierto.lista_de and 10 not in reabierto.lista_de and 4 not in reabierto.lista_de
        vivos = almacen.ids_vivos()
        for q in datos[:10]:
            assert reabierto.buscar(q, 7, probes=todas) == knn_exacto(q, almacen.matriz(), 7, COSINE, vivos)
        assert sorted(reabierto.lista_de) == vivos.tolist()
        assert os.path.exists(ruta) and not os.path.exists(ruta + ".tmp")


def _recall(indice, consultas, exactos, **opciones):
    total = 0.0
    for consulta, exacto in zip(consultas, exactos):
        aproximado = indice.buscar(consulta, 10, **opciones)
        ids_exactos = []
        for _, identificador in exacto:
            ids_exactos.append(identificador)
        ids_aproximados = []
        for _, identificador in aproximado:
            ids_aproximados.append(identificador)
        total += recall_at_k(ids_exactos, ids_aproximados)
    return total / len(exactos)


def _hnsw():
    datos = _vectores(1500, 16)
    consultas = _vectores(30, 16, semilla=9)
    with tempfile.TemporaryDirectory(prefix="test_vectorial_") as carpeta:
        for metrica, minimo in ((EUCLIDEAN, 0.95), (COSINE, 0.95), (DOT, 0.95)):
            almacen = _cargar_almacen(carpeta, datos, "hnsw_" + metrica)
            indice = IndiceHNSW(almacen, metrica)
            indice.construir()
            exactos = []
            for consulta in consultas:
                exactos.append(knn_exacto(consulta, datos, 10, metrica))
            alto = _recall(indice, consultas, exactos, ef_search=200)
            assert alto >= minimo, (metrica, alto)
            assert alto >= _recall(indice, consultas, exactos, ef_search=10) - 0.01
            assert len(indice.buscar(consultas[0], 10, ef_search=1)) == 10
            for capas in indice.vecinos.values():
                for capa, lista in enumerate(capas):
                    assert len(lista) <= indice._limite(capa)
                    assert len(lista) == len(set(lista))
            assert indice.nivel_maximo == len(indice.vecinos[indice.entrada]) - 1
            indice.insertar(0)
            assert len(indice.vecinos) == 1500
        vacio = AlmacenVectores(os.path.join(carpeta, "vacio_hnsw"), 16)
        sin_datos = IndiceHNSW(vacio, COSINE)
        sin_datos.construir()
        assert sin_datos.buscar(consultas[0], 3) == []
        _falla(lambda: sin_datos.buscar(consultas[0], 0), "k no positivo")
        _falla(lambda: sin_datos.buscar(consultas[0], 3, ef_search=0), "ef_search no positivo")
        _falla(lambda: IndiceHNSW(vacio, COSINE, m=1), "m menor que 2")
        _falla(lambda: IndiceHNSW(vacio, COSINE, ef_construccion=0), "ef_construccion no positivo")
        assert IndiceHNSW(vacio, COSINE).m_max0 == 32


def _hnsw_mantenimiento():
    datos = _vectores(600, 8)
    with tempfile.TemporaryDirectory(prefix="test_vectorial_") as carpeta:
        almacen = _cargar_almacen(carpeta, datos, "hnsw_m")
        indice = IndiceHNSW(almacen, COSINE)
        indice.construir()
        assert 3 in {i for _, i in indice.buscar(datos[3], 5, ef_search=100)}
        almacen.borrar(almacen.rid(3))
        indice.borrar(3)
        assert 3 not in {i for _, i in indice.buscar(datos[3], 5, ef_search=100)}
        assert len(indice.buscar(datos[3], 5, ef_search=100)) == 5
        nuevo = almacen.agregar(datos[3] * 3, (2, 0))
        indice.insertar(nuevo)
        assert nuevo == indice.buscar(datos[3], 1, ef_search=100)[0][1]
        ruta = os.path.join(carpeta, "indice.hnsw")
        indice.guardar(ruta)
        assert not os.path.exists(ruta + ".tmp")
        antes = indice.buscar(datos[7], 10, ef_search=50)
        posterior = almacen.agregar(datos[8] * 2, (2, 1))
        reabierto = IndiceHNSW.abrir(almacen, ruta)
        assert reabierto.metrica == COSINE and reabierto.m == 16 and reabierto.ef_construccion == 64
        assert reabierto.vecinos[0] == indice.vecinos[0] and posterior in reabierto.vecinos
        assert reabierto.nivel_maximo >= indice.nivel_maximo
        ids_antes = set()
        for _, identificador in antes:
            ids_antes.add(identificador)
        ids_despues = set()
        for _, identificador in reabierto.buscar(datos[7], 10, ef_search=50):
            ids_despues.add(identificador)
        assert ids_despues == ids_antes
        assert 3 not in {i for _, i in reabierto.buscar(datos[3], 5, ef_search=100)}
        for identificador in almacen.ids_vivos().tolist():
            almacen.borrar(almacen.rid(identificador))
        assert reabierto.buscar(datos[0], 5) == []
        sin_datos = IndiceHNSW(AlmacenVectores(os.path.join(carpeta, "vacio_m"), 8), EUCLIDEAN)
        ruta_vacia = os.path.join(carpeta, "vacio.hnsw")
        sin_datos.guardar(ruta_vacia)
        assert IndiceHNSW.abrir(sin_datos.almacen, ruta_vacia).entrada is None


def _distancias_entre():
    azar = np.random.default_rng(3)
    matriz = azar.normal(0, 1, (40, 16)).astype(np.float32)
    matriz[5] = 0
    matriz[9] = matriz[8]
    for metrica in (EUCLIDEAN, COSINE, DOT):
        cruzadas = distancias_entre(matriz, metrica)
        assert cruzadas.shape == (40, 40)
        for fila in range(40):
            assert np.allclose(cruzadas[fila], distancias(matriz[fila], matriz, metrica), atol=1e-3), (metrica, fila)


def _seleccion_hnsw():
    with tempfile.TemporaryDirectory(prefix="test_vectorial_") as carpeta:
        almacen = AlmacenVectores(os.path.join(carpeta, "v"), 2)
        puntos = [[1.0, 0.0], [1.1, 0.0], [1.2, 0.0], [0.0, 2.0], [0.0, 2.1]]
        for posicion, punto in enumerate(puntos):
            almacen.agregar(punto, (1, posicion))
        indice = IndiceHNSW(almacen, EUCLIDEAN, m=4)
        candidatos = []
        for posicion, punto in enumerate(puntos):
            candidatos.append((distancia([0.0, 0.0], punto, EUCLIDEAN), posicion))
        assert indice._seleccionar(candidatos, 4) == [0, 3]
        assert indice._seleccionar(candidatos, 1) == [0]
        assert indice._seleccionar(candidatos[:3], 3) == [0, 1, 2]
        almacen.cerrar()


def main():
    _distancias_entre()
    _seleccion_hnsw()
    _metricas()
    _exacta()
    _almacen()
    _kmeans()
    _ivf()
    _ivf_mantenimiento()
    _hnsw()
    _hnsw_mantenimiento()
    print("OK: métricas, búsqueda exacta, almacén de vectores, k-means, IVF, mantenimiento de IVF, HNSW, mantenimiento de HNSW")


if __name__ == "__main__":
    main()
