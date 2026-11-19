import cv2
import numpy as np
import onnxruntime as ort

from config import DIMENSION, LADO_ALINEADO, MODELO_ARCFACE


class Embedder:
    def __init__(self, ruta=MODELO_ARCFACE):
        self.sesion = ort.InferenceSession(str(ruta), providers=["CPUExecutionProvider"])
        self.entrada = self.sesion.get_inputs()[0].name

    def calcular(self, alineadas):
        if not alineadas:
            return np.zeros((0, DIMENSION), dtype=np.float32)
        lote = cv2.dnn.blobFromImages(
            alineadas, 1.0 / 127.5, (LADO_ALINEADO, LADO_ALINEADO), (127.5, 127.5, 127.5), swapRB=True
        )
        salida = self.sesion.run(None, {self.entrada: lote})[0].astype(np.float32)
        normas = np.linalg.norm(salida, axis=1, keepdims=True)
        return salida / np.maximum(normas, 1e-12)
