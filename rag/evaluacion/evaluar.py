import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import buscador
import embeddings
from config import CARPETA_DATOS, RAIZ_PROYECTO, SPLIT

CORTES = (1, 5, 10)
SALIDA = RAIZ_PROYECTO / "benchmarks" / "rag_results"


def posicion(ids, objetivo):
    for indice, identificador in enumerate(ids, start=1):
        if identificador == objetivo:
            return indice
    return None


def percentil(valores, p):
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, int(round(p / 100 * len(ordenados) + 0.5)) - 1))
    return ordenados[indice]


def resumir(modo, filas):
    resumen = {"modo": modo, "preguntas": len(filas)}
    for nivel in ("chunk", "articulo"):
        reciprocos = []
        for fila in filas:
            rango = fila[f"rango_{nivel}"]
            reciprocos.append(0.0 if rango is None else 1.0 / rango)
        resumen[f"mrr_{nivel}"] = round(statistics.mean(reciprocos), 4)
        for corte in CORTES:
            aciertos = 0
            for fila in filas:
                rango = fila[f"rango_{nivel}"]
                if rango is not None and rango <= corte:
                    aciertos += 1
            resumen[f"recall@{corte}_{nivel}"] = round(aciertos / len(filas), 4)
    latencias = []
    for fila in filas:
        latencias.append(fila["ms"])
    resumen["ms_promedio"] = round(statistics.mean(latencias), 1)
    resumen["ms_p95"] = round(percentil(latencias, 95), 1)
    return resumen


def main():
    parser = argparse.ArgumentParser(description="Evalúa la recuperación BM25, embeddings e híbrida")
    parser.add_argument("--k", type=int, default=max(CORTES))
    argumentos = parser.parse_args()
    ruta = CARPETA_DATOS / SPLIT / "preguntas.jsonl"
    preguntas = []
    with open(ruta, encoding="utf-8") as archivo:
        for linea in archivo:
            preguntas.append(json.loads(linea))
    embeddings.modelo()
    detalle = []
    resumenes = []
    for modo in buscador.MODOS:
        filas = []
        for pregunta in preguntas:
            inicio = time.perf_counter()
            fragmentos, _ = buscador.recuperar(pregunta["pregunta"], modo, argumentos.k)
            milisegundos = (time.perf_counter() - inicio) * 1000
            chunks = []
            articulos = []
            for fragmento in fragmentos:
                chunks.append(fragmento["id"])
                if fragmento["articulo_id"] not in articulos:
                    articulos.append(fragmento["articulo_id"])
            fila = {
                "modo": modo,
                "pregunta_id": pregunta["id"],
                "rango_chunk": posicion(chunks, pregunta["chunk_id"]),
                "rango_articulo": posicion(articulos, pregunta["articulo_id"]),
                "ms": round(milisegundos, 1),
            }
            filas.append(fila)
            detalle.append(fila)
        resumen = resumir(modo, filas)
        resumenes.append(resumen)
        print(json.dumps(resumen, ensure_ascii=False))
    SALIDA.mkdir(parents=True, exist_ok=True)
    with open(SALIDA / "resumen.csv", "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(resumenes[0]))
        escritor.writeheader()
        escritor.writerows(resumenes)
    with open(SALIDA / "detalle.csv", "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(detalle[0]))
        escritor.writeheader()
        escritor.writerows(detalle)
    print(f"resultados en {SALIDA}")


if __name__ == "__main__":
    main()
