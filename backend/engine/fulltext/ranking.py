import heapq
import math

from .preprocess import bolsa

TF_IDF = "TF_IDF"
BM25 = "BM25"
METODOS = (TF_IDF, BM25)
K1 = 1.2
B = 0.75


def _mejores(puntajes, k):
    pares = []
    for doc, valor in puntajes.items():
        if valor > 0:
            pares.append((-valor, doc))
    if k is None:
        pares.sort()
    else:
        pares = heapq.nsmallest(k, pares)
    resultado = []
    for valor, doc in pares:
        resultado.append((-valor, doc))
    return resultado


def tfidf_coseno(indice, consulta, k=None):
    frecuencias, _ = bolsa(consulta)
    pesos = {}
    suma = 0.0
    for termino, tf in frecuencias.items():
        df = indice.df(termino)
        if df == 0:
            continue
        idf = math.log10(indice.documentos / df)
        peso = math.log10(1 + tf) * idf
        if peso > 0:
            pesos[termino] = (peso, idf)
            suma += peso * peso
    if suma == 0:
        return []
    norma_consulta = math.sqrt(suma)
    acumulado = {}
    for termino, (peso, idf) in pesos.items():
        for doc, tf in indice.postings(termino):
            acumulado[doc] = acumulado.get(doc, 0.0) + peso * math.log10(1 + tf) * idf
    for doc in acumulado:
        acumulado[doc] = acumulado[doc] / (norma_consulta * indice.normas[doc])
    return _mejores(acumulado, k)


def bm25(indice, consulta, k=None, k1=K1, b=B):
    frecuencias, _ = bolsa(consulta)
    promedio = indice.longitud_promedio or 1.0
    acumulado = {}
    for termino, tf_consulta in frecuencias.items():
        df = indice.df(termino)
        if df == 0:
            continue
        idf = math.log((indice.documentos - df + 0.5) / (df + 0.5) + 1)
        for doc, tf in indice.postings(termino):
            normalizacion = k1 * (1 - b + b * indice.longitudes[doc] / promedio)
            aporte = tf_consulta * idf * tf * (k1 + 1) / (tf + normalizacion)
            acumulado[doc] = acumulado.get(doc, 0.0) + aporte
    return _mejores(acumulado, k)


def buscar(indice, consulta, metodo, k=None, k1=K1, b=B):
    if metodo == TF_IDF:
        return tfidf_coseno(indice, consulta, k)
    return bm25(indice, consulta, k, k1, b)
