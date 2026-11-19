import cv2
import numpy as np

import lfw
from config import ARCHIVO_LFW, DIMENSION, LADO_ALINEADO, MODELO_ARCFACE, MODELO_YUNET
from detector import Detector, alinear, decodificar, mas_centrada
from embeddings import Embedder


def _falla(funcion, caso):
    try:
        funcion()
    except ValueError:
        return
    raise AssertionError(f"debía fallar: {caso}")


def _vector(foto, detector, embedder):
    imagen = decodificar(foto["datos"])
    caras = detector.detectar(imagen, maximo=None)
    assert caras, foto["archivo"]
    alto, ancho = imagen.shape[:2]
    alineada = alinear(imagen, mas_centrada(caras, ancho, alto)["puntos"])
    assert alineada.shape == (LADO_ALINEADO, LADO_ALINEADO, 3)
    return embedder.calcular([alineada])[0]


def _deteccion(detector):
    vacia = np.zeros((240, 320, 3), dtype=np.uint8)
    assert detector.detectar(vacia) == []
    _falla(lambda: decodificar(b"no es una imagen"), "bytes que no son imagen")
    jpg = cv2.imencode(".jpg", vacia)[1].tobytes()
    assert decodificar(jpg).shape == (240, 320, 3)
    caras = [{"caja": [0, 0, 10, 10]}, {"caja": [100, 100, 40, 40]}, {"caja": [280, 200, 40, 40]}]
    assert mas_centrada(caras, 240, 240)["caja"] == [100, 100, 40, 40]


def _identidad(fotos, detector, embedder):
    por_archivo = {}
    for foto in fotos:
        por_archivo[foto["archivo"]] = foto
    bush_1 = _vector(por_archivo["George_W_Bush_0001.jpg"], detector, embedder)
    bush_2 = _vector(por_archivo["George_W_Bush_0002.jpg"], detector, embedder)
    powell = _vector(por_archivo["Colin_Powell_0001.jpg"], detector, embedder)
    assert bush_1.shape == (DIMENSION,)
    assert abs(float(np.linalg.norm(bush_1)) - 1.0) < 1e-4
    mismo = float(bush_1 @ bush_2)
    distinto = float(bush_1 @ powell)
    assert mismo > 0.3, mismo
    assert mismo > distinto + 0.2, (mismo, distinto)
    return mismo, distinto


def main():
    if not (MODELO_YUNET.exists() and MODELO_ARCFACE.exists() and ARCHIVO_LFW.exists()):
        print("SALTADO: faltan los modelos o LFW; corre '.venv/bin/python descargas.py'")
        return
    detector = Detector()
    embedder = Embedder()
    _deteccion(detector)
    mismo, distinto = _identidad(lfw.leer(ARCHIVO_LFW), detector, embedder)
    print(f"OK: detección, alineación y embeddings (misma persona {mismo:.2f}, distinta {distinto:.2f})")


if __name__ == "__main__":
    main()
