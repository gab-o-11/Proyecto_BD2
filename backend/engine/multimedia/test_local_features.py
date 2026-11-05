"""Pruebas de la Parte 4.1: extracción de patrones locales.

Se corren desde la carpeta backend:
    .venv/Scripts/python -m engine.multimedia.test_local_features
"""
import tempfile
from pathlib import Path

import cv2
import numpy as np

from engine.multimedia.local_features import DescriptorBatch, SiftExtractor


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


def imagen_con_formas(alto=480, ancho=640):
    """Imagen sintética con bordes, esquinas y texto: SIFT encuentra keypoints."""
    img = np.full((alto, ancho), 40, np.uint8)
    cv2.rectangle(img, (60, 60), (220, 260), 200, -1)
    cv2.circle(img, (470, 200), 90, 140, -1)
    cv2.putText(img, "BD2", (230, 420), cv2.FONT_HERSHEY_SIMPLEX, 3, 255, 8)
    ruido = np.random.default_rng(0).integers(0, 25, img.shape, dtype=np.uint8)
    return cv2.GaussianBlur(cv2.add(img, ruido), (3, 3), 0)


def guardar(img, ruta):
    """cv2.imwrite también falla con tildes en Windows: se codifica en memoria
    y se escribe con numpy."""
    ok, buffer = cv2.imencode(".png", img)
    assert ok
    buffer.tofile(str(ruta))


def test_sift():
    ext = SiftExtractor(max_side=320, nfeatures=200)
    assert ext.descriptor_id == "sift:gray:max320:nf200"
    assert ext.dimension == 128

    with tempfile.TemporaryDirectory() as carpeta:
        carpeta = Path(carpeta)

        # 1. Imagen con estructura y con tildes en el nombre
        ruta = carpeta / "polo_azúl_ñ.png"
        guardar(imagen_con_formas(), ruta)
        b = ext.extract(ruta)
        n = len(b)
        assert n > 0, "una imagen con formas debe tener keypoints"
        assert b.values.shape == (n, 128) and b.positions.shape == (n, 4)
        assert b.descriptor_id == ext.descriptor_id and b.source == str(ruta)

        # 2. OpenCV entrega enteros entre 0 y 255 (por eso caben en uint8)
        assert b.values.min() >= 0 and b.values.max() <= 255
        assert np.array_equal(b.values, np.round(b.values))

        # 3. Posiciones en píxeles de la imagen ORIGINAL (640 x 480), aunque
        #    SIFT trabajó sobre la reducida (320 x 240): hay keypoints con x > 320
        x, y = b.positions[:, 0], b.positions[:, 1]
        assert x.min() >= 0 and x.max() < 640 and y.min() >= 0 and y.max() < 480
        assert x.max() > 320, "las posiciones no se reescalaron a la imagen original"

        # 4. Imagen lisa: 0 keypoints → lote vacío con las formas correctas
        lisa = carpeta / "lisa.png"
        guardar(np.full((200, 200), 128, np.uint8), lisa)
        v = ext.extract(lisa)
        assert len(v) == 0
        assert v.values.shape == (0, 128) and v.positions.shape == (0, 4)

        # 5. Archivos que no son imágenes
        falsa = carpeta / "falsa.jpg"
        falsa.write_bytes(b"esto no es una imagen")
        debe_fallar(lambda: ext.extract(falsa), "archivo que no es imagen")
        vacio = carpeta / "vacio.jpg"
        vacio.write_bytes(b"")
        debe_fallar(lambda: ext.extract(vacio), "archivo vacío")


if __name__ == "__main__":
    test_descriptor_batch()
    print("OK: DescriptorBatch")
    test_sift()
    print("OK: SiftExtractor")