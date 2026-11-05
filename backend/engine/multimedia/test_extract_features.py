import json
import math
import os
import tempfile

import numpy as np

from .extract_features import ColeccionesMultimedia, ExtractFeatures, resolver_archivo
from .local_features import DescriptorBatch, LocalFeatureExtractor
from ..catalog import _load_tables
from ..parser.executor import Executor
from ..parser.scanner import Scanner
from ..parser.sql_parser import Parser

CENTROIDES = np.array([[0, 0], [10, 0], [0, 10]], dtype=np.float32)


class ExtractorJson(LocalFeatureExtractor):
    def __init__(self, identificador="json-2", dimension=2, entregado=None):
        self._identificador = identificador
        self._dimension = dimension
        self._entregado = entregado or identificador

    @property
    def descriptor_id(self):
        return self._identificador

    @property
    def dimension(self):
        return self._dimension

    def extract(self, path):
        with open(path, encoding="utf-8") as archivo:
            return DescriptorBatch(self._entregado, self._dimension, json.load(archivo), source=str(path))


class Vocabulario:
    def __init__(self, descriptor_id, centroids):
        self.descriptor_id = descriptor_id
        self.centroids = centroids


def _falla(funcion, texto):
    try:
        funcion()
    except ValueError as error:
        assert texto in str(error), str(error)
        return
    raise AssertionError(f"debía fallar: {texto}")


def _escribir(carpeta, nombre, descriptores):
    with open(os.path.join(carpeta, nombre), "w", encoding="utf-8") as archivo:
        json.dump(descriptores, archivo)


def _ejecutar(executor, sql):
    resultado = executor.run(Parser(Scanner(sql)).parse_program())[-1]
    assert "error" not in resultado, (sql, resultado)
    return resultado


def _resolver():
    with tempfile.TemporaryDirectory(prefix="test_extract_") as raiz:
        carpeta = os.path.join(raiz, "media")
        os.makedirs(os.path.join(carpeta, "sub"))
        _escribir(carpeta, "a.json", [])
        _escribir(carpeta, os.path.join("sub", "b.json"), [])
        _escribir(raiz, "secreto.json", [])
        real = os.path.realpath(carpeta)
        assert resolver_archivo(carpeta, "a.json") == os.path.join(real, "a.json")
        assert resolver_archivo(carpeta, "sub/b.json") == os.path.join(real, "sub", "b.json")
        assert resolver_archivo(carpeta, os.path.join(real, "a.json")) == os.path.join(real, "a.json")
        os.symlink(os.path.join(raiz, "secreto.json"), os.path.join(carpeta, "enlace.json"))
        os.makedirs(carpeta + "_hermana")
        _escribir(carpeta + "_hermana", "x.json", [])
        _falla(lambda: resolver_archivo(carpeta, "../secreto.json"), "fuera")
        _falla(lambda: resolver_archivo(carpeta, "sub/../../secreto.json"), "fuera")
        _falla(lambda: resolver_archivo(carpeta, os.path.join(raiz, "secreto.json")), "fuera")
        _falla(lambda: resolver_archivo(carpeta, "enlace.json"), "fuera")
        _falla(lambda: resolver_archivo(carpeta, "../media_hermana/x.json"), "fuera")
        _falla(lambda: resolver_archivo(carpeta, "nada.json"), "no existe")
        _falla(lambda: resolver_archivo(carpeta, "sub"), "no existe")
        _falla(lambda: resolver_archivo(carpeta, "."), "no existe")


def _extraccion():
    extractor = ExtractorJson()
    with tempfile.TemporaryDirectory(prefix="test_extract_") as carpeta:
        ruta = os.path.join(carpeta, "a.json")
        _escribir(carpeta, "a.json", [[1, 1], [9, 1], [8, 0], [0, 9]])
        extraccion = ExtractFeatures(extractor, CENTROIDES)
        assert extraccion.dimension == 3
        assert extraccion.histograma(ruta).tolist() == [1, 2, 1]
        assert ExtractFeatures(extractor, Vocabulario("json-2", CENTROIDES)).vocabulario_id == extraccion.vocabulario_id
        modelo = extraccion.ajustar([[1, 2, 1], [3, 0, 0]])
        esperado = [0.0, 2 / 4 * math.log(2), 1 / 4 * math.log(2)]
        assert np.allclose(extraccion.vector(ruta, modelo), esperado)
        _escribir(carpeta, "vacio.json", [])
        assert extraccion.histograma(os.path.join(carpeta, "vacio.json")).tolist() == [0, 0, 0]
        assert np.allclose(extraccion.vector(os.path.join(carpeta, "vacio.json"), modelo), [0, 0, 0])
        otro = ExtractFeatures(extractor, CENTROIDES + 1)
        assert otro.vocabulario_id != extraccion.vocabulario_id
        _falla(lambda: otro.vector(ruta, modelo), "otro vocabulario")
        _falla(lambda: ExtractFeatures(ExtractorJson("otro"), CENTROIDES).vector(ruta, modelo), "otro vocabulario")
        cambiado = ExtractFeatures(ExtractorJson("json-2", entregado="json-b"), CENTROIDES)
        _falla(lambda: cambiado.histograma(ruta), "json-b")
    _falla(lambda: ExtractFeatures(extractor, Vocabulario("otro", CENTROIDES)), "no se entrenó")
    _falla(lambda: ExtractFeatures(extractor, np.zeros((3, 4))), "(K, 2)")
    _falla(lambda: ExtractFeatures(extractor, np.zeros((0, 2))), "(K, 2)")


def _vector_de(tabla, identificador):
    almacen = tabla.almacenes["v"]
    fila = tabla.search("id", identificador)[0]
    posicion = almacen.id_de(fila["__rid__"])
    if posicion is None:
        return None
    return almacen.vector(posicion)


def _carga():
    with tempfile.TemporaryDirectory(prefix="test_extract_") as raiz:
        media = os.path.join(raiz, "media")
        datos = os.path.join(raiz, "datos")
        os.makedirs(media)
        os.makedirs(datos)
        _escribir(media, "a.json", [[0, 0], [10, 0], [10, 0], [0, 10]])
        _escribir(media, "b.json", [[0, 0], [0, 0], [0, 0], [0, 0]])
        _escribir(media, "c.json", [])
        colecciones = ColeccionesMultimedia(media)
        extractor = ExtractorJson()
        catalogo = {}
        executor = Executor(catalogo, data_dir=datos)
        _ejecutar(executor, "CREATE TABLE img (id INT PRIMARY KEY, ruta VARCHAR(40), v VECTOR(3));")
        _ejecutar(executor, "INSERT INTO img (id, ruta) VALUES (1, 'a.json'), (2, 'b.json'), (3, 'c.json'), (4, NULL);")
        tabla = catalogo["img"]
        _falla(lambda: colecciones.cargar(tabla, "ruta", "json-2"), "no hay un extractor")
        _falla(lambda: colecciones.vectorizar(tabla, "a.json"), "no tiene características")
        colecciones.registrar(extractor, CENTROIDES)
        _falla(lambda: colecciones.cargar(tabla, "id", "json-2"), "columna de texto")
        _falla(lambda: colecciones.cargar(tabla, "nada", "json-2"), "columna de texto")
        assert colecciones.cargar(tabla, "ruta", "json-2") == 3
        assert os.path.exists(tabla.ruta_modelo("v"))
        idf = [math.log(3 / 2), math.log(3), math.log(3)]
        assert np.allclose(_vector_de(tabla, 1), [0.25 * idf[0], 0.5 * idf[1], 0.25 * idf[2]])
        assert np.allclose(_vector_de(tabla, 2), [idf[0], 0, 0])
        assert np.allclose(_vector_de(tabla, 3), [0, 0, 0])
        assert _vector_de(tabla, 4) is None
        assert len(tabla.almacenes["v"]) == 3
        assert np.allclose(colecciones.vectorizar(tabla, "a.json"), _vector_de(tabla, 1))
        _falla(lambda: colecciones.vectorizar(tabla, "../datos/nada.json"), "fuera")
        _falla(lambda: colecciones.vectorizar(tabla, "nada.json"), "no existe")

        _ejecutar(executor, "CREATE INDEX idx ON img (v) USING HNSW WITH (METRIC=cosine, M=4);")
        _ejecutar(executor, "UPDATE img SET ruta = 'a.json' WHERE id = 2;")
        assert colecciones.cargar(tabla, "ruta", "json-2") == 3
        assert len(tabla.almacenes["v"]) == 3
        assert np.allclose(_vector_de(tabla, 1), _vector_de(tabla, 2))
        filas = _ejecutar(executor, "SELECT id FROM img WHERE SIMILAR_TO(VECTOR(0, 1, 0), k=2) USING HNSW ORDER BY id;")["rows"]
        assert filas[0]["id"] == 1 and filas[1]["id"] == 2

        previo = _vector_de(tabla, 1)
        _ejecutar(executor, "UPDATE img SET ruta = 'nada.json' WHERE id = 3;")
        _falla(lambda: colecciones.cargar(tabla, "ruta", "json-2"), "no existe")
        assert np.array_equal(_vector_de(tabla, 1), previo)

        _ejecutar(executor, "CREATE TABLE corta (id INT PRIMARY KEY, ruta VARCHAR(40), v VECTOR(5));")
        _falla(lambda: colecciones.cargar(catalogo["corta"], "ruta", "json-2"), "VECTOR(5)")
        _ejecutar(executor, "CREATE TABLE vacia (id INT PRIMARY KEY, ruta VARCHAR(40), v VECTOR(3));")
        _falla(lambda: colecciones.cargar(catalogo["vacia"], "ruta", "json-2"), "no tiene archivos")
        _ejecutar(executor, "CREATE TABLE plana (id INT PRIMARY KEY, ruta VARCHAR(40));")
        _falla(lambda: colecciones.cargar(catalogo["plana"], "ruta", "json-2"), "columna VECTOR")

        reentrenado = ColeccionesMultimedia(media)
        reentrenado.registrar(extractor, CENTROIDES + 1)
        _falla(lambda: reentrenado.vectorizar(tabla, "a.json"), "ya no está registrado")

        for nombre in list(catalogo):
            catalogo[nombre].cerrar()
        catalogo = _load_tables(datos)
        assert np.allclose(colecciones.vectorizar(catalogo["img"], "a.json"), previo)
        executor = Executor(catalogo, data_dir=datos)
        ruta_modelo = catalogo["img"].ruta_modelo("v")
        _ejecutar(executor, "DROP TABLE img;")
        assert not os.path.exists(ruta_modelo)
        for nombre in catalogo:
            catalogo[nombre].cerrar()


def main():
    _resolver()
    _extraccion()
    _carga()
    print("OK: ExtractFeatures y carga de la colección")


if __name__ == "__main__":
    main()
