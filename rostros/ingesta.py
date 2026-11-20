import argparse
import shutil
import time

import cv2
import numpy as np

import cliente_bd as bd
import descargas
import esquema
import lfw
from cache import Cache
from config import (
    ARCHIVO_EMBEDDINGS, CARPETA_FOTOS, CARPETA_IMPORTAR, CARPETA_PROPIAS, DIMENSION, LARGO_NOMBRE, LOTE_INSERT,
    TABLA_PERSONAS, TABLA_ROSTROS,
)
from detector import Detector, alinear, decodificar, mas_centrada
from embeddings import Embedder

LOTE_EMBEDDINGS = 64
EXTENSIONES = (".jpg", ".jpeg", ".png")


def alinear_principal(datos, detector, centrada):
    try:
        imagen = decodificar(datos)
    except ValueError:
        return None
    caras = detector.detectar(imagen, maximo=None)
    if not caras:
        return None
    alto, ancho = imagen.shape[:2]
    cara = mas_centrada(caras, ancho, alto) if centrada else caras[0]
    try:
        return alinear(imagen, cara["puntos"])
    except ValueError:
        return None


def vectorizar(fotos, detector, embedder, centrada):
    vectores = np.zeros((len(fotos), DIMENSION), dtype=np.float32)
    detectadas = np.zeros(len(fotos), dtype=bool)
    pendientes = []
    posiciones = []
    inicio = time.time()
    for posicion, foto in enumerate(fotos):
        alineada = alinear_principal(foto["datos"], detector, centrada)
        if alineada is not None:
            pendientes.append(alineada)
            posiciones.append(posicion)
        if pendientes and (len(pendientes) == LOTE_EMBEDDINGS or posicion == len(fotos) - 1):
            vectores[posiciones] = embedder.calcular(pendientes)
            detectadas[posiciones] = True
            pendientes = []
            posiciones = []
        if (posicion + 1) % 1000 == 0:
            print(f"  {posicion + 1}/{len(fotos)} fotos ({time.time() - inicio:.0f} s)")
    return vectores, detectadas


def vectores_lfw(fotos, detector, embedder, guardar):
    archivos = []
    for foto in fotos:
        archivos.append(foto["archivo"])
    archivos = np.array(archivos)
    if ARCHIVO_EMBEDDINGS.exists():
        guardado = np.load(ARCHIVO_EMBEDDINGS)
        if np.array_equal(guardado["archivos"], archivos):
            return guardado["vectores"], guardado["detectadas"]
    print(f"calculando embeddings de {len(fotos)} fotos de LFW (CPU)...")
    vectores, detectadas = vectorizar(fotos, detector, embedder, centrada=True)
    if guardar:
        np.savez(ARCHIVO_EMBEDDINGS, archivos=archivos, vectores=vectores, detectadas=detectadas)
    return vectores, detectadas


def fotos_carpeta():
    fotos = []
    if not CARPETA_IMPORTAR.exists():
        return fotos
    for carpeta in sorted(CARPETA_IMPORTAR.iterdir()):
        if not carpeta.is_dir():
            continue
        for ruta in sorted(carpeta.iterdir()):
            if ruta.suffix.lower() not in EXTENSIONES:
                continue
            try:
                imagen = decodificar(ruta.read_bytes())
            except ValueError:
                print(f"  se omite {ruta}: no se pudo leer")
                continue
            fotos.append({"archivo": ruta.name, "persona": carpeta.name, "datos": cv2.imencode(".jpg", imagen)[1].tobytes()})
    return fotos


def recortar(nombre):
    return nombre.encode("utf-8")[:LARGO_NOMBRE].decode("utf-8", errors="ignore")


def armar(grupos):
    personas = []
    rostros = []
    ids = {}
    for origen, fotos, vectores, detectadas in grupos:
        for foto, vector, detectada in zip(fotos, vectores, detectadas):
            if not detectada:
                continue
            clave = (origen, foto["persona"])
            if clave not in ids:
                ids[clave] = len(ids) + 1
                personas.append({"id": ids[clave], "nombre": recortar(lfw.nombre_visible(foto["persona"])), "origen": origen})
            rostro_id = len(rostros) + 1
            if origen == "lfw":
                archivo = f"lfw/{foto['persona']}/{foto['archivo']}"
            else:
                archivo = f"propias/{ids[clave]}/{rostro_id}.jpg"
            rostros.append({"id": rostro_id, "persona_id": ids[clave], "archivo": archivo, "vector": vector, "datos": foto["datos"]})
    return personas, rostros


def guardar_fotos(rostros):
    for rostro in rostros:
        destino = CARPETA_FOTOS / rostro["archivo"]
        if destino.exists():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(rostro["datos"])


def insertar_por_lotes(tabla, filas, describir, lote):
    for inicio in range(0, len(filas), lote):
        valores = []
        for fila in filas[inicio:inicio + lote]:
            valores.append(describir(fila))
        bd.ejecutar(f"INSERT INTO {tabla} VALUES " + ", ".join(valores) + ";")
        hechos = min(inicio + lote, len(filas))
        if hechos % (lote * 50) == 0 or hechos == len(filas):
            print(f"  {tabla}: {hechos}/{len(filas)}")


def fila_persona(persona):
    return f"({bd.numero_sql(persona['id'])}, {bd.texto_sql(persona['nombre'])}, {bd.texto_sql(persona['origen'])})"


def fila_rostro(rostro):
    return (
        f"({bd.numero_sql(rostro['id'])}, {bd.numero_sql(rostro['persona_id'])}, "
        f"{bd.texto_sql(rostro['archivo'])}, {bd.vector_sql(rostro['vector'])})"
    )


def main():
    parser = argparse.ArgumentParser(description="Carga LFW y las fotos de data/rostros/carpeta en el motor BD2")
    parser.add_argument("--reiniciar", action="store_true", help="borra las tablas, las personas registradas y sus fotos antes de cargar")
    parser.add_argument("--limite", type=int, default=0, help="cantidad máxima de fotos de LFW (0 = todas)")
    argumentos = parser.parse_args()
    if not bd.disponible():
        raise SystemExit("el motor no responde; levanta el backend con 'pnpm dev:backend'")
    if esquema.existen() and not argumentos.reiniciar:
        raise SystemExit(
            f"las tablas '{TABLA_PERSONAS}' o '{TABLA_ROSTROS}' ya existen; "
            "usa --reiniciar para recrearlas (borra también las personas registradas desde la app)"
        )
    descargas.modelos()
    fotos = lfw.leer(descargas.lfw())
    if argumentos.limite:
        fotos = fotos[:argumentos.limite]
    detector = Detector()
    embedder = Embedder()
    vectores, detectadas = vectores_lfw(fotos, detector, embedder, guardar=not argumentos.limite)
    propias = fotos_carpeta()
    vectores_propias, detectadas_propias = vectorizar(propias, detector, embedder, centrada=False)
    personas, rostros = armar([
        ("lfw", fotos, vectores, detectadas),
        ("propia", propias, vectores_propias, detectadas_propias),
    ])
    print(
        f"{int(detectadas.sum())}/{len(fotos)} fotos de LFW y "
        f"{int(detectadas_propias.sum())}/{len(propias)} fotos propias con rostro detectado"
    )
    if argumentos.reiniciar:
        esquema.borrar()
        shutil.rmtree(CARPETA_PROPIAS, ignore_errors=True)
        Cache().limpiar()
    esquema.crear_tablas()
    guardar_fotos(rostros)
    insertar_por_lotes(TABLA_PERSONAS, personas, fila_persona, LOTE_INSERT * 5)
    insertar_por_lotes(TABLA_ROSTROS, rostros, fila_rostro, LOTE_INSERT)
    print("creando índices HNSW y HASH...")
    esquema.crear_indices()
    print(f"listo: {len(personas)} personas y {len(rostros)} rostros en el motor")


if __name__ == "__main__":
    main()
