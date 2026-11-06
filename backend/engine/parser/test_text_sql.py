import importlib
import io
import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import UploadFile

from .executor import Executor
from .scanner import Scanner
from .sql_parser import Parser
from .visitor import PrintVisitor
from ..catalog import _load_tables
from ..importer import parse_csv
from ..transactions import TransactionManager

LARGO = "La inflación en el Perú bajó según el BCRP; O''Brien opinó que el año será mixto. " * 80
LEIDO = LARGO.replace("''", "'")


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


def _filas(executor, sql):
    return run(executor, sql)["rows"]


def _crear(executor, kind):
    using = "" if kind is None else " USING " + kind
    run(executor, "CREATE TABLE noticias (id INT PRIMARY KEY NOT NULL, titulo VARCHAR(30), contenido TEXT, categoria VARCHAR(20))" + using)
    run(executor, f"INSERT INTO noticias VALUES (1, 'largo', '{LARGO}', 'economia')")
    run(executor, "INSERT INTO noticias VALUES (2, 'corto', 'Banca digital y tecnología financiera', 'innovacion'), (3, 'nulo', NULL, 'economia'), (4, 'vacio', '', 'otra')")
    run(executor, "CREATE TABLE categorias (nombre VARCHAR(20) PRIMARY KEY, descripcion TEXT)" + using)
    run(executor, "INSERT INTO categorias VALUES ('economia', 'Noticias de macroeconomía y precios'), ('innovacion', 'Tecnología aplicada a la banca')")


def _consultas(executor):
    filas = _filas(executor, "SELECT * FROM noticias WHERE id = 1")
    assert len(LEIDO.encode()) > 4096
    assert filas[0]["contenido"] == LEIDO
    assert set(filas[0]) == {"id", "titulo", "contenido", "categoria"}

    filas = _filas(executor, "SELECT id, contenido FROM noticias ORDER BY id")
    assert [f["id"] for f in filas] == [1, 2, 3, 4]
    assert filas[2]["contenido"] is None
    assert filas[3]["contenido"] == ""

    filas = _filas(executor, "SELECT id FROM noticias WHERE contenido LIKE '%inflación%' OR contenido LIKE '%tecnología%' ORDER BY id")
    assert [f["id"] for f in filas] == [1, 2]
    filas = _filas(executor, "SELECT id FROM noticias WHERE contenido IS NULL")
    assert [f["id"] for f in filas] == [3]
    filas = _filas(executor, "SELECT id FROM noticias WHERE contenido = ''")
    assert [f["id"] for f in filas] == [4]

    filas = _filas(executor, "SELECT n.id, c.descripcion, n.contenido FROM noticias n JOIN categorias c ON n.categoria = c.nombre ORDER BY n.id")
    assert [f["n.id"] for f in filas] == [1, 2, 3]
    assert filas[0]["c.descripcion"] == "Noticias de macroeconomía y precios"
    assert filas[0]["n.contenido"] == LEIDO

    filas = _filas(executor, "SELECT categoria, COUNT(*) FROM noticias GROUP BY categoria ORDER BY categoria")
    assert [(f["categoria"], f["conteo"]) for f in filas] == [("economia", 2), ("innovacion", 1), ("otra", 1)]

    run(executor, "UPDATE noticias SET contenido = 'Texto nuevo con ñ' WHERE id = 2")
    run(executor, "UPDATE noticias SET titulo = 'renombrado' WHERE id = 1")
    run(executor, "UPDATE noticias SET contenido = 'ya no es nulo' WHERE id = 3")
    run(executor, "DELETE FROM noticias WHERE id = 4")
    filas = _filas(executor, "SELECT * FROM noticias ORDER BY id")
    assert [f["id"] for f in filas] == [1, 2, 3]
    assert filas[0]["titulo"] == "renombrado" and filas[0]["contenido"] == LEIDO
    assert filas[1]["contenido"] == "Texto nuevo con ñ"
    assert filas[2]["contenido"] == "ya no es nulo"

    texto = "\n".join(run(executor, "EXPLAIN SELECT * FROM noticias WHERE contenido LIKE '%BCRP%'")["explain"]["text"])
    assert "noticias" in texto


def _errores(executor, en_disco):
    assert "TEXT no admite PRIMARY KEY" in error(executor, "CREATE TABLE mal (c TEXT PRIMARY KEY, id INT)")
    if en_disco:
        assert "TEXT 'contenido' no admite índices" in error(executor, "CREATE INDEX idx_contenido ON noticias (contenido) USING BPLUS")
        assert "TEXT 'contenido' no admite índices" in error(executor, "CREATE INDEX idx_contenido ON noticias (contenido) USING HASH")
    assert "LIKE requiere" in error(executor, "SELECT * FROM noticias WHERE id LIKE '1%'")


def _indice_por_defecto(temp):
    executor = Executor(data_dir=temp)
    run(executor, "CREATE TABLE notas (cuerpo TEXT, id INT, autor VARCHAR(10))")
    tabla = executor.catalog["notas"]
    assert tabla.index_field == "id"
    run(executor, "INSERT INTO notas VALUES ('" + "x" * 9000 + "', 1, 'ana')")
    assert _filas(executor, "SELECT cuerpo FROM notas WHERE id = 1")[0]["cuerpo"] == "x" * 9000


def _importacion():
    largo = "El BCRP mantuvo la tasa, dijo el directorio, y añadió que la inflación cede. " * 50
    contenido = "id,titulo,cuerpo,nota\n1,corto,\"" + largo + "\",\n2,otro,breve,\"una nota algo más larga que treinta y dos bytes\"\n"
    encabezados, schema, filas = parse_csv(contenido.encode())
    assert dict(schema) == {"id": "int", "titulo": "str", "cuerpo": "text", "nota": "text"}
    assert filas[0]["cuerpo"] == largo.strip() and filas[0]["nota"] is None

    with patch("engine.catalog.create_catalog", return_value={}):
        api = importlib.import_module("api.main")
    with TemporaryDirectory() as temp:
        api.catalog = {}
        api.DATA_DIR = temp
        api.transaction_manager = TransactionManager()
        respuesta = api.import_table(UploadFile(io.BytesIO(contenido.encode()), filename="docs.csv"), "docs", "BPLUS", "")
        assert "error" not in respuesta, respuesta
        assert {"name": "cuerpo", "type": "text"} in respuesta["schema"]
        filas = api.query(api.QueryBody(sql="SELECT id, cuerpo FROM docs WHERE cuerpo LIKE '%inflación%'"))["rows"]
        assert filas == [{"id": 1, "cuerpo": largo.strip()}]
        respuesta = api.import_table(UploadFile(io.BytesIO(contenido.encode()), filename="docs.csv"), "mala", "HASH", "cuerpo")
        assert "no puede ser TEXT" in respuesta["error"]
        assert "mala" not in api.catalog


def main():
    for sql in ("CREATE TABLE t (id INT PRIMARY KEY, c TEXT NOT NULL, d TEXT)", "CREATE TABLE t (c TEXT) USING BPLUS_CLUSTERED"):
        original = parse(sql)
        assert parse(PrintVisitor().render(original)) == original, sql

    for kind in (None, "HASH", "BPLUS", "BPLUS_CLUSTERED"):
        with TemporaryDirectory() as temp:
            executor = Executor(data_dir=None if kind is None else temp)
            _crear(executor, kind)
            _consultas(executor)
            _errores(executor, kind is not None)
            if kind is not None:
                for tabla in executor.catalog.values():
                    tabla.cerrar()
                reabierto = Executor(catalog=_load_tables(temp), data_dir=temp)
                filas = _filas(reabierto, "SELECT id, contenido FROM noticias ORDER BY id")
                assert filas[0]["contenido"] == LEIDO
                assert filas[1]["contenido"] == "Texto nuevo con ñ"
                assert reabierto.catalog["noticias"].analyze()["columnas"]["contenido"]["largo_promedio"] > 1000
                run(reabierto, "DROP TABLE noticias")
                assert not any(nombre.startswith("noticias.") for nombre in os.listdir(temp))

    with TemporaryDirectory() as temp:
        _indice_por_defecto(temp)
    _importacion()

    print("OK: SQL con TEXT en memoria, HASH, BPLUS y BPLUS_CLUSTERED; LIKE, JOIN, GROUP BY, UPDATE, DELETE, persistencia, restricciones e importación CSV")


if __name__ == "__main__":
    main()
