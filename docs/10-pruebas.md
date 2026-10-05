# ✅ Pruebas

Las pruebas se ejecutan desde `backend/` con el Python del entorno virtual:

```bash
cd backend
.venv/bin/python -m engine.parser.test_sql
.venv/bin/python -m engine.parser.test_spatial_sql
.venv/bin/python -m engine.test_rtree
.venv/bin/python -m engine.parser.testing
```

| Suite | Qué cubre |
|---|---|
| `engine.parser.test_sql` | Parser y ejecución con los tres índices y en memoria; restricciones (`PRIMARY KEY`, `NOT NULL`, `VARCHAR(n)`, `DATE`) que persisten al reabrir; JOIN externo y JOIN de varias tablas comparados contra SQLite; `EXPLAIN`; bloqueos entre hilos; API |
| `engine.parser.test_spatial_sql` | SQL espacial: radio, k-NN y polígonos sin barrido, mantenimiento del R-Tree al modificar, persistencia, datos del mapa y `LIMIT` |
| `engine.test_rtree` | R-Tree: inserción, split, borrado, radio, k-NN y polígonos contra fuerza bruta |
| `engine.parser.testing` | Ida y vuelta AST → SQL → AST, consultas que deben fallar y textos de los mensajes de error |

Las tres primeras terminan con una línea de confirmación (`OK: ...`) o se detienen en el primer `AssertionError`. `testing` imprime cuántos casos pasaron en cada grupo.

Demostraciones que se pueden correr aparte:

```bash
.venv/bin/python -m engine.transactions.demo
.venv/bin/python -m engine.hashing.demo
```

La primera es la simulación de concurrencia con hilos; la segunda muestra el hash extensible y el `GROUP BY` y `JOIN` por hash externo.

Las comparaciones de rendimiento no son pruebas: están en [benchmarks](../benchmarks/README.md).

---

<div align="center">

[← Interfaz](09-interfaz.md) · [Inicio](../README.md) · [Alcance y limitaciones →](11-limitaciones.md)

</div>
