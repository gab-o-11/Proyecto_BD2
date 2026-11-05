from .scanner import Scanner
from .sql_parser import ParseError, Parser
from .nodes import DEFAULT_SCORE_COLUMN, And, SimilarTo, VectorLiteral
from .visitor import PrintVisitor


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


def main():
    _similar_to()
    _using()
    _score()
    _vector()
    print("OK: SQL de similitud")


if __name__ == "__main__":
    main()
