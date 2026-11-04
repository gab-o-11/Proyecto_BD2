"""Pruebas de la Parte 4.1: extracción de patrones locales.

Se corren desde la carpeta backend:
    .venv/Scripts/python -m engine.multimedia.test_local_features
"""
import numpy as np

from engine.multimedia.local_features import DescriptorBatch


def debe_fallar(funcion, caso):
    """Comprueba que funcion() lance ValueError. Si no lanza nada, la prueba falla."""
    try:
        funcion()
    except ValueError:
        return
    raise AssertionError(f"debía fallar y no falló: {caso}")


def test_descriptor_batch():
    # 1. Caso válido: una lista de enteros queda como matriz float32 (N, D)
    b = DescriptorBatch("t", 3, [[1, 2, 3], [4, 5, 6]])
    assert b.descriptor_id == "t"
    assert len(b) == 2
    assert b.values.dtype == np.float32 and b.values.shape == (2, 3)

    # 2. Lote vacío (imagen sin keypoints): forma (0, D), no (0,)
    vacio = DescriptorBatch("t", 128, [])
    assert len(vacio) == 0 and vacio.values.shape == (0, 128)

    # 3. Tiempos de MFCC como vector (N,): se guardan como columna (N, 1)
    audio = DescriptorBatch("t", 3, [[1, 2, 3], [4, 5, 6]], positions=[0.0, 0.023])
    assert audio.positions.shape == (2, 1)

    # 4. Lo que se debe rechazar
    debe_fallar(lambda: DescriptorBatch("t", 3, [[1, 2]]), "dimensión distinta")
    debe_fallar(lambda: DescriptorBatch("t", 3, [[1, 2, 3]], positions=np.zeros((2, 4))),
                "positions con otra cantidad de filas")
    debe_fallar(lambda: DescriptorBatch("t", 3, [[1, np.nan, 3]]), "valor NaN")
    debe_fallar(lambda: DescriptorBatch("t", 0, []), "dimensión 0")


if __name__ == "__main__":
    test_descriptor_batch()
    print("OK: DescriptorBatch")