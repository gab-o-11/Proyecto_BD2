import math
import os
import random
import tempfile

from . import spimi
from .inverted_index import IndiceInvertido
from .preprocess import bolsa, terminos
from .ranking import B, BM25, K1, TF_IDF, bm25, buscar, tfidf_coseno

PALABRAS = ("banca digital tecnología financiera inflación crecimiento económico sostenibilidad energías renovables "
            "criptomonedas blockchain crédito vivienda pandemia alianzas regulación mercado empresas clientes "
            "innovación pagos móviles tasas interés exportaciones minería agricultura turismo").split()
CONSULTAS = ("banca digital", "inflación y crecimiento económico", "energías renovables sostenibilidad", "blockchain",
             "crédito para vivienda durante la pandemia", "palabrainexistente", "la de que")


def _corpus(cantidad, semilla=11):
    generador = random.Random(semilla)
    documentos = []
    for numero in range(cantidad):
        palabras = []
        for _ in range(generador.randint(3, 60)):
            palabras.append(generador.choice(PALABRAS))
        documentos.append(((numero + 1, numero % 7), "El informe dice que " + " ".join(palabras) + "."))
    return documentos


def _cerca(a, b):
    assert abs(a - b) <= 1e-9 * max(1.0, abs(b)), (a, b)


def _fuerza_bruta(documentos, consulta, metodo):
    bolsas = []
    for _, texto in documentos:
        bolsas.append(bolsa(texto))
    total = len(bolsas)
    df = {}
    for frecuencias, _ in bolsas:
        for termino in frecuencias:
            df[termino] = df.get(termino, 0) + 1
    promedio = sum(longitud for _, longitud in bolsas) / total
    consulta_bolsa, _ = bolsa(consulta)
    puntajes = {}
    if metodo == TF_IDF:
        pesos_consulta = {}
        for termino, tf in consulta_bolsa.items():
            if termino in df:
                pesos_consulta[termino] = math.log10(1 + tf) * math.log10(total / df[termino])
        norma_consulta = math.sqrt(sum(p * p for p in pesos_consulta.values()))
        for doc, (frecuencias, _) in enumerate(bolsas):
            pesos = {}
            for termino, tf in frecuencias.items():
                pesos[termino] = math.log10(1 + tf) * math.log10(total / df[termino])
            norma = math.sqrt(sum(p * p for p in pesos.values()))
            punto = sum(peso * pesos.get(termino, 0.0) for termino, peso in pesos_consulta.items())
            if punto > 0:
                puntajes[doc] = punto / (norma_consulta * norma)
    else:
        for doc, (frecuencias, longitud) in enumerate(bolsas):
            valor = 0.0
            for termino, tf_consulta in consulta_bolsa.items():
                tf = frecuencias.get(termino, 0)
                if tf == 0:
                    continue
                idf = math.log((total - df[termino] + 0.5) / (df[termino] + 0.5) + 1)
                valor += tf_consulta * idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * longitud / promedio))
            if valor > 0:
                puntajes[doc] = valor
    return sorted(((v, d) for d, v in puntajes.items()), key=lambda par: (-par[0], par[1]))


def _preprocesamiento():
    assert terminos("La INFLACIÓN y la inflación, en el Perú!") == ["inflacion", "inflacion", "peru"]
    frecuencias, longitud = bolsa("Banca digital: la banca crece")
    assert frecuencias == {"banc": 2, "digital": 1, "crec": 1} and longitud == 4
    assert bolsa("de la que el") == ({}, 0)


def _comparar(indice, documentos):
    for consulta in CONSULTAS:
        for metodo in (TF_IDF, BM25):
            esperado = _fuerza_bruta(documentos, consulta, metodo)
            obtenido = buscar(indice, consulta, metodo)
            assert len(obtenido) == len(esperado), (consulta, metodo)
            for (valor, doc), (valor_esperado, doc_esperado) in zip(obtenido, esperado):
                _cerca(valor, valor_esperado)
                assert doc == doc_esperado, (consulta, metodo)
            top = buscar(indice, consulta, metodo, 5)
            assert top == obtenido[:5]


def _spimi():
    documentos = _corpus(400)
    with tempfile.TemporaryDirectory() as carpeta:
        unico = os.path.join(carpeta, "unico")
        varios = os.path.join(carpeta, "varios")
        multinivel = os.path.join(carpeta, "multinivel")
        meta_unico = spimi.construir(iter(documentos), unico, limite_postings=10**9)
        meta_varios = spimi.construir(iter(documentos), varios, limite_postings=300)
        meta_multinivel = spimi.construir(iter(documentos), multinivel, limite_postings=50, fan_in=4)
        assert meta_unico["bloques"] == 1
        assert meta_varios["bloques"] > 5
        assert meta_multinivel["bloques"] > 16
        for sufijo in (".post", ".lex", ".docs"):
            with open(unico + sufijo, "rb") as a, open(varios + sufijo, "rb") as b, open(multinivel + sufijo, "rb") as c:
                contenido = a.read()
                assert contenido == b.read() == c.read(), sufijo
        sobrantes = []
        for nombre in os.listdir(carpeta):
            if os.path.splitext(nombre)[1] not in spimi.SUFIJOS:
                sobrantes.append(nombre)
        assert sobrantes == [], sobrantes

        indice = IndiceInvertido(varios)
        assert indice.documentos == 400
        assert indice.rid(0) == (1, 0) and indice.rid(399) == (400, 399 % 7)
        assert indice.df("banc") == sum(1 for _, texto in documentos if "banca" in texto)
        assert indice.postings("noexiste") == []
        postings = indice.postings("inflacion")
        assert [doc for doc, _ in postings] == sorted(doc for doc, _ in postings)
        _comparar(indice, documentos)
        assert indice.bytes_en_disco() > 0
        spimi.destruir(varios)
        assert not os.path.exists(varios + ".post")


def _bm25_intuicion():
    documentos = [
        ((1, 0), "inflación " * 4 + "precios " * 196),
        ((2, 0), "inflación " * 10 + "precios " * 2990),
        ((3, 0), "deporte fútbol"),
    ]
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "intuicion")
        spimi.construir(iter(documentos), ruta)
        indice = IndiceInvertido(ruta)
        assert [doc for _, doc in bm25(indice, "inflación")] == [0, 1]
        assert bm25(indice, "inflación", b=0.0)[0][1] == 1
        assert tfidf_coseno(indice, "deporte")[0][1] == 2


def _vacio():
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "vacio")
        meta = spimi.construir(iter([]), ruta)
        assert meta["documentos"] == 0
        indice = IndiceInvertido(ruta)
        assert buscar(indice, "banca", TF_IDF) == [] and buscar(indice, "banca", BM25) == []


def main():
    _preprocesamiento()
    _spimi()
    _bm25_intuicion()
    _vacio()
    print("OK: preprocesamiento, SPIMI con uno, varios bloques y merge multinivel, TF-IDF + coseno y BM25 contra fuerza bruta")


if __name__ == "__main__":
    main()
