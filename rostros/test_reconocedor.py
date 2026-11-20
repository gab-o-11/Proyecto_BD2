import cv2
import fakeredis
import numpy as np

import reconocedor
from cache import Cache
from detector import PLANTILLA_ARCFACE
from reconocedor import Reconocedor, decidir, mejores_por_persona


class DetectorFalso:
    def detectar(self, imagen, maximo=5):
        return [{"caja": [10, 20, 100, 100], "puntos": PLANTILLA_ARCFACE + 20, "confianza": 0.9}]


class EmbedderFalso:
    def __init__(self, vector):
        self.vector = vector

    def calcular(self, alineadas):
        filas = []
        for _ in alineadas:
            filas.append(self.vector)
        return np.array(filas, dtype=np.float32).reshape(len(alineadas), len(self.vector))


class MotorFalso:
    def __init__(self, score):
        self.score = score
        self.consultas = 0

    def buscar(self, vector, metodo="HNSW", k=5, tabla_rostros=None):
        self.consultas += 1
        return [{"persona_id": 7, "archivo": "lfw/x.jpg", "score": self.score}], {"motor": 1.0, "motor_http": 2.0}

    def nombre(self, persona_id, tabla_personas=None):
        return "Ana", {"motor": 0.5, "motor_http": 1.0}


def _mejores_y_decision():
    filas = [
        {"persona_id": 1, "archivo": "a", "score": 0.5},
        {"persona_id": 2, "archivo": "b", "score": 0.7},
        {"persona_id": 1, "archivo": "c", "score": 0.6},
    ]
    mejores = mejores_por_persona(filas)
    resumen = []
    for fila in mejores:
        resumen.append((fila["persona_id"], fila["archivo"]))
    assert resumen == [(2, "b"), (1, "c")]
    assert decidir([], 0.4) == (None, None)
    assert decidir(mejores, 0.8) == (None, 0.7)
    ganador, score = decidir(mejores, 0.4)
    assert ganador["persona_id"] == 2 and score == 0.7


def _reconocer():
    vector = np.zeros(512, dtype=np.float32)
    vector[0] = 1.0
    motor = MotorFalso(0.9)
    reconocedor.buscar_en_motor = motor.buscar
    reconocedor.nombre_de = motor.nombre
    cache = Cache(fakeredis.FakeRedis())
    cache.limpiar()
    servicio = Reconocedor(DetectorFalso(), EmbedderFalso(vector), cache, umbral=0.4, umbral_cache=0.55)
    cuadro = cv2.imencode(".jpg", np.zeros((300, 300, 3), dtype=np.uint8))[1].tobytes()

    primera = servicio.reconocer(cuadro)
    cara = primera["caras"][0]
    assert cara["nombre"] == "Ana" and cara["fuente"] == "motor" and cara["caja"] == [10, 20, 100, 100]
    assert primera["cache"] == "activa" and set(primera["tiempos"]) == set(reconocedor.ETAPAS)
    assert (primera["ancho"], primera["alto"]) == (300, 300)

    segunda = servicio.reconocer(cuadro)["caras"][0]
    assert segunda["fuente"] == "cache" and segunda["persona_id"] == 7 and motor.consultas == 1

    sin_cache = servicio.reconocer(cuadro, usar_cache=False)
    assert sin_cache["cache"] == "desactivada" and sin_cache["caras"][0]["fuente"] == "motor" and motor.consultas == 2

    motor.score = 0.1
    cache.limpiar()
    desconocido = servicio.reconocer(cuadro)["caras"][0]
    assert desconocido["persona_id"] is None and desconocido["nombre"] is None and desconocido["similitud"] == 0.1


def main():
    _mejores_y_decision()
    _reconocer()
    print("OK: mejor coincidencia por persona, umbral, caché y desconocidos")


if __name__ == "__main__":
    main()
