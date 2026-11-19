import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel

import cliente_bd as bd
import llm
from config import CARPETA_DATOS, SPLIT, TABLA_CHUNKS

INSTRUCCIONES = """Recibes un fragmento de un artículo científico en español.
Escribe UNA pregunta que alguien haría a un buscador de artículos y que este fragmento responde.

Reglas:
- La pregunta debe entenderse sola, sin ver el fragmento: nombra el tema concreto
  (enfermedad, especie, población, lugar, técnica), nunca digas "el estudio" o "el artículo".
- Parafrasea: no copies frases ni combinaciones de palabras poco comunes del fragmento.
  Usa sinónimos cuando sea natural.
- Máximo 25 palabras, en español.
- Marca util=false si el fragmento es solo bibliografía, afiliaciones, agradecimientos,
  una tabla sin contexto o texto ilegible. En ese caso deja la pregunta vacía."""

HILOS = 8


class Generada(BaseModel):
    util: bool
    pregunta: str


def muestrear(cantidad, semilla):
    total = bd.filas(f"SELECT COUNT(*) FROM {TABLA_CHUNKS};")[0]["conteo"]
    azar = random.Random(semilla)
    ids = azar.sample(range(1, total + 1), min(total, cantidad))
    filas = []
    for inicio in range(0, len(ids), 200):
        filas.extend(bd.filas(
            f"SELECT id, articulo_id, texto FROM {TABLA_CHUNKS} WHERE id IN {bd.lista_sql(ids[inicio:inicio + 200])};"
        ))
    filas.sort(key=lambda fila: ids.index(fila["id"]))
    return filas


def generar(fila):
    resultado = llm.estructurado(INSTRUCCIONES, fila["texto"], Generada)
    return fila, resultado


def main():
    parser = argparse.ArgumentParser(description="Genera preguntas de evaluación a partir de chunks al azar")
    parser.add_argument("--cantidad", type=int, default=200)
    parser.add_argument("--semilla", type=int, default=2026)
    argumentos = parser.parse_args()
    candidatos = muestrear(int(argumentos.cantidad * 1.3), argumentos.semilla)
    destino = CARPETA_DATOS / SPLIT / "preguntas.jsonl"
    destino.parent.mkdir(parents=True, exist_ok=True)
    guardadas = 0
    descartadas = 0
    with open(destino, "w", encoding="utf-8") as archivo, ThreadPoolExecutor(HILOS) as hilos:
        for fila, resultado in hilos.map(generar, candidatos):
            if guardadas >= argumentos.cantidad:
                break
            if not resultado.util or not resultado.pregunta.strip():
                descartadas += 1
                continue
            archivo.write(json.dumps({
                "id": guardadas + 1,
                "pregunta": resultado.pregunta.strip(),
                "chunk_id": fila["id"],
                "articulo_id": fila["articulo_id"],
            }, ensure_ascii=False) + "\n")
            guardadas += 1
    print(f"{guardadas} preguntas en {destino} ({descartadas} chunks descartados)")


if __name__ == "__main__":
    main()
