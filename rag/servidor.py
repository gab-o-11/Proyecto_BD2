import json
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import buscador
import cliente_bd as bd
import embeddings
import generador
from config import K_CONTEXTO, MODELO_EMBEDDINGS, MODELO_LLM, RAIZ_RAG, TABLA_ARTICULOS, TABLA_CHUNKS

PAISES = {
    "bol": "Bolivia", "col": "Colombia", "esp": "España", "per": "Perú",
    "pry": "Paraguay", "scl": "Chile", "ury": "Uruguay",
}

app = FastAPI(title="RAG SciELO")
app.mount("/static", StaticFiles(directory=RAIZ_RAG / "web"), name="static")


class Mensaje(BaseModel):
    rol: str
    contenido: str


class Filtros(BaseModel):
    pais: str | None = None
    desde: int | None = None
    hasta: int | None = None


class Pregunta(BaseModel):
    mensajes: list[Mensaje]
    modo: str = "hibrido"
    k: int = Field(default=K_CONTEXTO, ge=1, le=10)
    filtros: Filtros = Field(default_factory=Filtros)


@app.on_event("startup")
def precargar():
    embeddings.modelo()


@app.get("/")
def inicio():
    return FileResponse(RAIZ_RAG / "web" / "index.html")


@app.get("/api/estado")
def estado():
    salida = {"motor": bd.disponible(), "llm": MODELO_LLM, "embeddings": MODELO_EMBEDDINGS, "articulos": 0, "chunks": 0}
    if not salida["motor"]:
        return salida
    try:
        salida["articulos"] = bd.filas(f"SELECT COUNT(*) FROM {TABLA_ARTICULOS};")[0]["conteo"]
        salida["chunks"] = bd.filas(f"SELECT COUNT(*) FROM {TABLA_CHUNKS};")[0]["conteo"]
    except bd.ErrorMotor:
        pass
    return salida


@app.get("/api/paises")
def paises():
    try:
        filas = bd.filas(f"SELECT pais, COUNT(*) FROM {TABLA_ARTICULOS} GROUP BY pais;")
    except bd.ErrorMotor:
        return []
    salida = []
    for fila in filas:
        salida.append({"codigo": fila["pais"], "nombre": PAISES.get(fila["pais"], fila["pais"]), "articulos": fila["conteo"]})
    salida.sort(key=lambda pais: pais["nombre"])
    return salida


def linea(datos):
    return json.dumps(datos, ensure_ascii=False) + "\n"


def fuente_publica(fuente):
    articulo = fuente["articulo"]
    return {
        "numero": fuente["numero"],
        "chunk_id": fuente["id"],
        "orden": fuente["orden"],
        "texto": fuente["texto"],
        "puntaje": fuente["puntaje"],
        "posiciones": fuente["posiciones"],
        "titulo": articulo.get("titulo"),
        "autores": articulo.get("autores"),
        "revista": articulo.get("revista"),
        "anio": articulo.get("anio"),
        "pais": PAISES.get(articulo.get("pais"), articulo.get("pais")),
        "url_pdf": articulo.get("url_pdf"),
    }


@app.post("/api/preguntar")
def preguntar(pregunta: Pregunta):
    mensajes = []
    for mensaje in pregunta.mensajes:
        mensajes.append({"rol": mensaje.rol, "contenido": mensaje.contenido})

    def flujo():
        inicio = time.perf_counter()
        try:
            fuentes, tiempos = buscador.buscar(mensajes, pregunta.modo, pregunta.k, pregunta.filtros.model_dump())
        except (bd.ErrorMotor, ValueError) as error:
            yield linea({"tipo": "error", "mensaje": str(error)})
            return
        tiempos["recuperacion_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
        publicas = []
        for fuente in fuentes:
            publicas.append(fuente_publica(fuente))
        yield linea({"tipo": "fuentes", "fuentes": publicas, "tiempos": tiempos})
        inicio_llm = time.perf_counter()
        primero = None
        uso = None
        try:
            for parte in generador.responder(mensajes, fuentes):
                if isinstance(parte, dict):
                    uso = parte
                    continue
                if primero is None:
                    primero = round((time.perf_counter() - inicio_llm) * 1000, 1)
                yield linea({"tipo": "texto", "delta": parte})
        except Exception as error:
            yield linea({"tipo": "error", "mensaje": f"error del LLM: {error}"})
            return
        tiempos["primer_token_ms"] = primero
        tiempos["total_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
        yield linea({"tipo": "fin", "tiempos": tiempos, "tokens": uso})

    return StreamingResponse(flujo(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn
    from config import PUERTO

    uvicorn.run(app, host="127.0.0.1", port=PUERTO)
