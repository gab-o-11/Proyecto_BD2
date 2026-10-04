"""Regresiones espaciales: python -m engine.parser.test_spatial_sql."""

import importlib
import json
import math
import tempfile
from pathlib import Path
from unittest.mock import patch

from .executor import Executor, Table
from .scanner import LexicalError
from .sql_parser import ParseError
from .test_sql import error, parse, run
from .visitor import PrintVisitor
from ..catalog import _load_tables
from ..spatial import EARTH_RADIUS_METERS, distance


def main():
    ejemplos = [
        "SELECT * FROM tiendas WHERE distancia(ubicacion, POINT(-12.0464, -77.0428)) < 5000;",
        "SELECT * FROM restaurantes ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 10;",
        "SELECT * FROM t ORDER BY distancia(POINT(0, 0), ubicacion, 'euclidean') DESC LIMIT 0;",
        "CREATE TABLE t (id INT PRIMARY KEY, ubicacion POINT NOT NULL);",
        "SELECT * FROM t WHERE intersecta(ubicacion, POLYGON(POINT(0, 0), POINT(1, 0), POINT(0, 1)));",
        "INSERT INTO t VALUES (1, POINT(1e-7, -7.70428e1));",
        "UPDATE t SET ubicacion = POINT(1, 2) WHERE distancia(ubicacion, POINT(0, 0), 'euclidean') <= 5;",
        "DELETE FROM t WHERE distancia(ubicacion, centro) > 5000;",
        "EXPLAIN ANALYZE SELECT a.id FROM t a JOIN t b ON a.id = b.id WHERE distancia(a.ubicacion, b.ubicacion) = 0 ORDER BY distancia(a.ubicacion, mi_ubicacion) LIMIT 2;",
    ]
    for sql in ejemplos:
        ast = parse(sql)
        assert ast == parse(PrintVisitor().render(ast)), sql
    for sql in [
        "SELECT * FROM t LIMIT -1", "SELECT * FROM t LIMIT 1.5",
        "SELECT * FROM t LIMIT", "SELECT * FROM t LIMIT 9999999999999999999999",
        "SELECT * FROM t LIMIT 1 ORDER BY id",
        "SELECT * FROM t WHERE distancia(ubicacion) < 5",
        "SELECT * FROM t WHERE distancia(ubicacion, POINT(1)) < 5",
        "SELECT * FROM t WHERE distancia(ubicacion, POINT(1, 2, 3)) < 5",
        "SELECT * FROM t WHERE distancia(ubicacion, POINT('x', 2)) < 5",
        "SELECT * FROM t WHERE distancia(ubicacion, POINT(1e999, 2)) < 5",
        "SELECT * FROM t WHERE distancia(ubicacion, POINT(1, 2), 'desconocida') < 5",
        "SELECT * FROM t ORDER BY desconocida(ubicacion, POINT(1, 2))",
        "SELECT * FROM t ORDER BY intersecta(ubicacion, POLYGON(POINT(0, 0), POINT(1, 0), POINT(0, 1)))",
        "INSERT INTO t VALUES (1, POINT(1e, 2))",
    ]:
        try:
            parse(sql)
        except (LexicalError, ParseError):
            pass
        else:
            raise AssertionError(sql)

    assert distance((0, 0), (3, 4), "euclidean") == 5
    assert distance((-12.0464, -77.0428), (-12.0464, -77.0428)) == 0
    assert math.isclose(distance((0, 0), (0, 1)), math.pi * EARTH_RADIUS_METERS / 180, rel_tol=1e-12)
    assert math.isclose(distance((0, 0), (0, 180)), math.pi * EARTH_RADIUS_METERS, rel_tol=1e-12)
    assert math.isclose(distance((0, 179), (0, -179)), 2 * math.pi * EARTH_RADIUS_METERS / 180, rel_tol=1e-12)

    for kind in (None, "HASH", "BPLUS", "BPLUS_CLUSTERED"):
        with tempfile.TemporaryDirectory() as temp:
            executor = Executor(data_dir=None if kind is None else temp, parameters={"mi_ubicacion": (-12.0464, -77.0428)})
            using = "" if kind is None else " USING " + kind
            run(executor, "CREATE TABLE tiendas (ubicacion POINT, id INT PRIMARY KEY, nombre VARCHAR(20), referencia POINT)" + using)
            for id_, lat, lon in [(3, -13, -78), (1, -12.0464, -77.0428), (2, -12.05, -77.04)]:
                run(executor, f"INSERT INTO tiendas VALUES (POINT({lat}, {lon}), {id_}, 'Tienda {id_}', POINT(0, 0))")
            radio = run(executor, ejemplos[0])
            assert sorted(r["id"] for r in radio["rows"]) == [1, 2]
            assert any(p["op"] == "Spatial Index Scan" and p["method"] == "RTREE-radius" for p in radio["plan"])
            cercana = run(executor, "SELECT id FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 2")
            assert cercana["rows"] == [{"id": 1}, {"id": 2}]
            assert any(p["method"] == "RTREE-knn" for p in cercana["plan"])
            assert cercana["spatial"][0]["points"] == [(-12.0464, -77.0428), (-12.05, -77.04)]
            polygon = "intersecta(ubicacion, POLYGON(POINT(-12.1, -77.1), POINT(-12, -77.1), POINT(-12, -77), POINT(-12.1, -77)))"
            assert sorted(r["id"] for r in run(executor, "SELECT id FROM tiendas WHERE " + polygon)["rows"]) == [1, 2]
            assert run(executor, "SELECT t.id FROM tiendas t WHERE " + polygon.replace("(ubicacion,", "(t.ubicacion,"))["rows"]
            table = executor.catalog["tiendas"]
            tree = table.spatial_index("ubicacion")
            with patch.object(table, "scan", side_effect=AssertionError("warm R-Tree realizó scan")):
                assert len(run(executor, "SELECT id FROM tiendas WHERE " + polygon)["rows"]) == 2
                assert run(executor, "SELECT id FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 1")["rows"] == [{"id": 1}]
                assert len(run(executor, ejemplos[0])["rows"]) == 2
            run(executor, "INSERT INTO tiendas VALUES (POINT(-12.0464, -77.0428), 4, 'Nueva', POINT(0, 0))")
            assert len(run(executor, ejemplos[0])["rows"]) == 3
            if kind != "BPLUS_CLUSTERED":
                assert table.spatial_index("ubicacion") is tree
            run(executor, "UPDATE tiendas SET ubicacion = POINT(-13, -78) WHERE id = 4")
            assert len(run(executor, ejemplos[0])["rows"]) == 2
            run(executor, "DELETE FROM tiendas WHERE id = 4")
            assert len(table.spatial_index("ubicacion")) == 3
            assert run(executor, "SELECT id FROM tiendas WHERE id > 1 ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 1")["rows"] == [{"id": 2}]
            joined_polygon = polygon.replace("(ubicacion,", "(t.ubicacion,")
            assert sorted(r["t.id"] for r in run(executor, "SELECT t.id FROM tiendas t JOIN tiendas s ON t.id = s.id WHERE " + joined_polygon)["rows"]) == [1, 2]
            run(executor, "CREATE TABLE zonas (id INT PRIMARY KEY, ubicacion POINT)" + using)
            for identifier, coordinates in [(1, (0, 0)), (2, (3, 4)), (3, (8, 8))]:
                run(executor, f"INSERT INTO zonas VALUES ({identifier}, POINT{coordinates})")
            assert len(run(executor, "SELECT * FROM zonas WHERE distancia(ubicacion, POINT(0, 0), 'euclidean') < 5")["rows"]) == 1
            assert len(run(executor, "SELECT * FROM zonas WHERE distancia(ubicacion, POINT(0, 0), 'euclidean') <= 5")["rows"]) == 2
            triangle = "intersecta(ubicacion, POLYGON(POINT(0, 0), POINT(6, 0), POINT(0, 8)))"
            assert len(run(executor, "SELECT * FROM zonas WHERE " + triangle)["rows"]) == 2
            run(executor, "UPDATE zonas SET ubicacion = POINT(1, 1) WHERE " + triangle)
            assert len(run(executor, "SELECT * FROM zonas WHERE " + triangle)["rows"]) == 2
            run(executor, "DELETE FROM zonas WHERE " + triangle)
            assert run(executor, "SELECT id FROM zonas ORDER BY distancia(ubicacion, POINT(0, 0), 'euclidean') LIMIT 2")["rows"] == [{"id": 3}]
            error(executor, "SELECT * FROM tiendas WHERE intersecta(id, POLYGON(POINT(0, 0), POINT(1, 0), POINT(0, 1)))")
            error(executor, "SELECT * FROM tiendas WHERE intersecta(ubicacion, POLYGON(POINT(0, 0), POINT(1, 0)))")
            error(executor, "SELECT * FROM tiendas WHERE intersecta(ubicacion, POLYGON(POINT(0, 0), POINT(1, 1), POINT(2, 2)))")
            assert run(executor, "SELECT id FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) DESC LIMIT 1")["rows"] == [{"id": 3}]
            assert run(executor, "SELECT * FROM tiendas LIMIT 0")["rows"] == []
            assert len(run(executor, "SELECT * FROM tiendas LIMIT 10")["rows"]) == 3
            assert run(executor, "SELECT id FROM tiendas t ORDER BY distancia(t.ubicacion, mi_ubicacion) LIMIT 1")["rows"] == [{"t.id": 1}]
            assert run(executor, "SELECT id FROM tiendas WHERE distancia(ubicacion, referencia, 'euclidean') > 0 LIMIT 1")["rows"]
            run(executor, "CREATE TABLE restaurantes (id INT PRIMARY KEY, ubicacion POINT)" + using)
            run(executor, "INSERT INTO restaurantes VALUES (1, POINT(-12.0464, -77.0428))")
            assert run(executor, ejemplos[1])["rows"] == [{"id": 1, "ubicacion": (-12.0464, -77.0428)}]
            assert run(executor, "SELECT t.id FROM tiendas t JOIN restaurantes r ON t.id = r.id WHERE distancia(t.ubicacion, r.ubicacion) = 0 ORDER BY distancia(t.ubicacion, mi_ubicacion) LIMIT 1")["rows"] == [{"t.id": 1}]
            plan = run(executor, "EXPLAIN ANALYZE SELECT * FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 1")
            assert plan["explain"]["tree"]["node"] == "Limit"
            assert plan["explain"]["tree"]["actual"]["rows"] == 1
            error(executor, "SELECT * FROM tiendas ORDER BY distancia(id, mi_ubicacion) LIMIT 1")
            error(executor, "SELECT * FROM tiendas ORDER BY distancia(ubicacion, no_definido)")
            error(executor, "SELECT * FROM tiendas WHERE distancia(ubicacion, mi_ubicacion) < 'x'")
            error(executor, "SELECT * FROM tiendas WHERE distancia(ubicacion, POINT(91, 0)) < 10")
            error(executor, "INSERT INTO tiendas VALUES (5, 5, 'x', POINT(0, 0))")
            error(executor, "SELECT COUNT(*) FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion)")
            run(executor, "UPDATE tiendas SET ubicacion = POINT(-12.0464, -77.0428) WHERE distancia(tiendas.ubicacion, mi_ubicacion) > 5000")
            run(executor, "DELETE FROM tiendas WHERE distancia(tiendas.ubicacion, mi_ubicacion) = 0")
            assert run(executor, "SELECT COUNT(*) FROM tiendas")["rows"] == [{"conteo": 1}]
            if kind is not None:
                recargado = Executor(_load_tables(temp), data_dir=temp, parameters=executor.parameters)
                assert run(recargado, "SELECT ubicacion FROM tiendas WHERE id >= 2")["rows"] == [{"ubicacion": (-12.05, -77.04)}]
                assert run(recargado, "SELECT * FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 1")["rows"][0]["id"] == 2

    tabla = Table("puntos", ["id", "ubicacion"], column_types={"id": "INT", "ubicacion": "POINT"})
    for i in range(80):
        tabla.insert({"id": i, "ubicacion": (0, i)})
    executor = Executor({"puntos": tabla})
    with tempfile.TemporaryDirectory() as temp, patch("tempfile.tempdir", temp):
        assert run(executor, "SELECT id FROM puntos ORDER BY distancia(ubicacion, POINT(0, 0), 'euclidean') DESC LIMIT 2")["rows"] == [{"id": 79}, {"id": 78}]
        assert not list(Path(temp).iterdir()), "LIMIT dejó runs de ordenamiento"
        run(executor, "SELECT a.id FROM puntos a JOIN puntos b ON a.id = b.id LIMIT 1")
        assert not list(Path(temp).iterdir()), "LIMIT dejó particiones del JOIN"
        run(executor, "SELECT ubicacion FROM puntos GROUP BY ubicacion LIMIT 1")
        assert not list(Path(temp).iterdir()), "LIMIT dejó particiones del GROUP BY"
        tabla.rows[-1]["ubicacion"] = (91, 0)
        error(executor, "SELECT id FROM puntos ORDER BY distancia(ubicacion, POINT(0, 0)) LIMIT 1")
        assert not list(Path(temp).iterdir()), "un error de distancia dejó runs"

    with patch("engine.catalog.create_catalog", return_value={}):
        api = importlib.import_module("api.main")
    with tempfile.TemporaryDirectory() as temp:
        api.catalog = {}
        api.DATA_DIR = temp
        setup = api.query(api.QueryBody(sql="CREATE TABLE tiendas (id INT PRIMARY KEY, ubicacion POINT); INSERT INTO tiendas VALUES (1, POINT(-12.0464, -77.0428));"))
        assert "error" not in setup, setup
        response = api.query(api.QueryBody(sql="SELECT * FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 1", parameters={"mi_ubicacion": [-12.0464, -77.0428]}))
        assert response["rows"][0]["ubicacion"] == (-12.0464, -77.0428)
        assert response["statements"][0]["spatial"][0]["points"] == [(-12.0464, -77.0428)]
        assert {k: api.tables()[0]["indexes"][-1][k] for k in ("field", "type")} == {"field": "ubicacion", "type": "RTREE"}
        assert json.loads(json.dumps(response))["rows"][0]["ubicacion"] == [-12.0464, -77.0428]
        response = api.query(api.QueryBody(sql="SELECT * FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion)", parameters={"mi_ubicacion": [float("nan"), 0]}))
        assert "error" in response
    print("OK: SQL espacial, R-Tree sin scan, radio/kNN/polígonos, mantenimiento, persistencia, mapa/API y LIMIT")


if __name__ == "__main__":
    main()
