# MiniGestor de Base de Datos Multimodal — Presentación

Guion de sustentación: **(1)** estructura del proyecto y **(2)** demo en vivo con 6 bloques de SQL.

---

## Parte 1 — Estructura del proyecto

### Arquitectura por capas

```
   Frontend (React + Vite)         escribes SQL y ves resultado + plan de ejecución
        │  POST /api/query
        ▼
   API REST (FastAPI)              recibe el SQL, orquesta la respuesta
        │
        ▼
   Parser SQL                      scanner → parser → AST (patrón Visitor)
        │
        ▼
   Executor                        recorre el AST, ELIGE el método de acceso, arma el plan
        │
        ▼
   Catálogo (StorageTable)         adaptador: conecta cada tabla con su storage + índice
        │
        ├─► Datos:   Heap (.dat, desordenado)   │  Sequential (.seq, ordenado)
        └─► Índices: B+ (.meta/.nodes)  ·  Extendible Hash (.dir/.buk)
```

### Qué implementa cada pieza

| Capa | Componente | Rol |
|---|---|---|
| Almacenamiento | **Heap file** | datos sin orden, con lista libre para reusar borrados |
| Almacenamiento | **Sequential file** | datos ordenados por clave + overflow + reorganización |
| Índice | **B+ tree** | igualdad **y** rango; agrupado (clustered) y no agrupado |
| Índice | **Extendible Hashing** | igualdad; directorio + buckets con split dinámico |
| Externos | **External Sorting** | ORDER BY que no cabe en RAM (runs a disco + k-way merge) |
| Externos | **External Hashing** | GROUP BY con particionado a disco (Grace hash) |
| Motor | **Parser + Executor** | SQL → plan de ejecución; elige índice vs scan |
| Motor | **Transacciones** | BEGIN/END con bloqueo exclusivo por tabla (2PL estricto) |

### Las 3 tablas sembradas (una por estructura)

| Tabla | Índice sobre `id` | Datos | Filas |
|---|---|---|---|
| `clientes` | Extendible **Hash** | heap (`.dat`) | 24 |
| `ventas` | **B+ no agrupado** | heap (`.dat`) | 40 |
| `productos` | **B+ agrupado** (clustered) | sequential (`.seq`) | 30 |

> Idea central: el **índice** guarda solo `(clave → puntero)`; los **datos completos** viven en el heap o el sequential. En el clustered, el puntero es una *posición* dentro de un archivo ya ordenado → el orden físico coincide con el de la clave.

Detalle técnico completo en [GUIA_PROYECTO.md](GUIA_PROYECTO.md).

---

## Parte 2 — Demo en vivo

> En cada bloque, mira el **panel de Plan de Ejecución**: ahí se ve qué estructura eligió el motor.

### Bloque 1 — Las 3 estructuras de indexación (búsqueda por igualdad)

```sql
SELECT * FROM clientes  WHERE id = 10;
SELECT * FROM ventas    WHERE id = 15;
SELECT * FROM productos WHERE id = 7;
SELECT * FROM productos;
```

**Qué demuestra:** la misma consulta (`WHERE id = ...`) usa una estructura distinta según la tabla → plan `Index Search` con método **`HASH(id)`**, **`BPLUS(id)`** y **`BPLUS_CLUSTERED(id)`**. El `SELECT *` de `productos` sale **ordenado por id sin ordenar nada**: es la prueba de que el B+ agrupado mantiene el orden físico.

---

### Bloque 2 — El motor elige el método de acceso (índice vs rango vs scan)

```sql
SELECT id, monto  FROM ventas    WHERE id > 36;
SELECT id, nombre FROM productos WHERE id <= 4;
SELECT id         FROM clientes  WHERE id >= 22;
SELECT nombre, ciudad FROM clientes WHERE ciudad = 'Lima';
```

**Qué demuestra:** el B+ resuelve **rangos** con `Range Search` (`BPLUS(id)` y `BPLUS_CLUSTERED(id)`). El **hash no soporta rangos**, así que `clientes WHERE id >= 22` cae elegantemente a `Sequential Scan + Filter`. Y una columna **no indexada** (`ciudad`) también hace scan con filtro. El motor decide, no el usuario.

---

### Bloque 3 — Algoritmos externos (sorting y hashing)

```sql
SELECT * FROM ventas ORDER BY monto;
SELECT categoria, COUNT(*), SUM(monto), AVG(monto) FROM ventas GROUP BY categoria;
SELECT COUNT(*), MIN(monto), MAX(monto) FROM ventas;
```

**Qué demuestra:** `ORDER BY` usa **external sorting** (plan `Order By (external-merge)`, runs a disco + k-way merge). `GROUP BY` usa **external hashing** (plan `Group By (external-hash)`) y soporta agregaciones **COUNT / SUM / AVG / MIN / MAX**. La última es una **agregación global** (una sola fila de resumen).

---

### Bloque 4 — Modificación de datos y persistencia (DML)

```sql
INSERT INTO productos VALUES (99, 'Teclado', 120.0, 50);
SELECT * FROM productos WHERE id = 99;
UPDATE productos SET stock = 5 WHERE id = 99;
DELETE FROM productos WHERE id = 99;
```

**Qué demuestra:** `INSERT`/`UPDATE`/`DELETE` sobre la tabla clustered (se inserta en su posición ordenada, se actualiza, y el borrado es lógico con lápida). **Persistencia:** si insertas algo y reinicias el backend, los cambios **siguen ahí** (los datos viven en disco y el catálogo se redescubre desde los descriptores `.tbl`).

---

### Bloque 5 — Crear índices desde SQL (DDL con `USING`)

```sql
CREATE TABLE cursos (id INT PRIMARY KEY, nombre VARCHAR(32)) USING BPLUS;
CREATE TABLE stock  (id INT PRIMARY KEY, cantidad INT) USING BPLUS_CLUSTERED;
INSERT INTO cursos VALUES (1, 'BD2');
INSERT INTO cursos VALUES (2, 'Redes');
SELECT * FROM cursos WHERE id = 2;
```

**Qué demuestra:** desde el propio SQL se elige la **columna indexada** (`PRIMARY KEY`) y el **tipo de índice** (`USING BPLUS` / `BPLUS_CLUSTERED` / `HASH`). La tabla nueva aparece en el panel lateral con su tipo, y la búsqueda ya usa su índice (`Index Search BPLUS(id)`).

---

### Bloque 6 — Transacciones y concurrencia (2PL)

> ⚠️ **Importante:** envía las 4 líneas **juntas en una sola ejecución** (un clic en "Ejecutar"). El contexto transaccional vive por consulta; si las corres una por una, el `END TRANSACTION` no encontrará la transacción abierta.

```sql
BEGIN TRANSACTION;
INSERT INTO ventas VALUES (99, 3, 500, 'A');
DELETE FROM ventas WHERE id = 99;
END TRANSACTION;
```

**Qué demuestra:** dentro de `BEGIN … END` cada operación toma un **bloqueo exclusivo** de la tabla (2PL estricto: los locks se retienen hasta el `END`). Fuera de transacción, las operaciones no bloquean. (La evidencia de *lost update* sin locks vs con locks está en `engine.transactions.demo`, ejecutable con `python -m engine.transactions.demo`.)

---

## Cierre — qué se cubrió

```
 ✔ 3 estructuras de indexación:  Hash · B+ no agrupado · B+ agrupado
 ✔ Métodos de acceso:            Index Search · Range Search · Sequential Scan (+Filter)
 ✔ Algoritmos externos:          External Sorting (ORDER BY) · External Hashing (GROUP BY)
 ✔ Agregaciones:                 COUNT · SUM · AVG · MIN · MAX (por grupo y globales)
 ✔ DML:                          INSERT · UPDATE · DELETE + persistencia en disco
 ✔ DDL:                          CREATE TABLE con PRIMARY KEY y USING <índice>
 ✔ Transacciones:                BEGIN/END con bloqueo exclusivo (2PL estricto)
 ✔ Plan de ejecución:            visible en el panel por cada consulta
```
