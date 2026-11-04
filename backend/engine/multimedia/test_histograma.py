import numpy as np

from .histograma import asignar_palabras, construir_histograma


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


def main():
    _histograma()
    print("OK: histograma")


if __name__ == "__main__":
    main()
