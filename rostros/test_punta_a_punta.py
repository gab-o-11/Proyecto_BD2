import os
import tempfile

os.environ["ROSTROS_TABLA_PERSONAS"] = "prueba_personas"
os.environ["ROSTROS_TABLA_ROSTROS"] = "prueba_rostros"
os.environ["ROSTROS_FOTOS"] = tempfile.mkdtemp(prefix="rostros_prueba_")

import cv2
import fakeredis
import numpy as np

import cliente_bd as bd
import esquema
import lfw
from config import ARCHIVO_LFW, CARPETA_FOTOS, MODELO_ARCFACE, MODELO_YUNET, URL_MOTOR
from detector import Detector, decodificar


def _fotos_de_una_cara(cantidad):
    detector = Detector()
    elegidas = []
    for foto in lfw.leer(ARCHIVO_LFW):
        if foto["persona"] != "George_W_Bush":
            continue
        if len(detector.detectar(decodificar(foto["datos"]), maximo=None)) == 1:
            elegidas.append(foto["datos"])
        if len(elegidas) == cantidad:
            return elegidas
    raise AssertionError("LFW no tiene suficientes fotos de una sola cara")


def _archivos(fotos):
    salida = []
    for indice, datos in enumerate(fotos, start=1):
        salida.append(("fotos", (f"{indice}.jpg", datos, "image/jpeg")))
    return salida


def _reconocer(cliente, datos, usar_cache):
    valor = "true" if usar_cache else "false"
    respuesta = cliente.post(f"/reconocer?cache={valor}", files={"imagen": ("cuadro.jpg", datos, "image/jpeg")})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["caras"][0]


def _flujo(cliente, fotos):
    respuesta = cliente.post("/personas", data={"nombre": "Prueba Rostros"}, files=_archivos(fotos[:5]))
    assert respuesta.status_code == 200, respuesta.text
    persona = respuesta.json()
    assert persona["nombre"] == "Prueba Rostros" and len(persona["fotos"]) == 5
    assert (CARPETA_FOTOS / persona["fotos"][0]["archivo"]).exists()

    cara = _reconocer(cliente, fotos[5], False)
    assert cara["persona_id"] == persona["id"] and cara["fuente"] == "motor", cara
    _reconocer(cliente, fotos[5], True)
    cara = _reconocer(cliente, fotos[5], True)
    assert cara["persona_id"] == persona["id"] and cara["fuente"] == "cache", cara

    repetida = cliente.post("/personas", data={"nombre": "Prueba Rostros"}, files=_archivos(fotos[:5]))
    assert repetida.status_code == 400 and "ya existe" in repetida.json()["error"], repetida.text
    vacia = cv2.imencode(".jpg", np.zeros((240, 320, 3), dtype=np.uint8))[1].tobytes()
    sin_cara = cliente.post("/personas", data={"nombre": "Otra"}, files=_archivos(fotos[:2] + [vacia] + fotos[3:5]))
    assert sin_cara.status_code == 400 and sin_cara.json()["foto"] == 3, sin_cara.text
    incompleta = cliente.post("/personas", data={"nombre": "Otra"}, files=_archivos(fotos[:2]))
    assert incompleta.status_code == 400, incompleta.text

    listado = cliente.get("/personas").json()
    assert len(listado) == 1 and listado[0]["id"] == persona["id"] and listado[0]["fotos"] == 5, listado

    primera = persona["fotos"][0]
    borrada = cliente.delete(f"/rostros/{primera['id']}").json()
    assert borrada["persona_eliminada"] is False, borrada
    assert not (CARPETA_FOTOS / primera["archivo"]).exists()
    assert len(cliente.get(f"/personas/{persona['id']}").json()["fotos"]) == 4

    agregada = cliente.post(f"/personas/{persona['id']}/fotos", files=_archivos([fotos[6]]))
    assert agregada.status_code == 200 and len(agregada.json()["fotos"]) == 5, agregada.text

    assert cliente.delete(f"/personas/{persona['id']}").status_code == 200
    assert cliente.get(f"/personas/{persona['id']}").status_code == 404
    cara = _reconocer(cliente, fotos[5], True)
    assert cara["persona_id"] is None and cara["fuente"] == "motor", cara
    assert bd.filas("SELECT COUNT(*) FROM prueba_rostros;")[0]["conteo"] == 0
    assert bd.filas("SELECT COUNT(*) FROM prueba_personas;")[0]["conteo"] == 0
    assert cliente.get("/salud").json()["motor"] == "ok"


def main():
    if not (MODELO_YUNET.exists() and MODELO_ARCFACE.exists() and ARCHIVO_LFW.exists()):
        print("SALTADO: faltan los modelos o LFW; corre '.venv/bin/python descargas.py'")
        return
    if not bd.disponible():
        print(f"SALTADO: el motor no responde en {URL_MOTOR}; levanta 'pnpm dev:backend'")
        return
    from fastapi.testclient import TestClient

    import servidor

    servidor.cache.cliente = fakeredis.FakeRedis()
    servidor.cache.limpiar()
    fotos = _fotos_de_una_cara(7)
    esquema.borrar()
    esquema.crear_tablas()
    esquema.crear_indices()
    try:
        _flujo(TestClient(servidor.app), fotos)
    finally:
        esquema.borrar()
    print("OK: registro, reconocimiento por motor y caché, validaciones y borrado de fotos y personas")


if __name__ == "__main__":
    main()
