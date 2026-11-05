import os
from tempfile import TemporaryDirectory

from .executor import Executor
from .scanner import Scanner
from .sql_parser import ParseError, Parser
from .visitor import PrintVisitor
from ..catalog import _load_tables
from ..fulltext import ranking
from ..fulltext.test_fulltext import _corpus

ENUNCIADO = [
    "SELECT * FROM documentos WHERE MATCH(contenido, 'base de datos vectorial') USING TF_IDF LIMIT 10",
    "SELECT *, SCORE() as relevancia FROM articulos WHERE MATCH(texto, 'machine learning') USING BM25 ORDER BY relevancia DESC",
]
IDA_Y_VUELTA = ENUNCIADO + [
    "SELECT id, SCORE() FROM t WHERE MATCH(c, 'banca digital') AND id > 3 USING BM25 WITH K1=1.5, B=0.25 LIMIT 3",
    "SELECT id FROM t WHERE MATCH(c, 'O''Brien') ORDER BY id",
    "SELECT SCORE() AS s, id FROM t WHERE MATCH(t.c, 'x') USING TF_IDF",
    "CREATE INDEX idx ON t (c) USING FULLTEXT",
]
RECHAZADAS = [
    "SELECT id, SCORE() FROM t WHERE id = 1",
    "SELECT id FROM t WHERE id = 1 USING BM25",
    "SELECT id FROM t WHERE MATCH(c, 'x') USING HNSW",
    "SELECT id FROM t WHERE MATCH(c, 'x') USING TF_IDF WITH K1=1.2",
    "SELECT id FROM t WHERE MATCH(c, 'x') USING BM25 WITH B=2",
    "SELECT id FROM t WHERE MATCH(c, 'x') USING BM25 WITH K1=-1",
    "SELECT id FROM t WHERE MATCH(c, 'x') USING BM25 WITH M=3",
    "SELECT id FROM t ORDER BY MATCH(c, 'x')",
    "SELECT id FROM t WHERE MATCH(c, 3)",
    "SELECT id, SCORE(), SCORE() FROM t WHERE MATCH(c, 'x')",
    "SELECT COUNT(*), SCORE() FROM t WHERE MATCH(c, 'x')",
    "SELECT id, SIMILARITY_SCORE() FROM t WHERE MATCH(c, 'x')",
    "CREATE INDEX idx ON t (c) USING FULLTEXT WITH (M=3)",
]


def parse(sql):
    return Parser(Scanner(sql)).parse_program()


def run(executor, sql):
    resultados = executor.run(parse(sql))
    assert all("error" not in r for r in resultados), resultados
    return resultados[-1]


def error(executor, sql):
    resultado = executor.run(parse(sql))[-1]
    assert "error" in resultado, (sql, resultado)
    return resultado["error"]


def _parser():
    for sql in IDA_Y_VUELTA:
        original = parse(sql)
        assert parse(PrintVisitor().render(original)) == original, sql
    for sql in RECHAZADAS:
        try:
            parse(sql)
        except ParseError:
            continue
        raise AssertionError(f"debía rechazarse: {sql}")
    select = parse(ENUNCIADO[1])[0]
    assert select.score_column == "relevancia" and select.index_method == "BM25" and select.order_desc
    assert parse("SELECT id, SCORE() FROM t WHERE MATCH(c, 'x')")[0].score_column == "score"


def _esperado(tabla, consulta, metodo, k=None, **opciones):
    estructura = tabla.indices_texto["idx_contenido"].vigente()
    ids = {}
    for fila in tabla.scan():
        ids[tabla._rid_secundario(fila)] = fila["id"]
    salida = []
    for valor, doc in ranking.buscar(estructura, consulta, metodo, k, **opciones):
        salida.append((ids[estructura.rid(doc)], valor))
    return salida


def _cerca(obtenido, esperado):
    assert len(obtenido) == len(esperado), (obtenido, esperado)
    for (id_obtenido, valor), (id_esperado, valor_esperado) in zip(obtenido, esperado):
        assert id_obtenido == id_esperado, (obtenido, esperado)
        assert abs(valor - valor_esperado) < 1e-9


def _puntajes(executor, sql, columna="score"):
    salida = []
    for fila in run(executor, sql)["rows"]:
        salida.append((fila["id"], fila[columna]))
    return salida


def _consultas(executor, tabla):
    filas = run(executor, "SELECT * FROM noticias WHERE MATCH(contenido, 'banca digital') USING TF_IDF LIMIT 10")["rows"]
    esperado = _esperado(tabla, "banca digital", ranking.TF_IDF, 10)
    assert [f["id"] for f in filas] == [i for i, _ in esperado]
    assert set(filas[0]) == {"id", "categoria", "contenido"}

    _cerca(_puntajes(executor, "SELECT *, SCORE() as relevancia FROM noticias WHERE MATCH(contenido, 'inflación y crecimiento económico') USING BM25 ORDER BY relevancia DESC", "relevancia"),
           _esperado(tabla, "inflación y crecimiento económico", ranking.BM25))
    _cerca(_puntajes(executor, "SELECT id, SCORE() FROM noticias WHERE MATCH(contenido, 'blockchain') LIMIT 7"),
           _esperado(tabla, "blockchain", ranking.BM25, 7))
    _cerca(_puntajes(executor, "SELECT id, SCORE() FROM noticias WHERE MATCH(contenido, 'energías renovables') USING BM25 WITH K1=2, B=0.3 LIMIT 5"),
           _esperado(tabla, "energías renovables", ranking.BM25, 5, k1=2.0, b=0.3))

    todos = _esperado(tabla, "crédito vivienda", ranking.TF_IDF)
    filtrados = []
    for id_, valor in todos:
        if id_ % 2 == 0:
            filtrados.append((id_, valor))
    _cerca(_puntajes(executor, "SELECT id, SCORE() FROM noticias WHERE MATCH(contenido, 'crédito vivienda') AND categoria = 'par' USING TF_IDF LIMIT 4"),
           filtrados[:4])

    ascendente = _puntajes(executor, "SELECT id, SCORE() FROM noticias WHERE MATCH(contenido, 'pagos móviles') ORDER BY score LIMIT 3")
    valores = []
    for _, valor in _esperado(tabla, "pagos móviles", ranking.BM25):
        valores.append(valor)
    assert [valor for _, valor in ascendente] == sorted(valores)[:3]
    por_id = run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'turismo') ORDER BY id")["rows"]
    assert [f["id"] for f in por_id] == sorted(i for i, _ in _esperado(tabla, "turismo", ranking.BM25))
    assert run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'palabrainexistente de la')")["rows"] == []

    plan = "\n".join(run(executor, "EXPLAIN ANALYZE SELECT id FROM noticias WHERE MATCH(contenido, 'banca') USING TF_IDF LIMIT 3")["explain"]["text"])
    assert "Text Index Scan using idx_contenido on noticias" in plan and "Ranking: TF_IDF top=3" in plan and "Terms: banc" in plan


def _mantenimiento(executor, tabla):
    indice = tabla.indices_texto["idx_contenido"]
    antes = indice.reconstrucciones
    run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'banca') LIMIT 3")
    run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'minería') LIMIT 3")
    assert indice.reconstrucciones == antes

    run(executor, "INSERT INTO noticias VALUES (9001, 'nuevo', 'zorzal zorzal zorzal en la sierra')")
    assert [f["id"] for f in run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'zorzal')")["rows"]] == [9001]
    assert indice.reconstrucciones == antes + 1
    run(executor, "UPDATE noticias SET contenido = 'colibrí en la costa' WHERE id = 9001")
    assert run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'zorzal')")["rows"] == []
    assert [f["id"] for f in run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'colibrí')")["rows"]] == [9001]
    run(executor, "DELETE FROM noticias WHERE id = 9001")
    assert run(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'colibrí')")["rows"] == []


def _errores(executor):
    assert "no tiene índice FULLTEXT" in error(executor, "SELECT id FROM sin_indice WHERE MATCH(cuerpo, 'banca')")
    assert "requiere una columna TEXT" in error(executor, "SELECT id FROM noticias WHERE MATCH(categoria, 'par')")
    assert "solo indexa columnas TEXT" in error(executor, "CREATE INDEX idx_cat ON noticias (categoria) USING FULLTEXT")
    assert "ya tiene el índice FULLTEXT" in error(executor, "CREATE INDEX otro ON noticias (contenido) USING FULLTEXT")
    assert "ya existe un índice" in error(executor, "CREATE INDEX idx_contenido ON sin_indice (cuerpo) USING FULLTEXT")
    assert "usa USING FULLTEXT" in error(executor, "CREATE INDEX idx_b ON noticias (contenido) USING BPLUS")
    assert "AND" in error(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'banca') OR id = 1")
    assert "un solo MATCH" in error(executor, "SELECT id FROM noticias WHERE MATCH(contenido, 'banca') AND MATCH(contenido, 'pagos')")
    assert "JOIN" in error(executor, "SELECT n.id FROM noticias n JOIN sin_indice s ON n.id = s.id WHERE MATCH(n.contenido, 'banca')")
    assert "coincide" in error(executor, "SELECT id, SCORE() AS categoria FROM noticias WHERE MATCH(contenido, 'banca')")
    assert "solo se admite en SELECT" in error(executor, "DELETE FROM noticias WHERE MATCH(contenido, 'banca')")
    assert "solo se admite en SELECT" in error(executor, "UPDATE noticias SET categoria = 'x' WHERE MATCH(contenido, 'banca')")
    assert "no existe" in error(Executor(), "SELECT id FROM nada WHERE MATCH(c, 'x')")


def _cargar(executor, kind, documentos):
    run(executor, f"CREATE TABLE noticias (id INT PRIMARY KEY, categoria VARCHAR(10), contenido TEXT) USING {kind}")
    run(executor, "CREATE TABLE sin_indice (id INT PRIMARY KEY, cuerpo TEXT)")
    valores = []
    for numero, (_, texto) in enumerate(documentos):
        valores.append(f"({numero + 1}, '{'par' if (numero + 1) % 2 == 0 else 'impar'}', '{texto}')")
    run(executor, "INSERT INTO noticias VALUES " + ", ".join(valores))
    run(executor, "INSERT INTO noticias VALUES (5000, 'nulo', NULL)")


def main():
    _parser()
    documentos = _corpus(300)
    for kind in ("HASH", "BPLUS", "BPLUS_CLUSTERED"):
        with TemporaryDirectory() as temp:
            executor = Executor(data_dir=temp)
            _cargar(executor, kind, documentos)
            tabla = executor.catalog["noticias"]
            tabla.limite_spimi = 500
            mensaje = run(executor, "CREATE INDEX idx_contenido ON noticias (contenido) USING FULLTEXT")["message"]
            assert "300 documentos" in mensaje and "bloque(s)" in mensaje
            assert tabla.indices_texto["idx_contenido"].estructura.meta["bloques"] > 1
            _consultas(executor, tabla)
            _mantenimiento(executor, tabla)
            _errores(executor)

            esperado = _puntajes(executor, "SELECT id, SCORE() FROM noticias WHERE MATCH(contenido, 'banca digital') LIMIT 20")
            for t in executor.catalog.values():
                t.cerrar()
            reabierto = Executor(catalog=_load_tables(temp), data_dir=temp)
            indice = reabierto.catalog["noticias"].indices_texto["idx_contenido"]
            assert indice.estructura is not None
            _cerca(_puntajes(reabierto, "SELECT id, SCORE() FROM noticias WHERE MATCH(contenido, 'banca digital') LIMIT 20"), esperado)
            assert indice.reconstrucciones == 0

            run(reabierto, "INSERT INTO noticias VALUES (7000, 'x', 'ñandú ñandú')")
            for t in reabierto.catalog.values():
                t.cerrar()
            otra_vez = Executor(catalog=_load_tables(temp), data_dir=temp)
            assert otra_vez.catalog["noticias"].indices_texto["idx_contenido"].estructura is None
            assert [f["id"] for f in run(otra_vez, "SELECT id FROM noticias WHERE MATCH(contenido, 'ñandú')")["rows"]] == [7000]

            run(otra_vez, "DROP INDEX idx_contenido")
            assert not any("__idx_contenido" in nombre for nombre in os.listdir(temp))
            assert "no tiene índice FULLTEXT" in error(otra_vez, "SELECT id FROM noticias WHERE MATCH(contenido, 'banca')")
            run(otra_vez, "CREATE INDEX idx_contenido ON noticias (contenido) USING FULLTEXT")
            run(otra_vez, "DROP TABLE noticias")
            assert not any(nombre.startswith("noticias") for nombre in os.listdir(temp))
    print("OK: SQL de texto: MATCH, SCORE(), USING TF_IDF/BM25 con WITH, LIMIT, filtros, mantenimiento, persistencia y errores en HASH, BPLUS y BPLUS_CLUSTERED")


if __name__ == "__main__":
    main()
