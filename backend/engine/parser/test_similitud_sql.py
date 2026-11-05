import os
import tempfile

import numpy as np

from .executor import Executor
from .scanner import Scanner
from .sql_parser import ParseError, Parser
from .nodes import DEFAULT_SCORE_COLUMN, And, SimilarTo, VectorLiteral
from .visitor import PrintVisitor
from ..catalog import _load_tables, table_info
from ..vectorial.exacta import knn_exacto
from ..vectorial.metricas import COSINE, DOT, EUCLIDEAN, distancias, score


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


def _literal(vector):
    partes = []
    for valor in vector:
        partes.append(str(float(valor)))
    return "VECTOR(" + ", ".join(partes) + ")"


def _datos(n=120, dimension=6, semilla=0):
    azar = np.random.default_rng(semilla)
    centros = azar.random((5, dimension)) * 4
    return centros[azar.integers(0, 5, n)] + azar.normal(0, 0.2, (n, dimension))


def _tabla_con_datos(executor, datos):
    _ejecutar(executor, f"CREATE TABLE img (id INT PRIMARY KEY, grupo INT, v VECTOR({datos.shape[1]}));")
    filas = []
    for i, vector in enumerate(datos):
        filas.append(f"({i}, {i % 3}, {_literal(vector)})")
    _ejecutar(executor, "INSERT INTO img VALUES " + ", ".join(filas) + ";")


def _crear_indices():
    with tempfile.TemporaryDirectory(prefix="test_similitud_") as carpeta:
        catalogo = {}
        executor = Executor(catalogo, data_dir=carpeta)
        _error(executor, "CREATE TABLE _x (id INT, v VECTOR(2)); CREATE INDEX i ON _x (v) USING IVF;", "IVF necesita datos")
        _tabla_con_datos(executor, _datos())
        mensaje = _ejecutar(executor, "CREATE INDEX ih ON img (v) USING HNSW WITH (METRIC=cosine, M=8, EF_CONSTRUCTION=32);")["message"]
        assert "120 entradas" in mensaje and "HNSW" in mensaje
        _ejecutar(executor, "CREATE INDEX iv ON img (v) USING IVF WITH (METRIC=euclidean, LISTS=10);")
        _ejecutar(executor, "CREATE INDEX idef ON img (v) USING HNSW WITH (METRIC=dot);")
        tabla = catalogo["img"]
        assert tabla.indices_vectoriales["ih"].estructura.m == 8
        assert tabla.indices_vectoriales["iv"].estructura.lists == 10
        assert tabla.indices_vectoriales["idef"].metrica == "dot"
        assert "iv" in [i["name"] for i in table_info(tabla)["indexes"]]
        _error(executor, "CREATE INDEX ih ON img (v) USING IVF;", "ya existe")
        _error(executor, "CREATE INDEX otro ON img (v) USING HNSW WITH (METRIC=cosine);", "ya tiene")
        _error(executor, "CREATE INDEX x ON img (grupo) USING HNSW;", "no es una columna VECTOR")
        _error(executor, "CREATE INDEX x ON img (v) USING BPLUS;", "solo admite índices IVF o HNSW")
        _error(executor, "CREATE INDEX x ON img (v);", "solo admite índices IVF o HNSW")
        _error(executor, "CREATE INDEX x ON img (v) USING IVF WITH (LISTS=9999);", "lists debe estar")
        _error(executor, "CREATE INDEX x ON img (v) USING HNSW WITH (METRIC=euclidean, M=1);", "m debe ser")
        ruta = tabla.indices_vectoriales["iv"].ruta
        assert os.path.exists(ruta)
        entradas = tabla.indices_vectoriales["ih"].estructura.indice.ntotal
        for t in catalogo.values():
            t.cerrar()
        catalogo = _load_tables(carpeta)
        tabla = catalogo["img"]
        assert sorted(tabla.indices_vectoriales) == ["idef", "ih", "iv"]
        assert tabla.indices_vectoriales["ih"].estructura.indice.ntotal == entradas == 120
        assert tabla.indices_vectoriales["iv"].metrica == "euclidean" and tabla.indices_vectoriales["iv"].estructura.lists == 10
        executor = Executor(catalogo, data_dir=carpeta)
        _ejecutar(executor, "DROP INDEX iv;")
        assert not os.path.exists(ruta) and "iv" not in tabla.indices_vectoriales
        _error(executor, "DROP INDEX iv;", "no existe")
        _ejecutar(executor, "DROP TABLE img;")
        assert not any(nombre.startswith("img") for nombre in os.listdir(carpeta))


def _ids(resultado):
    salida = []
    for fila in resultado["rows"]:
        salida.append(fila["id"])
    return salida


def _plan(resultado):
    salida = []
    for paso in resultado["plan"]:
        salida.append(paso["op"])
    return salida


def _busquedas():
    datos = _datos(200, 6).astype(np.float32)
    with tempfile.TemporaryDirectory(prefix="test_similitud_") as carpeta:
        catalogo = {}
        executor = Executor(catalogo, data_dir=carpeta)
        _tabla_con_datos(executor, datos)
        consulta = datos[7]
        q = _literal(consulta)
        for metrica in (EUCLIDEAN, COSINE, DOT):
            exacto = knn_exacto(consulta, datos, 10, metrica)
            esperados = []
            for _, identificador in exacto:
                esperados.append(identificador)
            resultado = _ejecutar(executor, f"SELECT id, SIMILARITY_SCORE() AS score FROM img WHERE SIMILAR_TO({q}, k=10) USING SEQ WITH METRIC={metrica};")
            assert _ids(resultado) == esperados, metrica
            assert resultado["columns"] == ["id", "score"] and "Seq Scan" in _plan(resultado)
            for fila, (valor, _) in zip(resultado["rows"], exacto):
                assert abs(fila["score"] - score(valor, metrica)) < 1e-5
            _ejecutar(executor, f"CREATE INDEX h_{metrica} ON img (v) USING HNSW WITH (METRIC={metrica});")
            _ejecutar(executor, f"CREATE INDEX i_{metrica} ON img (v) USING IVF WITH (METRIC={metrica});")
            resultado = _ejecutar(executor, f"SELECT id FROM img WHERE SIMILAR_TO({q}, k=10) USING HNSW WITH METRIC={metrica}, EF_SEARCH=200;")
            assert "Vector Index Scan" in _plan(resultado) and len(set(_ids(resultado)) & set(esperados)) >= 9
            lists = catalogo["img"].indices_vectoriales["i_" + metrica].estructura.lists
            resultado = _ejecutar(executor, f"SELECT id FROM img WHERE SIMILAR_TO({q}, k=10) USING IVF WITH METRIC={metrica}, PROBES={lists};")
            assert "Vector Index Scan" in _plan(resultado) and _ids(resultado) == esperados
        resultado = _ejecutar(executor, f"SELECT id, SIMILARITY_SCORE() AS score FROM img WHERE SIMILAR_TO({q}, k=5) USING HNSW WITH METRIC=cosine ORDER BY score DESC;")
        puntajes = []
        for fila in resultado["rows"]:
            puntajes.append(fila["score"])
        assert puntajes == sorted(puntajes, reverse=True) and resultado["rows"][0]["id"] == 7
        resultado = _ejecutar(executor, f"SELECT id, SIMILARITY_SCORE() AS score FROM img WHERE SIMILAR_TO({q}, k=5) USING SEQ WITH METRIC=euclidean ORDER BY score ASC;")
        assert resultado["rows"][-1]["id"] == 7 and abs(resultado["rows"][-1]["score"] - 1.0) < 1e-6
        resultado = _ejecutar(executor, f"SELECT *, SIMILARITY_SCORE() FROM img WHERE SIMILAR_TO({q}, k=3) USING SEQ;")
        assert resultado["columns"] == ["id", "grupo", "similarity_score"] and len(resultado["rows"]) == 3
        resultado = _ejecutar(executor, f"SELECT * FROM img WHERE SIMILAR_TO({q}, k=3) USING SEQ ORDER BY similarity_score DESC LIMIT 2;")
        assert resultado["columns"] == ["id", "grupo"] and _ids(resultado)[0] == 7 and len(resultado["rows"]) == 2
        resultado = _ejecutar(executor, f"SELECT id FROM img WHERE SIMILAR_TO({q}, k=500) USING SEQ;")
        assert len(resultado["rows"]) == 200
        resultado = _ejecutar(executor, f"SELECT id, grupo FROM img WHERE grupo = 1 AND SIMILAR_TO({q}, k=10) USING SEQ;")
        todos = _ejecutar(executor, f"SELECT id, grupo FROM img WHERE SIMILAR_TO({q}, k=10) USING SEQ;")
        cumplen = []
        for fila in todos["rows"]:
            if fila["grupo"] == 1:
                cumplen.append(fila["id"])
        assert _ids(resultado) == cumplen and len(cumplen) < 10 and "Filter" in _plan(resultado)
        _ejecutar(executor, "DROP INDEX h_cosine;")
        resultado = _ejecutar(executor, f"SELECT id FROM img WHERE SIMILAR_TO({q}, k=3) USING HNSW WITH METRIC=cosine;")
        assert "Seq Scan" in _plan(resultado) and "Vector Index Scan" not in _plan(resultado)
        _error(executor, f"SELECT id FROM img WHERE SIMILAR_TO({q}, k=3) USING SEQ WITH EF_SEARCH=5;", "EF_SEARCH")
        _error(executor, f"SELECT id FROM img WHERE SIMILAR_TO({q}, k=3) USING HNSW WITH PROBES=5;", "PROBES")
        _error(executor, "SELECT id FROM img WHERE SIMILAR_TO(VECTOR(1, 2), k=3);", "dimensión 6")
        _error(executor, "SELECT id FROM img WHERE SIMILAR_TO('foto.jpg', k=3);", "extractor")
        _error(executor, f"SELECT id FROM img WHERE grupo = 1 OR SIMILAR_TO({q}, k=3);", "AND")
        _error(executor, f"SELECT id FROM img WHERE NOT SIMILAR_TO({q}, k=3);", "AND")
        _error(executor, f"SELECT id FROM img WHERE SIMILAR_TO({q}, k=3) AND SIMILAR_TO({q}, k=4);", "un solo")
        _error(executor, f"SELECT a.id FROM img a JOIN img b ON a.id = b.id WHERE SIMILAR_TO({q}, k=3);", "JOIN")
        _error(executor, f"SELECT id, SIMILARITY_SCORE() AS grupo FROM img WHERE SIMILAR_TO({q}, k=3);", "coincide")
        _error(executor, f"DELETE FROM img WHERE SIMILAR_TO({q}, k=3);", "solo se admite en SELECT")
        _error(executor, f"UPDATE img SET grupo = 1 WHERE SIMILAR_TO({q}, k=3);", "solo se admite en SELECT")
        _ejecutar(executor, "CREATE TABLE plana (id INT);")
        _error(executor, f"SELECT id FROM plana WHERE SIMILAR_TO({q}, k=3);", "columna VECTOR")
        _ejecutar(executor, "CREATE TABLE doble (id INT, a VECTOR(2), b VECTOR(2));")
        _error(executor, "SELECT id FROM doble WHERE SIMILAR_TO(VECTOR(1, 2), k=3);", "exactamente una")
        _ejecutar(executor, "CREATE TABLE vacia (id INT, v VECTOR(2));")
        assert _ejecutar(executor, "SELECT id FROM vacia WHERE SIMILAR_TO(VECTOR(1, 2), k=3);")["rows"] == []
        _ejecutar(executor, "CREATE INDEX vacio ON vacia (v) USING HNSW;")
        assert _ejecutar(executor, "SELECT id FROM vacia WHERE SIMILAR_TO(VECTOR(1, 2), k=3) USING HNSW;")["rows"] == []
        rutas = []

        def vectorizador(tabla, ruta):
            rutas.append((tabla.name, ruta))
            return consulta

        def sin_archivo(tabla, ruta):
            raise FileNotFoundError(f"el archivo '{ruta}' no se pudo leer")

        def fuera(tabla, ruta):
            raise ValueError(f"la ruta '{ruta}' está fuera de la carpeta multimedia")

        con_archivo = Executor(catalogo, data_dir=carpeta, vectorizador=vectorizador)
        resultado = _ejecutar(con_archivo, "SELECT id FROM img WHERE SIMILAR_TO('foto.jpg', k=1) USING SEQ;")
        assert rutas == [("img", "foto.jpg")] and _ids(resultado) == [7]
        malo = Executor(catalogo, data_dir=carpeta, vectorizador=lambda tabla, ruta: [1.0, 2.0])
        _error(malo, "SELECT id FROM img WHERE SIMILAR_TO('foto.jpg', k=1) USING SEQ;", "dimensión 6")
        _error(Executor(catalogo, data_dir=carpeta, vectorizador=sin_archivo), "SELECT id FROM img WHERE SIMILAR_TO('nada.jpg', k=1);", "no se pudo leer")
        _error(Executor(catalogo, data_dir=carpeta, vectorizador=fuera), "SELECT id FROM img WHERE SIMILAR_TO('../x.jpg', k=1);", "fuera de la carpeta")


def _texto_plan(resultado):
    return "\n".join(resultado["explain"]["text"])


def _explain():
    datos = _datos(300, 8).astype(np.float32)
    with tempfile.TemporaryDirectory(prefix="test_similitud_") as carpeta:
        catalogo = {}
        executor = Executor(catalogo, data_dir=carpeta)
        _tabla_con_datos(executor, datos)
        q = _literal(datos[1])
        _ejecutar(executor, "CREATE INDEX ih ON img (v) USING HNSW WITH (METRIC=cosine, M=8);")
        _ejecutar(executor, "CREATE INDEX iv ON img (v) USING IVF WITH (METRIC=euclidean, LISTS=16);")
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=5) USING HNSW WITH METRIC=cosine, EF_SEARCH=50;"))
        assert "Vector Index Scan using ih on img" in texto and "Metric: cosine" in texto
        assert "m=8, ef_search=50" in texto and "cost=" in texto and "Seq Scan" not in texto
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=20) USING HNSW WITH METRIC=cosine, EF_SEARCH=5;"))
        assert "ef_search=20" in texto
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=5) USING IVF WITH METRIC=euclidean;"))
        assert "Vector Index Scan using iv" in texto and "lists=16, probes=4" in texto
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=5) USING IVF WITH METRIC=euclidean, PROBES=8;"))
        assert "probes=8" in texto
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=5) USING SEQ WITH METRIC=dot;"))
        assert "Seq Scan on img" in texto and "Similarity: exact k=5" in texto and "Metric: dot" in texto and "Note" not in texto
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=5) USING HNSW WITH METRIC=dot;"))
        assert "Seq Scan on img" in texto and "no existe un índice HNSW con métrica dot" in texto
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN ANALYZE SELECT id, SIMILARITY_SCORE() AS score FROM img WHERE grupo = 1 AND SIMILAR_TO({q}, k=5) USING HNSW WITH METRIC=cosine ORDER BY score DESC LIMIT 2;"))
        assert "Vector Index Scan using ih" in texto and "actual time=" in texto
        assert "Filter" in texto and "Sort" in texto and "Limit" in texto and "Execution Time" in texto
        resultado = _ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=5) USING HNSW WITH METRIC=cosine;")
        assert resultado["explain"]["tree"]["index"] == "ih" and resultado["explain"]["tree"]["node"] == "Vector Index Scan"
        pocos = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM img WHERE SIMILAR_TO({q}, k=5);"))
        assert "Seq Scan on img" in pocos and "Note" not in pocos
        _ejecutar(executor, "CREATE TABLE grande (id INT PRIMARY KEY, v VECTOR(8));")
        almacen = catalogo["grande"].almacenes["v"]
        azar = np.random.default_rng(0)
        muchos = azar.random((40000, 8)).astype(np.float32)
        rids = []
        for i in range(40000):
            rids.append((1, i))
        almacen.agregar_lote(muchos, rids)
        _ejecutar(executor, "CREATE INDEX g_iv ON grande (v) USING IVF WITH (METRIC=cosine, LISTS=200);")
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM grande WHERE SIMILAR_TO({q}, k=5);"))
        assert "Vector Index Scan using g_iv" in texto, texto
        texto = _texto_plan(_ejecutar(executor, f"EXPLAIN SELECT id FROM grande WHERE SIMILAR_TO({q}, k=5) USING SEQ;"))
        assert "Seq Scan on grande" in texto


def _mantenimiento():
    datos = _datos(150, 6, semilla=4).astype(np.float32)
    with tempfile.TemporaryDirectory(prefix="test_similitud_") as carpeta:
        catalogo = {}
        executor = Executor(catalogo, data_dir=carpeta)
        _tabla_con_datos(executor, datos)
        _ejecutar(executor, "CREATE INDEX ih ON img (v) USING HNSW WITH (METRIC=euclidean);")
        _ejecutar(executor, "CREATE INDEX iv ON img (v) USING IVF WITH (METRIC=euclidean, LISTS=12);")
        lejos = [90.0, 90.0, 90.0, 90.0, 90.0, 90.0]
        cerca = [40.0, 40.0, 40.0, 40.0, 40.0, 40.0]
        busquedas = (
            "USING HNSW WITH METRIC=euclidean, EF_SEARCH=200",
            "USING IVF WITH METRIC=euclidean, PROBES=12",
            "USING SEQ WITH METRIC=euclidean",
        )

        def mejor(vector, k=1):
            salida = []
            for busqueda in busquedas:
                resultado = _ejecutar(executor, f"SELECT id FROM img WHERE SIMILAR_TO({_literal(vector)}, k={k}) {busqueda};")
                salida.append(_ids(resultado))
            return salida

        _ejecutar(executor, f"INSERT INTO img VALUES (500, 1, {_literal(lejos)});")
        assert mejor(lejos) == [[500], [500], [500]]
        assert 500 in [fila["id"] for fila in _ejecutar(executor, "SELECT id FROM img WHERE id = 500;")["rows"]]
        _ejecutar(executor, f"UPDATE img SET v = {_literal(cerca)} WHERE id = 500;")
        assert mejor(cerca) == [[500], [500], [500]]
        _ejecutar(executor, "UPDATE img SET grupo = 2 WHERE id = 500;")
        assert mejor(cerca) == [[500], [500], [500]]
        _ejecutar(executor, "DELETE FROM img WHERE id = 500;")
        for ids in mejor(cerca, 3):
            assert 500 not in ids and len(ids) == 3
        _ejecutar(executor, f"INSERT INTO img VALUES (501, 1, {_literal(lejos)});")
        assert mejor(lejos) == [[501], [501], [501]]
        _ejecutar(executor, "UPDATE img SET v = NULL WHERE id = 501;")
        for ids in mejor(lejos):
            assert 501 not in ids
        _ejecutar(executor, f"INSERT INTO img VALUES (502, 1, {_literal(lejos)});")
        reabierto = _load_tables(carpeta)
        executor = Executor(reabierto, data_dir=carpeta)
        assert mejor(lejos) == [[502], [502], [502]]
        _ejecutar(executor, "DELETE FROM img WHERE id = 502;")
        for t in reabierto.values():
            t.cerrar()
        catalogo = _load_tables(carpeta)
        executor = Executor(catalogo, data_dir=carpeta)
        for ids in mejor(lejos):
            assert 502 not in ids
        assert sorted(catalogo["img"].indices_vectoriales["iv"].estructura.indexados) == catalogo["img"].almacenes["v"].ids_vivos().tolist()


def main():
    _columna_vector()
    _crear_indices()
    _busquedas()
    _explain()
    _mantenimiento()
    _similar_to()
    _using()
    _score()
    _vector()
    print("OK: SQL de similitud")


if __name__ == "__main__":
    main()
