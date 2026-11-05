# ✅ Pruebas

Las pruebas se ejecutan desde `backend/` con el Python del entorno virtual:

```bash
cd backend
.venv/bin/python -m engine.parser.test_sql
.venv/bin/python -m engine.parser.test_spatial_sql
.venv/bin/python -m engine.test_rtree
.venv/bin/python -m engine.test_text_storage
.venv/bin/python -m engine.parser.test_text_sql
.venv/bin/python -m engine.fulltext.test_fulltext
.venv/bin/python -m engine.parser.test_fulltext_sql
.venv/bin/python -m engine.parser.testing
```

| Suite | Qué cubre |
|---|---|
| `engine.parser.test_sql` | Parser y ejecución con los tres índices y en memoria; restricciones (`PRIMARY KEY`, `NOT NULL`, `VARCHAR(n)`, `DATE`) que persisten al reabrir; JOIN externo y JOIN de varias tablas comparados contra SQLite; `EXPLAIN`; bloqueos entre hilos; API |
| `engine.parser.test_spatial_sql` | SQL espacial: radio, k-NN y polígonos sin barrido, mantenimiento del R-Tree al modificar, persistencia, datos del mapa y `LIMIT` |
| `engine.test_rtree` | R-Tree: inserción, split, borrado, radio, k-NN y polígonos contra fuerza bruta |
| `engine.test_text_storage` | Archivo de textos: referencias, basura, compactación al 30 % con heap y secuencial, persistencia y restricciones de índices sobre `TEXT` |
| `engine.parser.test_text_sql` | `TEXT` desde SQL en memoria y con los tres índices: `LIKE`, `JOIN`, `GROUP BY`, `UPDATE`, `DELETE`, reapertura, `DROP TABLE` e importación de CSV |
| `engine.fulltext.test_fulltext` | Preprocesamiento, SPIMI con uno y varios bloques y con merge por niveles (los tres índices deben ser idénticos byte a byte), TF-IDF + coseno y BM25 contra un cálculo por fuerza bruta |
| `engine.parser.test_fulltext_sql` | `MATCH`, `SCORE()`, `USING TF_IDF/BM25 WITH ...`, `LIMIT`, filtros, `ORDER BY` por puntaje, reconstrucción tras `INSERT/UPDATE/DELETE`, persistencia, `DROP` y errores con HASH, BPLUS y BPLUS_CLUSTERED |
| `engine.parser.testing` | Ida y vuelta AST → SQL → AST, consultas que deben fallar y textos de los mensajes de error |

Todas menos `testing` terminan con una línea de confirmación (`OK: ...`) o se detienen en el primer `AssertionError`. `testing` imprime cuántos casos pasaron en cada grupo.

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
