import heapq
import json
import math
import os
import struct

from .preprocess import bolsa

LIMITE_POSTINGS = 200
FAN_IN = 64
LARGO = struct.Struct("<H")
CANTIDAD = struct.Struct("<I")
POSTING = struct.Struct("<II")
ENTRADA = struct.Struct("<IQ")
DOCUMENTO = struct.Struct("<iiId")
SUFIJOS = (".post", ".lex", ".docs", ".ftmeta")


def _escribir_entrada(archivo, termino, postings):
    datos = termino.encode()
    archivo.write(LARGO.pack(len(datos)))
    archivo.write(datos)
    archivo.write(CANTIDAD.pack(len(postings)))
    for doc, tf in postings:
        archivo.write(POSTING.pack(doc, tf))


def _leer_bloque(ruta):
    with open(ruta, "rb") as archivo:
        while True:
            cabecera = archivo.read(LARGO.size)
            if not cabecera:
                return
            termino = archivo.read(LARGO.unpack(cabecera)[0]).decode()
            cantidad = CANTIDAD.unpack(archivo.read(CANTIDAD.size))[0]
            crudo = archivo.read(cantidad * POSTING.size)
            yield termino, list(POSTING.iter_unpack(crudo))


def _escribir_bloque(diccionario, ruta):
    with open(ruta, "wb") as archivo:
        for termino in sorted(diccionario):
            _escribir_entrada(archivo, termino, diccionario[termino])
    return ruta


def _mezclar(rutas, emitir):
    lectores = []
    monticulo = []
    for posicion, ruta in enumerate(rutas):
        lector = _leer_bloque(ruta)
        lectores.append(lector)
        primero = next(lector, None)
        if primero is not None:
            heapq.heappush(monticulo, (primero[0], posicion, primero[1]))
    while monticulo:
        termino, posicion, postings = heapq.heappop(monticulo)
        juntos = list(postings)
        siguiente = next(lectores[posicion], None)
        if siguiente is not None:
            heapq.heappush(monticulo, (siguiente[0], posicion, siguiente[1]))
        while monticulo and monticulo[0][0] == termino:
            _, posicion, postings = heapq.heappop(monticulo)
            juntos.extend(postings)
            siguiente = next(lectores[posicion], None)
            if siguiente is not None:
                heapq.heappush(monticulo, (siguiente[0], posicion, siguiente[1]))
        emitir(termino, juntos)


def _borrar(rutas):
    for ruta in rutas:
        if os.path.exists(ruta):
            os.remove(ruta)


def _reducir(bloques, ruta, fan_in):
    nivel = 0
    while len(bloques) > fan_in:
        nuevos = []
        for inicio in range(0, len(bloques), fan_in):
            grupo = bloques[inicio:inicio + fan_in]
            destino = ruta + ".m" + str(nivel) + "_" + str(len(nuevos))
            with open(destino, "wb") as archivo:
                _mezclar(grupo, lambda termino, postings: _escribir_entrada(archivo, termino, postings))
            _borrar(grupo)
            nuevos.append(destino)
        bloques = nuevos
        nivel += 1
    return bloques


def construir(documentos, ruta, limite_postings=LIMITE_POSTINGS, fan_in=FAN_IN):
    documentos_leidos = []
    bloques = []
    diccionario = {}
    en_memoria = 0
    for rid, texto in documentos:
        frecuencias, longitud = bolsa(texto)
        numero = len(documentos_leidos)
        documentos_leidos.append((rid, longitud))
        for termino, tf in frecuencias.items():
            lista = diccionario.get(termino)
            if lista is None:
                lista = []
                diccionario[termino] = lista
            lista.append((numero, tf))
        en_memoria += len(frecuencias)
        if en_memoria >= limite_postings:
            bloques.append(_escribir_bloque(diccionario, ruta + ".blk" + str(len(bloques))))
            diccionario = {}
            en_memoria = 0
    if diccionario or not bloques:
        bloques.append(_escribir_bloque(diccionario, ruta + ".blk" + str(len(bloques))))
    cantidad_bloques = len(bloques)
    bloques = _reducir(bloques, ruta, fan_in)

    total = len(documentos_leidos)
    normas = [0.0] * total
    resumen = {"terminos": 0, "postings": 0}
    with open(ruta + ".post", "wb") as postings_archivo, open(ruta + ".lex", "wb") as lexico:
        def emitir(termino, postings):
            idf = math.log10(total / len(postings))
            datos = termino.encode()
            lexico.write(LARGO.pack(len(datos)))
            lexico.write(datos)
            lexico.write(ENTRADA.pack(len(postings), postings_archivo.tell()))
            for doc, tf in postings:
                postings_archivo.write(POSTING.pack(doc, tf))
                peso = math.log10(1 + tf) * idf
                normas[doc] += peso * peso
            resumen["terminos"] += 1
            resumen["postings"] += len(postings)
        _mezclar(bloques, emitir)
    _borrar(bloques)

    longitud_total = 0
    with open(ruta + ".docs", "wb") as archivo:
        for numero, (rid, longitud) in enumerate(documentos_leidos):
            archivo.write(DOCUMENTO.pack(rid[0], rid[1], longitud, math.sqrt(normas[numero])))
            longitud_total += longitud
    meta = {
        "documentos": total,
        "longitud_promedio": longitud_total / total if total else 0.0,
        "terminos": resumen["terminos"],
        "postings": resumen["postings"],
        "bloques": cantidad_bloques,
        "limite_postings": limite_postings,
    }
    with open(ruta + ".ftmeta", "w") as archivo:
        json.dump(meta, archivo)
    return meta


def destruir(ruta):
    _borrar([ruta + sufijo for sufijo in SUFIJOS])
