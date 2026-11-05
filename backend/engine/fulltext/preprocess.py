import os
import re

import snowballstemmer

STOPLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stoplist.txt")
PALABRA = re.compile(r"[a-záéíóúñü]+")

_stemmer = snowballstemmer.stemmer("spanish")
_stopwords = None
_raices = {}


def stopwords():
    global _stopwords
    if _stopwords is None:
        with open(STOPLIST, encoding="utf-8") as archivo:
            _stopwords = frozenset(linea.strip() for linea in archivo if linea.strip())
    return _stopwords


def raiz(palabra):
    resultado = _raices.get(palabra)
    if resultado is None:
        resultado = _stemmer.stemWord(palabra)
        _raices[palabra] = resultado
    return resultado


def terminos(texto):
    raices = []
    vacias = stopwords()
    for palabra in PALABRA.findall(texto.lower()):
        if palabra not in vacias:
            raices.append(raiz(palabra))
    return raices


def bolsa(texto):
    frecuencias = {}
    lista = terminos(texto)
    for termino in lista:
        frecuencias[termino] = frecuencias.get(termino, 0) + 1
    return frecuencias, len(lista)
