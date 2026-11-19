import time

import cliente_bd as bd
import embeddings
from config import K_CANDIDATOS, K_CONTEXTO, RRF_K, TABLA_ARTICULOS, TABLA_CHUNKS

MODOS = ("bm25", "vectorial", "hibrido")
MENSAJES_PARA_BUSCAR = 3
COLUMNAS_CHUNK = "id, articulo_id, orden, texto"


def texto_de_busqueda(mensajes):
    preguntas = []
    for mensaje in mensajes:
        if mensaje["rol"] == "usuario":
            preguntas.append(mensaje["contenido"])
    return " ".join(preguntas[-MENSAJES_PARA_BUSCAR:])


def condiciones(filtros):
    partes = []
    if filtros.get("pais"):
        partes.append("pais = " + bd.texto_sql(filtros["pais"]))
    if filtros.get("desde"):
        partes.append("anio >= " + bd.numero_sql(int(filtros["desde"])))
    if filtros.get("hasta"):
        partes.append("anio <= " + bd.numero_sql(int(filtros["hasta"])))
    salida = ""
    for parte in partes:
        salida += " AND " + parte
    return salida


def bm25(texto, k, filtros):
    sql = (
        f"SELECT {COLUMNAS_CHUNK}, SCORE() AS puntaje FROM {TABLA_CHUNKS} "
        f"WHERE MATCH(texto, {bd.texto_sql(texto)}){condiciones(filtros)} USING BM25 LIMIT {k};"
    )
    try:
        return bd.filas(sql)
    except bd.ErrorMotor:
        return []


def vectorial(texto, k, filtros):
    vector = embeddings.consulta(texto)
    sql = (
        f"SELECT {COLUMNAS_CHUNK}, SIMILARITY_SCORE() AS puntaje FROM {TABLA_CHUNKS} "
        f"WHERE SIMILAR_TO({bd.vector_sql(vector)}, k={k}){condiciones(filtros)} "
        f"USING HNSW WITH METRIC=cosine;"
    )
    return bd.filas(sql)


def fusionar(listas, k):
    puntajes = {}
    filas = {}
    posiciones = {}
    for nombre, lista in listas.items():
        for posicion, fila in enumerate(lista, start=1):
            identificador = fila["id"]
            puntajes[identificador] = puntajes.get(identificador, 0.0) + 1.0 / (RRF_K + posicion)
            filas.setdefault(identificador, fila)
            posiciones.setdefault(identificador, {})[nombre] = posicion
    ordenados = sorted(puntajes, key=lambda identificador: puntajes[identificador], reverse=True)
    salida = []
    for identificador in ordenados[:k]:
        fila = dict(filas[identificador])
        fila["puntaje"] = puntajes[identificador]
        fila["posiciones"] = posiciones[identificador]
        salida.append(fila)
    return salida


def recuperar(texto, modo="hibrido", k=K_CONTEXTO, filtros=None, candidatos=K_CANDIDATOS):
    filtros = filtros or {}
    if modo not in MODOS:
        raise ValueError(f"modo desconocido '{modo}'; usa {', '.join(MODOS)}")
    tiempos = {}
    listas = {}
    if modo in ("bm25", "hibrido"):
        inicio = time.perf_counter()
        listas["bm25"] = bm25(texto, candidatos, filtros)
        tiempos["bm25_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
    if modo in ("vectorial", "hibrido"):
        inicio = time.perf_counter()
        listas["vectorial"] = vectorial(texto, candidatos, filtros)
        tiempos["vectorial_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
    if modo == "hibrido":
        resultado = fusionar(listas, k)
    else:
        resultado = []
        for posicion, fila in enumerate(listas[modo][:k], start=1):
            fila = dict(fila)
            fila["posiciones"] = {modo: posicion}
            resultado.append(fila)
    return resultado, tiempos


def articulos_de(fragmentos):
    ids = set()
    for fragmento in fragmentos:
        ids.add(fragmento["articulo_id"])
    if not ids:
        return {}
    filas = bd.filas(
        f"SELECT id, codigo, titulo, autores, revista, pais, anio, url_pdf FROM {TABLA_ARTICULOS} "
        f"WHERE id IN {bd.lista_sql(sorted(ids))};"
    )
    salida = {}
    for fila in filas:
        salida[fila["id"]] = fila
    return salida


def buscar(mensajes, modo="hibrido", k=K_CONTEXTO, filtros=None):
    texto = texto_de_busqueda(mensajes)
    fragmentos, tiempos = recuperar(texto, modo, k, filtros)
    articulos = articulos_de(fragmentos)
    fuentes = []
    for numero, fragmento in enumerate(fragmentos, start=1):
        fuente = dict(fragmento)
        fuente["numero"] = numero
        fuente["articulo"] = articulos.get(fragmento["articulo_id"], {})
        fuentes.append(fuente)
    return fuentes, tiempos
