import math
import os
import tempfile

import numpy as np

from .histograma import ModeloTfIdf, asignar_palabras, construir_histograma


def _falla(funcion, caso):
    try:
        funcion()
    except ValueError:
        return
    raise AssertionError(f"debía fallar: {caso}")


CENTROIDES = np.array([[0, 0], [10, 0], [0, 10], [10, 10]], dtype=np.float32)


def _histograma():
    descriptores = [[1, 1], [9, 1], [0.5, 9], [9, 9], [8, 8], [11, 12], [0, 0]]
    assert asignar_palabras(descriptores, CENTROIDES).tolist() == [0, 1, 2, 3, 3, 3, 0]
    assert construir_histograma(descriptores, CENTROIDES).tolist() == [2, 1, 1, 3]
    assert construir_histograma([], CENTROIDES).tolist() == [0, 0, 0, 0]
    azar = np.random.default_rng(0)
    muchos = azar.random((5000, 8)) * 10
    palabras = azar.random((64, 8)) * 10
    directo = np.argmin(((muchos[:, None, :] - palabras[None, :, :]) ** 2).sum(axis=2), axis=1)
    assert np.array_equal(asignar_palabras(muchos, palabras), directo)
    assert construir_histograma(muchos, palabras).sum() == 5000
    _falla(lambda: construir_histograma([[1, 2, 3]], CENTROIDES), "dimensión distinta")
    _falla(lambda: construir_histograma([[1, 2]], np.empty((0, 2))), "vocabulario vacío")


def _tfidf():
    histogramas = [[1, 8, 1, 0], [5, 1, 0, 0], [2, 0, 0, 0], [3, 0, 0, 0]]
    modelo = ModeloTfIdf.ajustar(histogramas, vocabulario_id="v1")
    assert modelo.documentos == 4 and modelo.frecuencias.tolist() == [4, 2, 1, 0]
    esperado = [0.0, math.log(2), math.log(4), 0.0]
    assert np.allclose(modelo.idf, esperado)
    vector = modelo.transformar([1, 8, 1, 0])
    assert vector.dtype == np.float32
    assert np.allclose(vector, [1 / 10 * 0.0, 8 / 10 * math.log(2), 1 / 10 * math.log(4), 0.0])
    assert np.allclose(modelo.transformar([0, 0, 0, 7]), [0, 0, 0, 0])
    assert np.allclose(modelo.transformar([0, 0, 0, 0]), [0, 0, 0, 0])
    sublineal = ModeloTfIdf.ajustar(histogramas, sublineal=True)
    assert np.allclose(sublineal.transformar([1, 8, 1, 0]), [0.0, math.log(9) * math.log(2), math.log(2) * math.log(4), 0.0])
    norma = np.linalg.norm(vector)
    assert abs(norma - 1.0) > 1e-3
    with tempfile.TemporaryDirectory(prefix="test_histograma_") as carpeta:
        ruta = os.path.join(carpeta, "modelo.json")
        modelo.guardar(ruta)
        reabierto = ModeloTfIdf.abrir(ruta)
        assert reabierto.vocabulario_id == "v1" and not reabierto.sublineal
        assert np.array_equal(reabierto.transformar([1, 8, 1, 0]), vector)
        assert os.listdir(carpeta) == ["modelo.json"]
    _falla(lambda: ModeloTfIdf.ajustar([]), "colección vacía")
    _falla(lambda: ModeloTfIdf.ajustar([[1, -1]]), "conteo negativo")
    _falla(lambda: modelo.transformar([1, 2]), "dimensión distinta")
    _falla(lambda: modelo.transformar([1, 2, 3, -1]), "conteo negativo en la consulta")


def main():
    _histograma()
    _tfidf()
    print("OK: histograma y TF-IDF")


if __name__ == "__main__":
    main()
