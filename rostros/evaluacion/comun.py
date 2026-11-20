import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib

matplotlib.use("Agg")

import numpy as np

import cliente_bd as bd
import esquema
import lfw
from config import ARCHIVO_EMBEDDINGS, LOTE_INSERT, RAIZ_PROYECTO

CARPETA_RESULTADOS = RAIZ_PROYECTO / "benchmarks" / "rostros_results"
TABLA_EVAL_PERSONAS = "eval_personas"
TABLA_EVAL_ROSTROS = "eval_rostros"
SEMILLA = 2026
MAX_PRUEBAS = 5
DESCONOCIDOS = 1000


def embeddings_lfw():
    if not ARCHIVO_EMBEDDINGS.exists():
        raise SystemExit("faltan los embeddings de LFW; corre 'ingesta.py' sin --limite primero")
    datos = np.load(ARCHIVO_EMBEDDINGS)
    archivos = datos["archivos"].tolist()
    vectores = datos["vectores"]
    detectadas = datos["detectadas"]
    por_persona = {}
    for posicion, archivo in enumerate(archivos):
        if detectadas[posicion]:
            por_persona.setdefault(lfw.persona_de(archivo), []).append(posicion)
    return archivos, vectores, por_persona


def particion(por_persona, n, rng):
    conocidas = []
    for persona in sorted(por_persona):
        if len(por_persona[persona]) >= n + 1:
            conocidas.append(persona)
    registros = []
    pruebas = []
    for persona_id, persona in enumerate(conocidas, start=1):
        posiciones = list(por_persona[persona])
        rng.shuffle(posiciones)
        for posicion in posiciones[:n]:
            registros.append({"persona_id": persona_id, "persona": persona, "posicion": posicion})
        for posicion in posiciones[n:n + MAX_PRUEBAS]:
            pruebas.append({"verdad": persona_id, "posicion": posicion})
    return registros, pruebas


def desconocidos(por_persona, rng):
    unicas = []
    for persona in sorted(por_persona):
        if len(por_persona[persona]) == 1:
            unicas.append(por_persona[persona][0])
    rng.shuffle(unicas)
    salida = []
    for posicion in unicas[:DESCONOCIDOS]:
        salida.append({"verdad": None, "posicion": posicion})
    return salida


def insertar(tabla, valores, lote):
    for inicio in range(0, len(valores), lote):
        bd.ejecutar(f"INSERT INTO {tabla} VALUES " + ", ".join(valores[inicio:inicio + lote]) + ";")


def cargar_galeria(registros, vectores):
    esquema.borrar(TABLA_EVAL_PERSONAS, TABLA_EVAL_ROSTROS)
    esquema.crear_tablas(TABLA_EVAL_PERSONAS, TABLA_EVAL_ROSTROS)
    nombres = {}
    for registro in registros:
        nombres[registro["persona_id"]] = lfw.nombre_visible(registro["persona"])
    personas = []
    for persona_id, nombre in nombres.items():
        personas.append(f"({persona_id}, {bd.texto_sql(nombre)}, 'lfw')")
    insertar(TABLA_EVAL_PERSONAS, personas, LOTE_INSERT * 5)
    rostros = []
    for rostro_id, registro in enumerate(registros, start=1):
        rostros.append(f"({rostro_id}, {registro['persona_id']}, 'eval', {bd.vector_sql(vectores[registro['posicion']])})")
    insertar(TABLA_EVAL_ROSTROS, rostros, LOTE_INSERT)
    esquema.crear_indices(TABLA_EVAL_ROSTROS)


def borrar_galeria():
    esquema.borrar(TABLA_EVAL_PERSONAS, TABLA_EVAL_ROSTROS)


def percentil(valores, p):
    return float(np.percentile(np.asarray(valores, dtype=float), p))


def guardar_csv(nombre, filas):
    CARPETA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    with open(CARPETA_RESULTADOS / nombre, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)


def guardar_json(nombre, datos):
    CARPETA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    (CARPETA_RESULTADOS / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
