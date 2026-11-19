import threading

import cv2
import numpy as np

from config import CONFIANZA_DETECCION, LADO_ALINEADO, LADO_MINIMO_CARA, MAX_CARAS, MODELO_YUNET

PLANTILLA_ARCFACE = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)


def decodificar(datos):
    imagen = cv2.imdecode(np.frombuffer(datos, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ValueError("la imagen no se pudo leer")
    return imagen


def alinear(imagen, puntos):
    matriz, _ = cv2.estimateAffinePartial2D(puntos, PLANTILLA_ARCFACE, method=cv2.LMEDS)
    if matriz is None:
        raise ValueError("el rostro no se pudo alinear")
    return cv2.warpAffine(imagen, matriz, (LADO_ALINEADO, LADO_ALINEADO), borderValue=0.0)


def mas_centrada(caras, ancho, alto):
    mejor = None
    menor = None
    for cara in caras:
        x, y, w, h = cara["caja"]
        distancia = (x + w / 2 - ancho / 2) ** 2 + (y + h / 2 - alto / 2) ** 2
        if menor is None or distancia < menor:
            mejor = cara
            menor = distancia
    return mejor


class Detector:
    def __init__(self, ruta=MODELO_YUNET, confianza=CONFIANZA_DETECCION):
        self.modelo = cv2.FaceDetectorYN.create(str(ruta), "", (320, 320), confianza, 0.3, 5000)
        self.candado = threading.Lock()

    def detectar(self, imagen, maximo=MAX_CARAS):
        alto, ancho = imagen.shape[:2]
        with self.candado:
            self.modelo.setInputSize((ancho, alto))
            _, filas = self.modelo.detect(imagen)
        if filas is None:
            return []
        caras = []
        for fila in filas:
            x, y, w, h = (float(valor) for valor in fila[:4])
            if min(w, h) < LADO_MINIMO_CARA:
                continue
            izquierda = max(0, int(round(x)))
            arriba = max(0, int(round(y)))
            derecha = min(ancho, int(round(x + w)))
            abajo = min(alto, int(round(y + h)))
            caras.append({
                "caja": [izquierda, arriba, derecha - izquierda, abajo - arriba],
                "puntos": np.asarray(fila[4:14], dtype=np.float32).reshape(5, 2),
                "confianza": float(fila[14]),
            })
        caras.sort(key=lambda cara: cara["caja"][2] * cara["caja"][3], reverse=True)
        if maximo is None:
            return caras
        return caras[:maximo]
