"""Comparación reproducible de barrido, R-Tree y PostgreSQL GiST (parte 2)."""

import argparse
import csv
import heapq
import io
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from engine.rtree import RTree
from engine.spatial import EARTH_RADIUS_METERS, distance

import psycopg2
os.environ.setdefault("MPLCONFIGDIR", "/tmp/bd2-spatial-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def deep_size(value, seen):
    """Objetos Python retenidos; evita contar dos veces los datos compartidos."""
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    total = sys.getsizeof(value)
    if isinstance(value, dict):
        total += sum(deep_size(k, seen) + deep_size(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        total += sum(deep_size(v, seen) for v in value)
    elif hasattr(value, "__dict__"):
        total += deep_size(vars(value), seen)
    return total


def elapsed(action):
    started = time.perf_counter_ns()
    result = action()
    return result, (time.perf_counter_ns() - started) / 1_000_000


def scan(points, center, operation, parameter):
    if operation == "radio":
        return [i for i, coordinates in points if distance(coordinates, center) <= parameter]
    return [i for _, i in heapq.nsmallest(parameter, ((distance(p, center), i) for i, p in points))]


def postgres_query(cursor, center, operation, parameter):
    if operation == "radio":
        sql = """SELECT id FROM puntos
                 WHERE earth_box(ll_to_earth(%s, %s), %s) @> loc
                 AND earth_distance(ll_to_earth(%s, %s), loc) <= %s"""
        values = (*center, parameter, *center, parameter)
    else:
        sql = """SELECT id FROM puntos
                 ORDER BY loc <-> ll_to_earth(%s, %s)::cube LIMIT %s"""
        values = (*center, parameter)
    cursor.execute(sql, values)
    return [row[0] for row in cursor.fetchall()]


def plot(output, summary, construction):
    colors = {"secuencial": "#475569", "rtree": "#0284c7", "gist": "#ea580c"}
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), constrained_layout=True)
    for row, operation in enumerate(("radio", "knn")):
        for column, parameter in enumerate((1000, 5000, 10000) if operation == "radio" else (10, 50, 100)):
            ax = axes[row, column]
            for method, color in colors.items():
                rows = [r for r in summary if r["metodo"] == method and r["operacion"] == operation and r["parametro"] == parameter]
                ax.plot([r["n"] for r in rows], [r["promedio_ms"] for r in rows], "o-", label=method, color=color)
            ax.set(xscale="log", yscale="log", xlabel="Número de puntos", ylabel="Tiempo promedio (ms)",
                   title=f"Radio {parameter // 1000} km" if operation == "radio" else f"k-NN: k = {parameter}")
            ax.grid(True, alpha=.25)
    axes[0, 0].legend()
    fig.suptitle("Consultas espaciales · Haversine · promedio de consultas verificadas")
    fig.savefig(output / "consultas.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for method in ("rtree", "gist"):
        rows = [r for r in construction if r["metodo"] == method]
        axes[0].plot([r["n"] for r in rows], [r["construccion_ms"] for r in rows], "o-", label=method, color=colors[method])
    rows = [r for r in construction if r["metodo"] == "gist"]
    if all(r.get("gist_cache_bytes", "") != "" for r in rows):
        axes[1].plot([r["n"] for r in rows], [r["gist_cache_bytes"] / 2**20 for r in rows], "o-", label="GiST: páginas en caché", color=colors["gist"])
    axes[2].plot([r["n"] for r in rows], [r["indice_disco_bytes"] / 2**20 for r in rows], "o-", label="GiST: archivo del índice", color=colors["gist"])
    rtree_rows = [r for r in construction if r["metodo"] == "rtree"]
    axes[2].plot([r["n"] for r in rtree_rows], [r["indice_disco_bytes"] / 2**20 for r in rtree_rows], "o-", label="R-Tree: archivo .nodes + .meta", color=colors["rtree"])
    axes[0].set(xscale="log", yscale="log", xlabel="Número de puntos", ylabel="Construcción (ms)", title="Construcción del índice")
    axes[1].set(xscale="log", xlabel="Número de puntos", ylabel="MiB", title="Caché del índice GiST")
    axes[2].set(xscale="log", xlabel="Número de puntos", ylabel="MiB", title="Disco del índice")
    for ax in axes:
        ax.legend()
        ax.grid(True, alpha=.25)
    fig.savefig(output / "construccion_espacio.png", dpi=160)
    plt.close(fig)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 100000])
    parser.add_argument("--queries", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "spatial_results")
    args = parser.parse_args()
    if args.queries < 1 or any(n < 100 for n in args.sizes):
        parser.error("se requieren consultas > 0 y tamaños >= 100")
    args.output.mkdir(parents=True, exist_ok=True)
    summary, samples, construction, plans = [], [], [], []
    rng = random.Random(20261004)
    all_points = [(i, (rng.uniform(-12.55, -11.55), rng.uniform(-77.55, -76.55))) for i in range(max(args.sizes))]
    centers = [(rng.uniform(-12.35, -11.75), rng.uniform(-77.35, -76.75)) for _ in range(args.queries)]
    metadata = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seed": 20261004, "sizes": args.sizes, "queries": args.queries,
                "python": sys.version, "platform": platform.platform(), "earth_radius_m": EARTH_RADIUS_METERS,
                "distribution": "Uniforme en [-12.55,-11.55] lat × [-77.55,-76.55] lon; centros interiores",
                "metric": "Haversine / gran círculo sobre esfera", "cpu_count": os.cpu_count(),
                "p95_method": "nearest_rank",
                "footprint_measurement": "Caché GiST medida en la misma corrida, después de las consultas y EXPLAIN de cada tamaño"}
    with tempfile.TemporaryDirectory(prefix="bd2-spatial-pg-") as work:
        cluster, socket = Path(work) / "data", Path(work) / "socket"
        socket.mkdir()
        log = Path(work) / "postgres.log"
        subprocess.run(["initdb", "-D", str(cluster), "-A", "trust", "--no-locale", "-E", "UTF8"], check=True, stdout=subprocess.DEVNULL)
        try:
            subprocess.run(["pg_ctl", "-D", str(cluster), "-l", str(log), "-o",
                            f"-h '' -k {socket} -p 55439 -c shared_buffers=64MB -c max_connections=10", "-w", "start"], check=True, stdout=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print(log.read_text(), file=sys.stderr)
            raise
        try:
            with psycopg2.connect(host=str(socket), port=55439, dbname="postgres") as connection:
                connection.autocommit = True
                with connection.cursor() as cursor:
                    cursor.execute("CREATE EXTENSION cube; CREATE EXTENSION earthdistance; CREATE EXTENSION pg_buffercache;")
                    cursor.execute("CREATE OR REPLACE FUNCTION earth() RETURNS float8 LANGUAGE SQL IMMUTABLE PARALLEL SAFE AS 'SELECT 6371000::float8'")
                    cursor.execute("SET enable_seqscan=off; SET max_parallel_workers_per_gather=0")
                    cursor.execute("SELECT version(), current_setting('shared_buffers')")
                    metadata["postgresql"], metadata["postgres_shared_buffers"] = cursor.fetchone()
                    for n in args.sizes:
                        print(f"N={n}: construcción", flush=True)
                        points = all_points[:n]
                        seen = set()
                        data_ram = deep_size(points, seen)
                        tree = RTree(os.path.join(work, f"rtree_{n}"))
                        _, tree_build = elapsed(lambda: tree.bulk_load([(coordinates, identity) for identity, coordinates in points]))
                        tree_disk = tree.bytes_en_disco()
                        cursor.execute("DROP TABLE IF EXISTS puntos; CREATE TABLE puntos (id integer, lat float8, lon float8, loc earth GENERATED ALWAYS AS (ll_to_earth(lat, lon)) STORED)")
                        buffer = io.StringIO()
                        csv.writer(buffer, lineterminator="\n").writerows((i, *p) for i, p in points)
                        serialized_bytes = len(buffer.getvalue().encode())
                        buffer.seek(0)
                        _, load_ms = elapsed(lambda: cursor.copy_expert("COPY puntos(id,lat,lon) FROM STDIN WITH CSV", buffer))
                        _, gist_build = elapsed(lambda: cursor.execute("CREATE INDEX puntos_gist ON puntos USING gist(loc)"))
                        cursor.execute("ANALYZE puntos")
                        cursor.execute("SELECT pg_relation_size('puntos'), pg_relation_size('puntos_gist')")
                        pg_data, pg_index = cursor.fetchone()
                        for method, build, ram, disk in (("secuencial", 0, 0, 0), ("rtree", tree_build, 0, tree_disk), ("gist", gist_build, "", pg_index)):
                            construction.append({"n": n, "metodo": method, "construccion_ms": build,
                                                 "datos_python_ram_bytes": data_ram if method != "gist" else "",
                                                 "indice_ram_bytes": ram, "indice_disco_bytes": disk,
                                                 "gist_cache_bytes": "",
                                                 "tabla_pg_disco_bytes": pg_data if method == "gist" else "",
                                                 "entrada_csv_bytes": serialized_bytes,
                                                 "carga_pg_ms": load_ms if method == "gist" else ""})
                        for operation, parameters in (("radio", (1000, 5000, 10000)), ("knn", (10, 50, 100))):
                            for parameter in parameters:
                                print(f"N={n}: {operation}={parameter}, {args.queries} consultas", flush=True)
                                operations = {
                                    "secuencial": lambda c: scan(points, c, operation, parameter),
                                    "rtree": (lambda c: tree.search_radius(c, parameter)) if operation == "radio" else (lambda c: tree.knn(c, parameter)),
                                    "gist": lambda c: postgres_query(cursor, c, operation, parameter),
                                }
                                for action in operations.values():
                                    action(centers[0])
                                for query, center in enumerate(centers):
                                    results = {}
                                    # Rotación de orden evita favorecer siempre la misma técnica.
                                    methods = list(operations)
                                    methods = methods[query % 3:] + methods[:query % 3]
                                    for method in methods:
                                        ids, ms = elapsed(lambda: operations[method](center))
                                        results[method] = sorted(ids) if operation == "radio" else ids
                                        samples.append({"n": n, "metodo": method, "operacion": operation,
                                                        "parametro": parameter, "consulta": query, "lat": center[0], "lon": center[1],
                                                        "tiempo_ms": ms, "resultados": len(ids)})
                                    assert results["secuencial"] == results["rtree"] == results["gist"], (n, operation, parameter, query)
                                for method in operations:
                                    rows = [r for r in samples if r["n"] == n and r["metodo"] == method and r["operacion"] == operation and r["parametro"] == parameter]
                                    timings = sorted(r["tiempo_ms"] for r in rows)
                                    summary.append({"n": n, "metodo": method, "operacion": operation, "parametro": parameter,
                                                    "consultas": args.queries, "promedio_ms": statistics.mean(timings),
                                                    "p95_ms": timings[math.ceil(len(timings) * .95) - 1],
                                                    "resultados_promedio": statistics.mean(r["resultados"] for r in rows),
                                                    "verificadas": True})
                                query_sql = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + (
                                    "SELECT id FROM puntos WHERE earth_box(ll_to_earth(%s,%s),%s) @> loc AND earth_distance(ll_to_earth(%s,%s),loc)<=%s"
                                    if operation == "radio" else "SELECT id FROM puntos ORDER BY loc <-> ll_to_earth(%s,%s)::cube LIMIT %s")
                                values = (*centers[0], parameter, *centers[0], parameter) if operation == "radio" else (*centers[0], parameter)
                                cursor.execute(query_sql, values)
                                plan = cursor.fetchone()[0][0]
                                assert "puntos_gist" in json.dumps(plan), "GiST no utilizado"
                                plans.append({"n": n, "operacion": operation, "parametro": parameter, "plan": plan})
                        cursor.execute("""SELECT count(*) * current_setting('block_size')::bigint
                                          FROM pg_buffercache WHERE relfilenode = pg_relation_filenode('puntos_gist') AND relforknumber=0
                                          AND reldatabase = (SELECT oid FROM pg_database WHERE datname=current_database())""")
                        construction[-1]["gist_cache_bytes"] = cursor.fetchone()[0]
                        write_csv(args.output / "consultas.csv", summary)
                        write_csv(args.output / "muestras.csv", samples)
                        write_csv(args.output / "construccion.csv", construction)
                        (args.output / "planes.json").write_text(json.dumps(plans, indent=2), encoding="utf-8")
        finally:
            subprocess.run(["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"], check=True, stdout=subprocess.DEVNULL)
    (args.output / "entorno.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    plot(args.output, summary, construction)
    print(f"Comparación verificada: {args.output}", flush=True)


if __name__ == "__main__":
    main()
