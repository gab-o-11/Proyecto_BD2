import argparse
import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

import chunks
import cliente_bd as bd
import embeddings
import limpieza
import metadata
from config import (
    CARPETA_DATOS, DIMENSION, INDICE_TEXTO, INDICE_VECTORES, LOTE_INSERT, MODELO_EMBEDDINGS,
    PALABRAS_CABECERA, PALABRAS_CHUNK, SPLIT, TABLA_ARTICULOS, TABLA_CHUNKS, URL_DATASET,
)

LARGOS = {"codigo": 12, "revista": 150, "pais": 3, "url_pdf": 150}
HILOS_LLM = 8


def recortar(texto, campo):
    if texto is None:
        return None
    return texto.encode("utf-8")[:LARGOS[campo]].decode("utf-8", errors="ignore")


def carpeta_split():
    carpeta = CARPETA_DATOS / SPLIT
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def descargar(nombre):
    destino = carpeta_split() / nombre
    if destino.exists():
        return destino
    print(f"descargando {nombre}...")
    temporal = destino.with_suffix(destino.suffix + ".part")
    with requests.get(f"{URL_DATASET}/{nombre}", stream=True, timeout=120) as respuesta:
        respuesta.raise_for_status()
        with open(temporal, "wb") as archivo:
            for bloque in respuesta.iter_content(1 << 20):
                archivo.write(bloque)
    temporal.rename(destino)
    return destino


def leer_articulos(limite):
    resumenes = descargar(f"es_{SPLIT}.txt")
    comprimido = zipfile.ZipFile(descargar(f"es_{SPLIT}.zip"))
    lineas = []
    with open(resumenes, encoding="utf-8") as archivo:
        for linea in archivo:
            lineas.append(linea)
    if limite and limite < len(lineas):
        paso = len(lineas) / limite
        elegidas = []
        for indice in range(limite):
            elegidas.append(lineas[int(indice * paso)])
        lineas = elegidas
    articulos = []
    for linea in lineas:
        fila = json.loads(linea)
        nombre = f"es_{SPLIT}/{fila['id']}.txt"
        try:
            crudo = comprimido.read(nombre).decode("utf-8")
        except KeyError:
            continue
        texto = limpieza.limpiar(crudo)
        if not texto:
            continue
        fecha = fila["publication_date"].replace(".", "-")
        articulos.append({
            "id": len(articulos) + 1,
            "codigo": fila["id"],
            "pais": fila["id"].split("_")[0],
            "fecha": fecha,
            "anio": int(fecha[:4]),
            "url_pdf": fila["pdf_url"],
            "abstract": fila["abstract"],
            "texto": texto,
        })
    return articulos


def completar_metadata(articulos, usar_llm=True):
    if not usar_llm:
        for articulo in articulos:
            articulo["titulo"] = None
            articulo["autores"] = None
            articulo["revista"] = None
        return
    ruta = carpeta_split() / "metadata.jsonl"
    guardada = {}
    if ruta.exists():
        with open(ruta, encoding="utf-8") as archivo:
            for linea in archivo:
                fila = json.loads(linea)
                guardada[fila["codigo"]] = fila
    pendientes = []
    for articulo in articulos:
        if articulo["codigo"] not in guardada:
            pendientes.append(articulo)
    if pendientes:
        print(f"extrayendo metadata de {len(pendientes)} artículos con el LLM...")

        def extraer(articulo):
            cabecera = " ".join(articulo["texto"].split()[:PALABRAS_CABECERA])
            return articulo["codigo"], metadata.extraer(cabecera)

        with open(ruta, "a", encoding="utf-8") as archivo, ThreadPoolExecutor(HILOS_LLM) as hilos:
            hechos = 0
            for codigo, datos in hilos.map(extraer, pendientes):
                datos["codigo"] = codigo
                guardada[codigo] = datos
                archivo.write(json.dumps(datos, ensure_ascii=False) + "\n")
                archivo.flush()
                hechos += 1
                if hechos % 50 == 0:
                    print(f"  {hechos}/{len(pendientes)}")
    for articulo in articulos:
        datos = guardada[articulo["codigo"]]
        articulo["titulo"] = datos["titulo"] or None
        articulo["autores"] = datos["autores"] or None
        articulo["revista"] = datos["revista"] or None


def armar_chunks(articulos):
    salida = []
    for articulo in articulos:
        for orden, texto in enumerate(chunks.partir(articulo["texto"])):
            salida.append({
                "id": len(salida) + 1,
                "articulo_id": articulo["id"],
                "orden": orden,
                "pais": articulo["pais"],
                "anio": articulo["anio"],
                "texto": texto,
            })
    return salida


def calcular_embeddings(fragmentos):
    nombre_modelo = MODELO_EMBEDDINGS.split("/")[-1]
    ruta = carpeta_split() / f"embeddings_{nombre_modelo}_{PALABRAS_CHUNK}_{len(fragmentos)}.npy"
    if ruta.exists():
        vectores = np.load(ruta)
        if vectores.shape == (len(fragmentos), DIMENSION):
            return vectores
    print(f"calculando embeddings de {len(fragmentos)} chunks con {nombre_modelo} (CPU)...")
    textos = []
    for fragmento in fragmentos:
        textos.append(fragmento["texto"])
    inicio = time.time()
    vectores = embeddings.pasajes(textos, progreso=True)
    print(f"  {time.time() - inicio:.0f} s")
    np.save(ruta, vectores)
    return vectores


def crear_tablas():
    bd.ejecutar(f"DROP TABLE IF EXISTS {TABLA_CHUNKS}; DROP TABLE IF EXISTS {TABLA_ARTICULOS};")
    bd.ejecutar(
        f"CREATE TABLE {TABLA_ARTICULOS} (id INT PRIMARY KEY, codigo VARCHAR({LARGOS['codigo']}), "
        f"titulo TEXT, autores TEXT, "
        f"revista VARCHAR({LARGOS['revista']}), pais VARCHAR({LARGOS['pais']}), fecha DATE, anio INT, "
        f"url_pdf VARCHAR({LARGOS['url_pdf']}), abstract TEXT);"
    )
    bd.ejecutar(
        f"CREATE TABLE {TABLA_CHUNKS} (id INT PRIMARY KEY, articulo_id INT, orden INT, "
        f"pais VARCHAR({LARGOS['pais']}), anio INT, texto TEXT, emb VECTOR({DIMENSION}));"
    )


def insertar_por_lotes(tabla, filas, describir):
    for inicio in range(0, len(filas), LOTE_INSERT):
        valores = []
        for fila in filas[inicio:inicio + LOTE_INSERT]:
            valores.append(describir(fila))
        bd.ejecutar(f"INSERT INTO {tabla} VALUES " + ", ".join(valores) + ";")
        hechos = min(inicio + LOTE_INSERT, len(filas))
        if hechos % (LOTE_INSERT * 50) == 0 or hechos == len(filas):
            print(f"  {tabla}: {hechos}/{len(filas)}")


def fila_articulo(articulo):
    partes = [
        bd.numero_sql(articulo["id"]),
        bd.texto_sql(recortar(articulo["codigo"], "codigo")),
        bd.texto_sql(articulo["titulo"]),
        bd.texto_sql(articulo["autores"]),
        bd.texto_sql(recortar(articulo["revista"], "revista")),
        bd.texto_sql(articulo["pais"]),
        bd.texto_sql(articulo["fecha"]),
        bd.numero_sql(articulo["anio"]),
        bd.texto_sql(recortar(articulo["url_pdf"], "url_pdf")),
        bd.texto_sql(articulo["abstract"]),
    ]
    return "(" + ", ".join(partes) + ")"


def cargar(articulos, fragmentos, vectores):
    crear_tablas()
    insertar_por_lotes(TABLA_ARTICULOS, articulos, fila_articulo)

    def fila_chunk(fragmento):
        partes = [
            bd.numero_sql(fragmento["id"]),
            bd.numero_sql(fragmento["articulo_id"]),
            bd.numero_sql(fragmento["orden"]),
            bd.texto_sql(fragmento["pais"]),
            bd.numero_sql(fragmento["anio"]),
            bd.texto_sql(fragmento["texto"]),
            bd.vector_sql(vectores[fragmento["id"] - 1]),
        ]
        return "(" + ", ".join(partes) + ")"

    insertar_por_lotes(TABLA_CHUNKS, fragmentos, fila_chunk)
    print("creando índice FULLTEXT (SPIMI)...")
    print(" ", bd.ejecutar(f"CREATE INDEX {INDICE_TEXTO} ON {TABLA_CHUNKS} (texto) USING FULLTEXT;")["message"])
    print("creando índice HNSW...")
    print(" ", bd.ejecutar(f"CREATE INDEX {INDICE_VECTORES} ON {TABLA_CHUNKS} (emb) USING HNSW WITH (METRIC=cosine);")["message"])


def main():
    parser = argparse.ArgumentParser(description="Ingesta de SciELO al motor BD2")
    parser.add_argument("--limite", type=int, default=0, help="cantidad máxima de artículos (0 = todos)")
    parser.add_argument("--sin-cargar", action="store_true", help="prepara metadata y embeddings sin tocar el motor")
    parser.add_argument("--sin-llm", action="store_true", help="omite título, autores y revista (no usa la API)")
    argumentos = parser.parse_args()
    if not argumentos.sin_cargar and not bd.disponible():
        raise SystemExit("el motor no responde; levanta el backend con 'pnpm dev:backend'")
    inicio = time.time()
    articulos = leer_articulos(argumentos.limite)
    print(f"{len(articulos)} artículos leídos y limpiados")
    completar_metadata(articulos, usar_llm=not argumentos.sin_llm)
    fragmentos = armar_chunks(articulos)
    print(f"{len(fragmentos)} chunks")
    vectores = calcular_embeddings(fragmentos)
    if not argumentos.sin_cargar:
        cargar(articulos, fragmentos, vectores)
    print(f"listo en {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
