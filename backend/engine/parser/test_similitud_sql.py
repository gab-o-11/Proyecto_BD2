import os
import tempfile

import numpy as np

from .executor import Executor
from .scanner import Scanner
from .sql_parser import ParseError, Parser
from .nodes import DEFAULT_SCORE_COLUMN, And, SimilarTo, VectorLiteral
from .visitor import PrintVisitor
from ..catalog import _load_tables, table_info


def _parse(sql):
    return Parser(Scanner(sql)).parse_program()


def _ida_y_vuelta(sql):
    ast = _parse(sql)
    assert ast == _parse(PrintVisitor().render(ast)), sql
    return ast[0]


def _rechaza(sql):
    try:
        _parse(sql)
    except ParseError:
        return
    raise AssertionError(f"debía rechazarse: {sql}")


def _similar_to():
    nodo = _ida_y_vuelta("SELECT * FROM imagenes WHERE SIMILAR_TO('foto_consulta.jpg', k=10);")
    assert nodo.where == SimilarTo("foto_consulta.jpg", 10)
    nodo = _ida_y_vuelta("SELECT * FROM imagenes WHERE tipo = 'a' AND similar_to('it''s.jpg', K=5);")
    assert isinstance(nodo.where, And) and nodo.where.conditions[1] == SimilarTo("it's.jpg", 5)
    for sql in [
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg')",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', 10)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', x=10)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', k=0)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', k=-1)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', k=1.5)",
        "SELECT * FROM t WHERE SIMILAR_TO(columna, k=5)",
        "SELECT * FROM t ORDER BY SIMILAR_TO('a.jpg', k=5)",
    ]:
        _rechaza(sql)


def _using():
    nodo = _ida_y_vuelta("SELECT * FROM imagenes WHERE SIMILAR_TO('q.jpg', k=10) USING HNSW WITH METRIC=cosine;")
    assert nodo.index_method == "HNSW" and nodo.search_options == (("METRIC", "cosine"),)
    nodo = _ida_y_vuelta("SELECT * FROM c WHERE SIMILAR_TO('q.mp3', k=5) using ivf with metric=EUCLIDEAN, probes=8 ORDER BY id DESC LIMIT 3;")
    assert nodo.index_method == "IVF" and nodo.search_options == (("METRIC", "euclidean"), ("PROBES", 8))
    assert nodo.order_by == "id" and nodo.limit == 3
    nodo = _ida_y_vuelta("SELECT * FROM c WHERE SIMILAR_TO('q', k=5) USING SEQ;")
    assert nodo.index_method == "SEQ" and nodo.search_options == ()
    nodo = _ida_y_vuelta("SELECT * FROM c WHERE SIMILAR_TO('q', k=5) USING HNSW WITH EF_SEARCH=100, METRIC=dot;")
    assert nodo.search_options == (("EF_SEARCH", 100), ("METRIC", "dot"))
    assert _parse("SELECT * FROM c WHERE SIMILAR_TO('q', k=5);")[0].index_method is None
    for sql in [
        "SELECT * FROM t USING HNSW",
        "SELECT * FROM t WHERE id = 1 USING HNSW",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING BPLUS",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING HNSW WITH",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING HNSW WITH METRIC=manhattan",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING HNSW WITH METRIC=3",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING HNSW WITH EF_SEARCH=0",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING HNSW WITH EF_SEARCH=cosine",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING HNSW WITH OTRA=1",
        "SELECT * FROM t WHERE SIMILAR_TO('q', k=5) USING HNSW WITH METRIC=dot, METRIC=cosine",
    ]:
        _rechaza(sql)


def _score():
    nodo = _ida_y_vuelta("SELECT nombre, artista, SIMILARITY_SCORE() AS score FROM canciones WHERE SIMILAR_TO('audio_query.mp3', k=5) USING IVF WITH METRIC=euclidean ORDER BY score DESC;")
    assert nodo.columns == ["nombre", "artista"] and nodo.projection == ["nombre", "artista", "score"]
    assert nodo.score_column == "score" and nodo.order_by == "score" and nodo.order_desc
    nodo = _ida_y_vuelta("SELECT similarity_score() FROM t WHERE SIMILAR_TO('q', k=1);")
    assert nodo.score_column == DEFAULT_SCORE_COLUMN and nodo.columns == []
    nodo = _ida_y_vuelta("SELECT *, SIMILARITY_SCORE() AS s FROM t WHERE SIMILAR_TO('q', k=1) USING SEQ;")
    assert nodo.columns is None and nodo.score_column == "s" and nodo.projection is None
    nodo = _ida_y_vuelta("SELECT SIMILARITY_SCORE() AS s, id FROM t WHERE SIMILAR_TO('q', k=1);")
    assert nodo.projection == ["s", "id"]
    assert _parse("SELECT * FROM t WHERE SIMILAR_TO('q', k=1);")[0].score_column is None
    for sql in [
        "SELECT SIMILARITY_SCORE() FROM t",
        "SELECT SIMILARITY_SCORE() FROM t WHERE id = 1",
        "SELECT SIMILARITY_SCORE(x) FROM t WHERE SIMILAR_TO('q', k=1)",
        "SELECT SIMILARITY_SCORE() AS FROM t WHERE SIMILAR_TO('q', k=1)",
        "SELECT SIMILARITY_SCORE(), SIMILARITY_SCORE() AS b FROM t WHERE SIMILAR_TO('q', k=1)",
        "SELECT COUNT(*), SIMILARITY_SCORE() FROM t WHERE SIMILAR_TO('q', k=1)",
        "SELECT *, id FROM t WHERE SIMILAR_TO('q', k=1)",
        "SELECT *, COUNT(*) FROM t WHERE SIMILAR_TO('q', k=1)",
        "SELECT id AS x FROM t WHERE SIMILAR_TO('q', k=1)",
    ]:
        _rechaza(sql)


def _vector():
    nodo = _ida_y_vuelta("CREATE TABLE imagenes (id INT PRIMARY KEY, nombre VARCHAR(50), embedding VECTOR(512) NOT NULL);")
    columna = nodo.columns[2]
    assert columna.type == "VECTOR" and columna.size == 512 and columna.not_null
    nodo = _ida_y_vuelta("INSERT INTO imagenes VALUES (1, 'a', VECTOR(0.5, -1, 2e-3));")
    assert nodo.values[2] == VectorLiteral((0.5, -1.0, 0.002))
    nodo = _ida_y_vuelta("UPDATE imagenes SET embedding = VECTOR(1, 2, 3) WHERE id = 1;")
    assert nodo.assignments[0][1] == VectorLiteral((1.0, 2.0, 3.0))
    nodo = _ida_y_vuelta("SELECT * FROM imagenes WHERE SIMILAR_TO(VECTOR(1, 0, 0), k=3) USING HNSW;")
    assert nodo.where == SimilarTo(VectorLiteral((1.0, 0.0, 0.0)), 3)
    nodo = _ida_y_vuelta("CREATE INDEX idx ON imagenes (embedding) USING HNSW WITH (METRIC=cosine, M=16, EF_CONSTRUCTION=64);")
    assert nodo.kind == "HNSW" and nodo.options == (("METRIC", "cosine"), ("M", 16), ("EF_CONSTRUCTION", 64))
    nodo = _ida_y_vuelta("CREATE INDEX idx ON imagenes (embedding) USING IVF WITH (LISTS=100, METRIC=euclidean);")
    assert nodo.kind == "IVF" and nodo.options == (("LISTS", 100), ("METRIC", "euclidean"))
    assert _ida_y_vuelta("CREATE INDEX idx ON imagenes (embedding) USING HNSW;").options == ()
    assert _ida_y_vuelta("CREATE INDEX idx ON clientes (nombre) USING BPLUS;").options == ()
    for sql in [
        "CREATE TABLE t (v VECTOR)",
        "CREATE TABLE t (v VECTOR(0))",
        "CREATE TABLE t (v VECTOR(1.5))",
        "INSERT INTO t VALUES (VECTOR())",
        "INSERT INTO t VALUES (VECTOR('a'))",
        "INSERT INTO t VALUES (VECTOR(1, 1e999))",
        "SELECT * FROM t WHERE id = VECTOR(1)",
        "CREATE INDEX i ON t (v) USING GRAFO",
        "CREATE INDEX i ON t (v) USING BPLUS WITH (METRIC=cosine)",
        "CREATE INDEX i ON t (v) WITH (METRIC=cosine)",
        "CREATE INDEX i ON t (v) USING HNSW WITH METRIC=cosine",
        "CREATE INDEX i ON t (v) USING HNSW WITH (LISTS=3)",
        "CREATE INDEX i ON t (v) USING IVF WITH (M=3)",
        "CREATE INDEX i ON t (v) USING IVF WITH (METRIC=cosine, METRIC=dot)",
    ]:
        _rechaza(sql)


def _ejecutar(executor, sql):
    resultados = executor.run(_parse(sql))
    assert "error" not in resultados[-1], (sql, resultados[-1])
    return resultados[-1]


def _error(executor, sql, texto):
    resultado = executor.run(_parse(sql))[-1]
    assert "error" in resultado, (sql, resultado)
    assert texto in resultado["error"], (sql, resultado["error"])


def _columna_vector():
    with tempfile.TemporaryDirectory(prefix="test_similitud_") as carpeta:
        catalogo = {}
        executor = Executor(catalogo, data_dir=carpeta)
        _ejecutar(executor, "CREATE TABLE img (id INT PRIMARY KEY, nombre VARCHAR(20), v VECTOR(3));")
        _ejecutar(executor, "INSERT INTO img VALUES (1, 'a', VECTOR(1, 0, 0)), (2, 'b', VECTOR(0, 1, 0));")
        _ejecutar(executor, "INSERT INTO img (id, nombre) VALUES (3, 'c');")
        _ejecutar(executor, "INSERT INTO img (id, v, nombre) VALUES (4, VECTOR(0, 0, 1), 'd');")
        tabla = catalogo["img"]
        almacen = tabla.almacenes["v"]
        assert tabla.columns == ["id", "nombre"] and len(almacen) == 3
        filas = _ejecutar(executor, "SELECT * FROM img ORDER BY id;")
        assert filas["columns"] == ["id", "nombre"] and len(filas["rows"]) == 4
        assert table_info(tabla)["columns"][-1] == {"name": "v", "type": "vector"}
        _error(executor, "SELECT v FROM img;", "no existe")
        _error(executor, "INSERT INTO img VALUES (5, 'e', VECTOR(1, 2));", "dimensión 3")
        _error(executor, "INSERT INTO img VALUES (5, 'e', 7);", "requiere VECTOR")
        _error(executor, "INSERT INTO img VALUES (VECTOR(1), 'e', VECTOR(1, 2, 3));", "no es de tipo VECTOR")
        _error(executor, "INSERT INTO img VALUES (5, 'e', VECTOR(1, 2, 1e50));", "rango")
        _error(executor, "INSERT INTO img VALUES (5, 'e');", "se esperaban 3 valores")
        _ejecutar(executor, "UPDATE img SET v = VECTOR(5, 5, 5) WHERE id = 3;")
        assert len(almacen) == 4
        fila = tabla.search("id", 3)[0]
        assert np.array_equal(almacen.vector(almacen.id_de(fila["__rid__"])), [5, 5, 5])
        _ejecutar(executor, "UPDATE img SET v = NULL WHERE id = 3;")
        assert len(almacen) == 3 and almacen.id_de(fila["__rid__"]) is None
        _ejecutar(executor, "UPDATE img SET nombre = 'z', v = VECTOR(9, 9, 9) WHERE id = 1;")
        fila = tabla.search("id", 1)[0]
        assert fila["nombre"] == "z" and np.array_equal(almacen.vector(almacen.id_de(fila["__rid__"])), [9, 9, 9])
        _ejecutar(executor, "DELETE FROM img WHERE id = 2;")
        assert len(almacen) == 2
        _ejecutar(executor, "INSERT INTO img VALUES (6, 'f', VECTOR(7, 7, 7));")
        assert len(almacen) == 3
        tabla.cerrar()
        catalogo = _load_tables(carpeta)
        reabierta = catalogo["img"]
        assert len(reabierta.almacenes["v"]) == 3 and reabierta.columnas_declaradas() == ["id", "nombre", "v"]
        fila = reabierta.search("id", 6)[0]
        assert np.array_equal(reabierta.almacenes["v"].vector(reabierta.almacenes["v"].id_de(fila["__rid__"])), [7, 7, 7])
        executor = Executor(catalogo, data_dir=carpeta)
        _ejecutar(executor, "CREATE TABLE obligatoria (id INT, v VECTOR(2) NOT NULL);")
        _error(executor, "INSERT INTO obligatoria (id) VALUES (1);", "no admite NULL")
        _error(executor, "CREATE TABLE p (v VECTOR(2) PRIMARY KEY, id INT);", "PRIMARY KEY")
        _error(executor, "CREATE TABLE c (id INT PRIMARY KEY, v VECTOR(2)) USING BPLUS_CLUSTERED;", "BPLUS_CLUSTERED")
        _error(executor, "CREATE TABLE s (v VECTOR(2));", "columna escalar")
        _error(Executor({}), "CREATE TABLE m (id INT, v VECTOR(2));", "en disco")
        _ejecutar(executor, "DROP TABLE img;")
        restantes = os.listdir(carpeta)
        assert not any(nombre.startswith("img") for nombre in restantes), restantes


def main():
    _columna_vector()
    _similar_to()
    _using()
    _score()
    _vector()
    print("OK: SQL de similitud")


if __name__ == "__main__":
    main()
