import requests
from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import cliente_bd as bd
import personas
from cache import Cache
from config import CARPETA_FOTOS, MODELO_ARCFACE, MODELO_YUNET
from detector import Detector
from embeddings import Embedder
from personas import ErrorSolicitud
from reconocedor import Reconocedor

if not (MODELO_YUNET.exists() and MODELO_ARCFACE.exists()):
    raise SystemExit("faltan los modelos; corre '.venv/bin/python descargas.py' dentro de rostros/")

CARPETA_FOTOS.mkdir(parents=True, exist_ok=True)
detector = Detector()
embedder = Embedder()
cache = Cache()
reconocedor = Reconocedor(detector, embedder, cache)

app = FastAPI(title="Rostros")
app.mount("/fotos", StaticFiles(directory=CARPETA_FOTOS), name="fotos")


@app.exception_handler(ErrorSolicitud)
def error_de_solicitud(_, error):
    return JSONResponse(status_code=error.estado, content=error.contenido())


@app.exception_handler(bd.ErrorMotor)
def error_del_motor(_, error):
    return JSONResponse(status_code=502, content={"error": f"el motor respondió con un error: {error}"})


@app.exception_handler(requests.RequestException)
def motor_caido(_, error):
    return JSONResponse(status_code=503, content={"error": "el motor no responde"})


def leer(fotos):
    datos = []
    for foto in fotos:
        datos.append(foto.file.read())
    return datos


@app.get("/salud")
def salud():
    return {"motor": "ok" if bd.disponible() else "no disponible", "cache": cache.estado()}


@app.post("/reconocer")
def reconocer(imagen: UploadFile = File(...), usar_cache: bool = Query(True, alias="cache")):
    try:
        return reconocedor.reconocer(imagen.file.read(), usar_cache)
    except ValueError as error:
        raise ErrorSolicitud(str(error)) from None


@app.get("/personas")
def listar_personas():
    return personas.listar()


@app.post("/personas")
def registrar_persona(nombre: str = Form(...), fotos: list[UploadFile] = File(...)):
    return personas.registrar(nombre, leer(fotos), detector, embedder)


@app.get("/personas/{persona_id}")
def ver_persona(persona_id: int):
    return personas.detalle(persona_id)


@app.post("/personas/{persona_id}/fotos")
def agregar_fotos(persona_id: int, fotos: list[UploadFile] = File(...)):
    return personas.agregar_fotos(persona_id, leer(fotos), detector, embedder, cache)


@app.delete("/personas/{persona_id}")
def eliminar_persona(persona_id: int):
    return personas.eliminar_persona(persona_id, cache)


@app.delete("/rostros/{rostro_id}")
def eliminar_rostro(rostro_id: int):
    return personas.eliminar_rostro(rostro_id, cache)
