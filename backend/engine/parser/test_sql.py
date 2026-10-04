"""Regresiones SQL: python -m engine.parser.test_sql (desde backend/)."""

import importlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from .executor import Executor, Table
from .nodes import Insert
from .scanner import LexicalError, Scanner
from .sql_parser import ParseError, Parser
from .testing import IDA_Y_VUELTA, INVALIDAS
from .visitor import PrintVisitor
from ..catalog import _load_tables
from ..transactions import LockMode, Resource, TransactionManager


def parse(sql):
    return Parser(Scanner(sql)).parse_program()


def run(executor, sql):
    resultados = executor.run(parse(sql))
    assert all("error" not in r for r in resultados), resultados
    return resultados[-1]


def error(executor, sql):
    resultado = executor.run(parse(sql))[-1]
    assert "error" in resultado, (sql, resultado)
    assert executor.transaction_manager.current() is None
    return resultado["error"]


def main():
    nuevas = [
        "-- comentario\nINSERT INTO t VALUES (-2, +3.5, 'O''Brien');",
        "SELECT * FROM t WHERE id <> -1 ORDER BY id DESC;",
        "SELECT SUM(id), id FROM t GROUP BY id ORDER BY id ASC;",
        "SELECT a.id, b.valor FROM t a INNER JOIN u b ON b.id = a.id ORDER BY b.valor DESC;",
        "SELECT COUNT(a.id), a.valor FROM t AS a JOIN t AS b ON a.id = b.id GROUP BY a.valor;",
    ]
    for sql in IDA_Y_VUELTA + nuevas:
        original = parse(sql)
        assert parse(PrintVisitor().render(original)) == original, sql
    for sql in INVALIDAS:
        try:
            parse(sql)
        except (LexicalError, ParseError):
            pass
        else:
            raise AssertionError(sql)

    for kind in (None, "HASH", "BPLUS", "BPLUS_CLUSTERED"):
        with TemporaryDirectory() as temp:
            executor = Executor(data_dir=None if kind is None else temp)
            using = "" if kind is None else " USING " + kind
            run(executor, "CREATE TABLE t (id INT PRIMARY KEY NOT NULL, valor INT, nombre VARCHAR(40), fecha DATE)" + using)
            run(executor, "INSERT INTO t VALUES (-1, 10, 'O''Brien', '2026-10-04')")
            run(executor, "INSERT INTO t VALUES (2, 20, 'áá', '2026-10-05')")
            antes = executor.run(parse("SELECT valor FROM t WHERE id = 2; UPDATE t SET valor = 21 WHERE id = 2;"))
            assert antes[0]["rows"] == [{"valor": 20}]
            run(executor, "UPDATE t SET valor = 20 WHERE id = 2")
            assert "duplicada" in error(executor, "INSERT INTO t VALUES (-1, 30, 'otra', '2026-10-06')")
            error(executor, "INSERT INTO t VALUES ('invalido', 1, 'x', '2026-10-04')")
            error(executor, "INSERT INTO t VALUES (3, 1, 'x', 'no-es-fecha')")
            error(executor, "UPDATE t SET id = 2 WHERE id = -1")
            error(executor, "UPDATE t SET id = 5")
            error(executor, "UPDATE t SET valor = 'invalido'")
            error(executor, "UPDATE t SET fecha = 'invalida'")
            error(executor, "SELECT * FROM t ORDER BY inexistente")
            error(executor, "SELECT COUNT(inexistente) FROM t")
            error(executor, "SELECT nombre, SUM(valor) FROM t GROUP BY id")
            error(executor, "SELECT nombre, COUNT(*) FROM t")
            error(executor, "SELECT SUM(nombre) FROM t")
            assert [r["id"] for r in run(executor, "SELECT * FROM t ORDER BY id DESC")["rows"]] == [2, -1]
            assert run(executor, "SELECT COUNT(id), COUNT(nombre) FROM t")["rows"] == [{"count_id": 2, "count_nombre": 2}]
            assert run(executor, "SELECT SUM(valor), id FROM t GROUP BY id")["columns"] == ["sum_valor", "id"]
            run(executor, "ANALYZE t")
            run(executor, "BEGIN TRANSACTION; UPDATE t SET nombre = 'nueva' WHERE id = 2; DELETE FROM t WHERE id = -1; END TRANSACTION;")
            assert run(executor, "SELECT COUNT(*) FROM t")["rows"] == [{"conteo": 1}]
            run(executor, "DELETE FROM t WHERE id = 2")
            assert run(executor, "SELECT COUNT(*), SUM(valor), AVG(valor), MIN(valor), MAX(valor) FROM t")["rows"] == [{"conteo": 0, "sum_valor": None, "avg_valor": None, "min_valor": None, "max_valor": None}]
            run(executor, "CREATE TABLE corta (id INT PRIMARY KEY, nombre VARCHAR(2))" + using)
            error(executor, "INSERT INTO corta VALUES (1, 'abc')")
            run(executor, "INSERT INTO corta VALUES (1, 'áá')")
            assert run(executor, "SELECT * FROM corta")["rows"][0]["nombre"] == "áá"
            if kind is not None:
                recargado = Executor(_load_tables(temp), data_dir=temp)
                error(recargado, "INSERT INTO t VALUES (3, 10, 'x', 'invalida')")
                error(recargado, "INSERT INTO corta VALUES (1, 'ab')")
                error(recargado, "INSERT INTO corta VALUES (2, 'abc')")
                largo = "x" * 40
                run(recargado, f"INSERT INTO t VALUES (3, 10, '{largo}', '2026-10-04')")
                assert run(recargado, "SELECT nombre FROM t")["rows"][0]["nombre"] == largo
            assert "error" in executor.run([Insert("corta", [None, "ab"])])[0]

    izquierda = Table("a", ["id", "valor"], column_types={"id": "INT", "valor": "INT"})
    derecha = Table("b", ["id", "valor"], column_types={"id": "INT", "valor": "INT"})
    for i in range(50):
        izquierda.insert({"id": i, "valor": i % 7})
        derecha.insert({"id": i, "valor": i * 2})
        derecha.insert({"id": i, "valor": i * 3})
    executor = Executor({"a": izquierda, "b": derecha})
    with sqlite3.connect(":memory:") as reference:
        reference.executescript("CREATE TABLE a (id INT, valor INT); CREATE TABLE b (id INT, valor INT);")
        reference.executemany("INSERT INTO a VALUES (?, ?)", [(r["id"], r["valor"]) for r in izquierda.rows])
        reference.executemany("INSERT INTO b VALUES (?, ?)", [(r["id"], r["valor"]) for r in derecha.rows])
        sql = "SELECT a.id, b.valor FROM a JOIN b ON b.id = a.id WHERE b.valor > 20 ORDER BY b.valor DESC"
        resultado = run(executor, sql)
        assert sorted((r["a.id"], r["b.valor"]) for r in resultado["rows"]) == sorted(reference.execute(sql).fetchall())
        assert [r["b.valor"] for r in resultado["rows"]] == sorted((r["b.valor"] for r in resultado["rows"]), reverse=True)
        assert any(p["op"] == "Join" and p["method"] == "external-hash" for p in resultado["plan"])
        agrupado = run(executor, "SELECT a.valor, SUM(b.valor) FROM a JOIN b ON a.id = b.id GROUP BY a.valor ORDER BY a.valor")
        assert [(r["a.valor"], r["sum_b.valor"]) for r in agrupado["rows"]] == reference.execute("SELECT a.valor, SUM(b.valor) FROM a JOIN b ON a.id = b.id GROUP BY a.valor ORDER BY a.valor").fetchall()
    assert "ambigua" in error(executor, "SELECT id FROM a JOIN b ON a.id = b.id")
    error(executor, "SELECT * FROM a JOIN b ON a.id = a.valor")
    assert run(executor, "SELECT x.id FROM a x JOIN a y ON x.id = y.id")["columns"] == ["x.id"]
    assert run(executor, "EXPLAIN SELECT * FROM a JOIN b ON a.id = b.id")["explain"]["tree"]["node"] == "Hash Join"
    assert run(executor, "EXPLAIN ANALYZE SELECT * FROM a JOIN b ON a.id = b.id")["explain"]["tree"]["actual"]["rows"] == 100
    assert len(run(executor, "SELECT a.id FROM a WHERE a.id >= 40")["rows"]) == 10

    manager = TransactionManager()
    writer = Executor({"a": izquierda}, manager)
    manager.begin()
    resource = Resource("table", "a")
    manager.acquire(resource, LockMode.PX)
    iniciado = Event()

    def insertar():
        iniciado.set()
        return run(writer, "INSERT INTO a VALUES (100, 1)")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pendiente = pool.submit(insertar)
        try:
            assert iniciado.wait(1)
            with manager.lock_manager.condition:
                assert manager.lock_manager.condition.wait_for(lambda: any(e[0] == "WAIT" for e in manager.lock_manager.history), timeout=1)
            assert not pendiente.done()
        finally:
            manager.end()
        pendiente.result(timeout=2)
    assert not manager.transactions and not manager.lock_manager.owners

    with patch("engine.catalog.create_catalog", return_value={}):
        api = importlib.import_module("api.main")
    with TemporaryDirectory() as temp:
        api.catalog = {}
        api.DATA_DIR = temp
        api.transaction_manager = TransactionManager()
        assert "error" in api.query(api.QueryBody(sql="BEGIN TRANSACTION; CREATE TABLE incompleta (id INT)"))
        assert "incompleta" not in api.catalog
        assert "error" not in api.query(api.QueryBody(sql="CREATE TABLE t (id INT PRIMARY KEY); BEGIN TRANSACTION; INSERT INTO t VALUES (1); END TRANSACTION; SELECT * FROM t;"))
        response = api.query(api.QueryBody(sql="SELECT x.id, y.id FROM t x JOIN t y ON x.id = y.id"))
        assert response["rows"] == [{"x.id": 1, "y.id": 1}]
        assert "error" in api.query(api.QueryBody(sql="INSERT INTO t VALUES ('invalido')"))
        assert "error" in api.query(api.QueryBody(sql="SELECT * FROM t ORDER BY noexiste"))
        assert "error" not in api.query(api.QueryBody(sql="DELETE FROM t WHERE id = 1; ANALYZE t;"))
        assert not api.transaction_manager.transactions
    print("OK: parser, ejecución, restricciones persistentes, JOIN externo, EXPLAIN, concurrencia y API")


if __name__ == "__main__":
    main()
