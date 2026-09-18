# Guía del Proyecto — MiniGestor de Base de Datos Multimodal

Documento de referencia para **(1)** probar el sistema de punta a punta y **(2)** entender la arquitectura, los archivos y cómo fluye una consulta desde el navegador hasta el disco.

---

## Parte 1 — Cómo probar que todo funciona

### 1.1 Requisitos

- Python 3.12 (ya hay un venv creado en `backend/.venv` y otro en `bd2/.venv`).
- Node + pnpm (o npm) para el frontend.

### 1.2 Levantar todo con un comando (recomendado)

Desde la raíz del monorepo `proyecto/Proyecto_BD2/`:

```bash
pnpm install        # solo la 1ra vez: instala concurrently en la raíz
pnpm setup          # solo la 1ra vez: crea backend/.venv + requirements + deps del frontend
pnpm dev            # levanta backend (8000) y frontend (5173) a la vez
```

- Backend: http://localhost:8000 — health check en http://localhost:8000/api/health
- Frontend: http://localhost:5173 — el `vite.config.js` proxea `/api` hacia `127.0.0.1:8000`.

> El puerto del backend **debe** quedar en 8000 porque el proxy de Vite apunta ahí. Si lo cambias, cambia también `frontend/vite.config.js`.

### 1.3 Levantar por separado

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # si no existe el venv
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

### 1.4 Qué deberías ver al abrir el frontend

El panel izquierdo (**FilesPanel**) lista 3 tablas sembradas automáticamente al arrancar el backend (`create_catalog` en `api/main.py`). Cada una demuestra una estructura de índice distinta:

| Tabla       | Índice sobre `id`  | `index_kind`       | Storage      | Filas |
|-------------|--------------------|--------------------|--------------|-------|
| `clientes`  | Extendible Hashing | `HASH`             | heap         | 24    |
| `ventas`    | B+ **no** agrupado | `BPLUS`            | heap         | 40    |
| `productos` | B+ **agrupado**    | `BPLUS_CLUSTERED`  | sequential   | 30    |

### 1.5 Consultas SQL para probar en el QueryPanel

El dialecto soportado es un subconjunto (ver §2.6). Prueba estas:

```sql
-- 1. Scan completo (tabla clustered → sale ORDENADA físicamente por id)
SELECT * FROM productos;

-- 2. Búsqueda por índice HASH (igualdad sobre la columna indexada)
SELECT * FROM clientes WHERE id = 10;

-- 3. Búsqueda por índice B+ no agrupado
SELECT * FROM ventas WHERE id = 15;

-- 4. Búsqueda por índice B+ agrupado
SELECT * FROM productos WHERE id = 7;

-- 5. Filtro que NO usa índice (operador != o columna no indexada) → Sequential Scan + Filter
SELECT * FROM clientes WHERE edad > 30;
SELECT nombre, ciudad FROM clientes WHERE ciudad = 'Lima';

-- 6. GROUP BY con external hashing (agrupa y cuenta)
SELECT ciudad FROM clientes GROUP BY ciudad;

-- 6b. GROUP BY con agregaciones (COUNT/SUM/AVG/MIN/MAX)
SELECT categoria, COUNT(*), SUM(monto), AVG(monto) FROM ventas GROUP BY categoria;

-- 6c. Agregación global (una sola fila)
SELECT COUNT(*), MIN(monto), MAX(monto) FROM ventas;

-- 7. ORDER BY con external sorting (k-way merge)
SELECT * FROM ventas ORDER BY monto;

-- 7b. Búsqueda por RANGO usando el índice B+ (no equality)
SELECT id FROM ventas WHERE id > 36;          -- B+ no agrupado → Range Search
SELECT id, nombre FROM productos WHERE id <= 4;  -- B+ agrupado  → Range Search
SELECT id FROM clientes WHERE id >= 22;        -- HASH no hace rangos → Scan + Filter

-- 8. INSERT / DELETE / UPDATE
INSERT INTO productos VALUES (99, 'Teclado', 120.0, 50);
SELECT * FROM productos WHERE id = 99;
UPDATE productos SET stock = 5 WHERE id = 99;
DELETE FROM productos WHERE id = 99;

-- 9. CREATE TABLE (crea una StorageTable nueva, HASH por defecto)
CREATE TABLE alumnos (id INT, nombre VARCHAR(32), nota FLOAT);
INSERT INTO alumnos VALUES (1, 'Ana', 18.5);
SELECT * FROM alumnos WHERE id = 1;

-- 10. Transacciones (bloqueo exclusivo de tabla)
BEGIN TRANSACTION;
INSERT INTO ventas VALUES (99, 3, 500, 'A');
END TRANSACTION;
```

**Qué observar en el PlanPanel** (panel de plan de ejecución, punto 2.1.5):

- Consulta 2/3/4 → paso `Index Search` con el método `HASH(id)` / `BPLUS(id)` / `BPLUS_CLUSTERED(id)`.
- Consulta 5 → paso `Sequential Scan + Filter`.
- Consulta 1 → `Sequential Scan` (sobre `sequential`, no `heap`).
- Consulta 6 / 6b → paso `Group By (external-hash)`; 6c → `Aggregate (external-hash)`.
- Consulta 7 → paso `Order By (external-merge)` (external sorting real, no `sorted()`).
- Consulta 7b → `Range Search` con `BPLUS(id)` / `BPLUS_CLUSTERED(id)`; sobre HASH cae a `Sequential Scan + Filter` (el hashing no soporta rangos).

### 1.6 Probar el backend sin frontend (curl)

```bash
curl http://localhost:8000/api/tables

curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT * FROM productos WHERE id = 7"}'
```

La respuesta trae `columns`, `rows`, `plan`, `statements` y `elapsedMs`.

### 1.7 Demos aisladas de módulos (sin servidor)

Desde `backend/` con el venv activo (o `PYTHONPATH=.`):

```bash
python -m engine.hashing.demo          # demo del extendible hashing
python -m engine.transactions.demo      # evidencia de "lost update" sin locks (70) vs con locks (120)
```

### 1.8 Probar las estructuras a mano (scripts rápidos)

Cada estructura es autónoma y se puede ejercitar en un intérprete. Ejemplo del **Sequential File + B+ agrupado** (corre desde `backend/` con `PYTHONPATH=.`):

```python
from engine.storage.sequential.sequential_file import SequentialFile
from engine.bplus import ClusteredBPlusTree

seq = SequentialFile("/tmp/t.seq", "if", key_index=0, page_size=256)  # 2 campos: int, float
tree = ClusteredBPlusTree("/tmp/t_idx", seq, key_type="int", block_factor=32)

for k in [5, 1, 9, 3, 7]:
    tree.insert(k, (k, float(k * 10)))

print(seq.scan())          # sale ordenado por clave, sin duplicados
print(tree.search(9))      # -> [(9, 90.0)]
print(seq.stats())         # páginas, overflow, borrados, reorganizaciones
seq.delete(3)
print([f for _, f in seq._ordered_with_pos()])
```

### 1.9 Checklist de verificación (qué demuestra el proyecto)

- [ ] Las 3 tablas aparecen en el panel con sus 3 tipos de índice.
- [ ] `SELECT * FROM productos` sale ordenado por `id` (orden físico = orden lógico → **clustered** real).
- [ ] Igualdad sobre la columna indexada muestra `Index Search`; lo demás muestra `Sequential Scan`/`+ Filter`.
- [ ] INSERT/DELETE/UPDATE modifican y se reflejan al re-consultar.
- [ ] `productos` tras muchos DELETE/INSERT dispara reorganización (ver `reorganizations` en `stats()`).
- [ ] La demo de transacciones muestra 70 (sin lock) vs 120 (con lock).

---

## Parte 2 — Estructura y funcionamiento (end-to-end)

### 2.0 Árbol del repositorio

```
Proyecto_BD2/
├── backend/
│   ├── api/main.py                     # FastAPI: /api/tables y /api/query
│   └── engine/
│       ├── catalog.py                  # StorageTable + create_catalog (siembra las 3 tablas)
│       ├── common/                     # contrato RID compartido
│       │   ├── rid.py                  #   as_pair()  (normaliza RID → tupla)
│       │   └── heap_adapter.py         #   to_heap_rid, heap_fetch, build_index
│       ├── storage/
│       │   ├── heap/heapfile.py        # Heap file paginado (no ordenado)
│       │   └── sequential/sequential_file.py   # Sequential file ORDENADO + overflow + reorg
│       ├── bplus/
│       │   ├── bplus_tree.py           # B+ tree en disco (índice no agrupado, devuelve RIDs)
│       │   └── clustered.py            # B+ agrupado (clave → posición en el sequential file)
│       ├── hashing/
│       │   ├── boundary.py             # empaquetado de clave/RID + stable_hash (FNV)
│       │   ├── page.py                 # Bucket + FileManager (páginas en disco, cuenta accesos)
│       │   ├── extendible_hash.py      # Extendible Hashing (índice de igualdad)
│       │   └── external_hash.py        # External hashing: group by + grace hash join
│       ├── external/external_sort.py   # External sorting (runs a disco + k-way merge)
│       ├── parser/                     # scanner → parser → nodes → visitor → executor
│       └── transactions/               # LockManager + TransactionManager (2PL estricto)
├── frontend/                           # React + Vite (light theme estilo pgAdmin)
│   └── src/
│       ├── App.jsx                     # arma los 4 paneles
│       ├── api/{client,real,mock}.js   # capa de red (client → real → fetch /api/*)
│       └── components/                 # FilesPanel, QueryPanel, ResultsPanel, PlanPanel
├── data/generate_data.py               # generador de CSV para benchmarks (2.1.6, otro compañero)
└── benchmarks/benchmark.ipynb          # análisis (borrador)
```

### 2.1 El flujo end-to-end de una consulta

```
Navegador (QueryPanel)
  │  onRun(sql)
  ▼
App.jsx → runQuery(sql)  ──►  api/client.js → api/real.js
  │                              fetch POST /api/query  {sql}
  ▼
Vite dev server  ──proxy /api──►  FastAPI  (api/main.py :8000)
  │
  ▼  @app.post("/api/query")
Scanner(sql)  →  Parser.parse_program()  →  [Select | Insert | ...]   (AST)
  │
  ▼  Executor(catalog, TransactionManager, DATA_DIR).run(sentencias)
sentencia.accept(executor)   (patrón Visitor)
  │
  ▼  visit_Select / visit_Insert / ...
StorageTable.search / insert / scan / remove       (catalog.py)
  │
  ├── clustered?  → ClusteredBPlusTree → SequentialFile   (bplus/clustered.py + sequential_file.py)
  └── si no       → Heapfile + índice (HASH o BPLUS)      (heap_adapter → índice → heap_fetch)
  │
  ▼  struct.pack/unpack sobre archivos binarios en data/runtime/*
resultado {columns, rows, plan}
  │
  ▼  respuesta JSON  →  real.js normaliza  →  ResultsPanel + PlanPanel
```

Punto clave: **el `Executor` no conoce el motor de almacenamiento.** Solo llama a una interfaz de tabla (`insert / scan / search / remove / update_rows` + atributos `name / columns / index_column / index_kind`). Esa interfaz la cumple `StorageTable`, que por dentro decide si usa heap+índice o sequential+clustered. Es el punto de integración entre el trabajo del parser (equipo) y las estructuras de indexación (2.1.2).

### 2.2 API — `api/main.py`

- Al importarse, ejecuta `catalog = create_catalog(DATA_DIR)` **una sola vez**: la primera vez siembra las 3 tablas; en arranques posteriores redescubre y reabre lo que hay en `data/runtime/` (ver §2.5). El catálogo queda como estado en memoria del proceso uvicorn.
- `GET /api/tables` → recorre el catálogo y devuelve `table_info` de cada tabla (nombre, columnas, índices, nº de filas, tipo de storage).
- `POST /api/query`:
  1. `Parser(Scanner(sql)).parse_program()` → lista de sentencias (si hay error léxico/sintáctico, responde `{error, plan:[], statements:[]}`).
  2. Crea un `Executor` nuevo por request y llama `run(sentencias)` (una salida por sentencia).
  3. Arma `statements[]` con `type`, `plan` y (`columns`+`rows`) o `message` o `error`.
  4. Devuelve el resultado de la **última** sentencia con datos (para que un `INSERT; SELECT;` muestre la tabla), más `elapsedMs`.

### 2.3 Parser SQL — `engine/parser/`

Pipeline clásico de compilador (trabajo del equipo, ya mergeado):

- **`tokens.py`** — enum `TokenType` + `KEYWORDS`.
- **`scanner.py`** — `Scanner`: análisis léxico carácter por carácter. Reconoce símbolos, números (INT/FLOAT), palabras (keyword vs identificador, case-insensitive) y strings entre comillas simples. Lanza `LexicalError`.
- **`sql_parser.py`** — `Parser`: descenso recursivo. Gramática soportada (ver comentarios de cada método):
  - `SELECT (col,... | agg(col)... | *) FROM t [WHERE cond] [GROUP BY col] [ORDER BY col]` — `agg` ∈ `COUNT/SUM/AVG/MIN/MAX` (`COUNT(*)` permitido; el resto exige columna).
  - `INSERT INTO t VALUES (v,...)`
  - `DELETE FROM t WHERE cond`
  - `UPDATE t SET col=val,... [WHERE cond]`
  - `CREATE TABLE t (col TIPO, ...)` con tipos `INT | FLOAT | VARCHAR(n)`
  - `BEGIN TRANSACTION` / `END TRANSACTION`
  - `cond` = **una** comparación `col OP valor` con `OP ∈ { =, !=, <, <=, >, >= }`. No hay `AND/OR/BETWEEN`.
- **`nodes.py`** — dataclasses del AST (`Select`, `Insert`, `Delete`, `Update`, `CreateTable`, `Compare`, `ColumnDef`, `BeginTransaction`, `EndTransaction`). Cada `Node.accept(visitor)` despacha a `visit_<ClaseNodo>` (patrón **Visitor**).
- **`visitor.py`** — clase base `Visitor`.
- **`executor.py`** — `Executor(Visitor)`: recorre el AST y ejecuta. Ver §2.4.

### 2.4 Executor — `engine/parser/executor.py`

El corazón de la ejecución. Puntos importantes:

- **`run(sentencias)`** devuelve estructurado (`{plan, columns, rows}` / `{message}` / `{error}`); `execute()` es la variante que imprime en consola.
- **`_filtrar(tabla, where)`** decide el método de acceso — **aquí se elige índice vs scan**:
  - `where is None` → `tabla.scan()` → plan `Sequential Scan`.
  - `where.op == "=" and where.column == tabla.index_column` → `tabla.search(col, val)` → plan `Index Search` con método `<index_kind>(<index_column>)`.
  - `where.op ∈ {>, >=, <, <=} and where.column == tabla.index_column` → `tabla.search_range(op, val)` → plan `Range Search`. Funciona con B+ (agrupado y no agrupado) y claves numéricas; el hashing devuelve `None` y cae al scan.
  - Cualquier otro caso (u operador no soportado por el índice) → `scan()` + filtro en memoria → plan `Sequential Scan + Filter`.
- **`visit_Select`** aplica, en orden: filtro → GROUP BY (o agregación global) → ORDER BY → proyección.
  - **GROUP BY** usa `external_group_by` de `external_hash.py` (Grace hashing con spill a disco) vía `_agg_specs`. Plan `Group By (external-hash)`. Sin agregaciones explícitas devuelve `(columna, conteo)`; con ellas soporta `COUNT/SUM/AVG/MIN/MAX`.
  - **Agregación global** (agregaciones sin `GROUP BY`, ej. `SELECT COUNT(*) FROM t`) → una sola fila. Plan `Aggregate (external-hash)`.
  - **ORDER BY** usa `external_sort` de `external_sort.py` (runs a disco + `heapq.merge` k-way). Plan `Order By (external-merge)`. El umbral de spill es la constante `MEM_BUDGET` en `executor.py` (bájala para forzar spill en la demo).
- **`visit_CreateTable`** — si hay `data_dir`, crea una `StorageTable` real en disco (por defecto `index_kind=HASH`, `index_column` = primera columna); si no, cae a la `Table` en memoria.
- **`visit_Insert/Delete/Update`** — delegan en la tabla y registran el paso en `self.plan`.
- **Transacciones**: `_bloquear_tabla` pide un lock exclusivo de tabla **solo si hay una transacción activa en el hilo**. Fuera de `BEGIN/END` no bloquea nada.
- Existe una `Table` en memoria (lista de dicts, búsqueda lineal) como fallback cuando no hay `data_dir`; la ruta real de producción usa `StorageTable`.

### 2.5 Catálogo y tabla de almacenamiento — `engine/catalog.py`

`StorageTable` es el **adaptador** que hace calzar el almacenamiento físico con la interfaz que espera el executor.

- **Constructor**: traduce el schema a un `record_format` de `struct` (`int→i`, `float→f`, `str→32s`) y bifurca:
  - `index_kind == "BPLUS_CLUSTERED"` → `is_clustered = True`. Crea un `SequentialFile` (`name.seq`) y un `ClusteredBPlusTree` encima. **No usa heap.** La clave se guarda dentro del propio registro ordenado.
  - Si no → crea un `Heapfile` (`name.dat`) + un índice secundario: `ExtendibleHashIndex` (HASH) o `BPlusTree` (BPLUS). El índice guarda **RIDs** `(page_id, slot_id)` que apuntan al heap.
- **Filas como dict con RID oculto**: `_to_dict` convierte una tupla de campos + su ubicación en un dict `{col: valor, ..., "__rid__": ubicacion}`. En clustered `__rid__` es la *posición* en el sequential file; en heap es el par `(page_id, slot_id)`.
- **`insert`**: clustered → `index.insert(clave, tupla)`; heap → `heap.insert(*valores)` y luego `index.insert(clave, rid)`.
- **`search(col, val)`**: clustered → `index.search_with_pos(val)`; heap → `index.search(val)` da RIDs y `heap_fetch` trae los campos.
- **`search_range(op, val)`**: usa `index.range_search(low, high)` (B+ agrupado o no agrupado) y post-filtra la exclusividad de `>`/`<`. Devuelve `None` si el índice es HASH o la clave no es numérica, para que el executor haga el scan con filtro.
- **`_iter_rows` / `scan`**: clustered recorre `seq._ordered_with_pos()` (ya ordenado); heap recorre página por página, slot por slot, saltando borrados.
- **`remove` / `update_rows`**: en clustered van al sequential file (borrado lógico / update; si cambia la clave, `rebuild()` del árbol). En heap borran del heap y del índice.
- **Descriptor persistente**: cada `StorageTable`, al construirse, escribe un pequeño archivo `<name>.tbl` (JSON con `name/schema/index_field/index_kind`). Es el "catálogo del sistema" que permite redescubrir las tablas tras un reinicio.
- **`create_catalog(data_dir)`**: **persistente y con redescubrimiento**. Al arrancar llama a `_load_tables`, que lee todos los `.tbl` de `data/runtime/` y reconstruye **todas** las tablas que existan en disco (incluidas las creadas en runtime con `CREATE TABLE`). Solo si no hay ningún `.tbl` (primera vez) crea las 3 tablas por defecto y las siembra (`_seed_clientes` 24, `_seed_ventas` 40, `_seed_productos` 30 en orden "revuelto" `pid = ((i*7)%30)+1` para demostrar que el clustered las ordena físicamente). La siembra está protegida por `count() == 0` para no duplicar.

### 2.6 Almacenamiento físico

Todos los archivos son binarios con `struct`; el patrón común es *header de archivo + páginas de tamaño fijo (4 KB) + slots de registro*.

#### 2.6.1 Heap file — `storage/heap/heapfile.py`

- **No ordenado**. Header de archivo `(page_size, total_páginas, total_registros, first_page_id)`; header de página `(id, nº registros, nº activos, free_list_head)`.
- Cada registro lleva un entero extra al final: `-1` = activo; si es libre, apunta al siguiente slot libre (**free list intra-página** para reusar huecos).
- `insert` busca la primera página con hueco (free list) o crea página nueva; devuelve un `RID(page_id, slot_id)`.
- `delete` es borrado lógico: encadena el slot en la free list y decrementa contadores. `update` reescribe el slot. `search` es scan lineal.

#### 2.6.2 Sequential file — `storage/sequential/sequential_file.py`

El que reescribió Michael para la parte 2.1.2 (soporte del B+ **agrupado**). Es un archivo **ordenado por clave**, paginado, con área de overflow y reorganización.

- **Header** `(main_count, total_slots, deleted_count, record_size, overflow_head)`.
- **Slot** = campos del registro + `(next, deleted)`. `next` encadena overflow; `deleted` es la lápida (tombstone).
- **Layout paginado**: `page_size=4096`, `SLOTS_PER_PAGE = (page_size − page_header) // slot_size`. `_locate(position)` traduce una **posición plana** a `(page_id, slot, page_start, offset)`, de modo que el resto del código razona con posiciones lineales aunque físicamente haya páginas de 4 KB con su propio header `(page_id, slot_count)`.
- **Área principal** `[0, main_count)`: ordenada por clave, se busca con binaria (`_bisect_right_main`).
- **Overflow**: cada registro del main tiene una cadena (`next`) con las claves de su "gap"; `overflow_head` cubre las claves menores que el primer main. Las cadenas se mantienen **ordenadas** al insertar (se empalma en su sitio). `_tails` cachea la cola de cada cadena para inserciones append rápidas.
- **`_ordered_with_pos()`**: recorre `overflow_head`, luego cada registro del main con su cadena. Cada registro se visita **exactamente una vez** → salida global ordenada y **sin duplicados** (esto arregló el bug histórico de `search_range` que duplicaba filas).
- **Reorganización**: `_should_reorganize` calcula `wasted = borrados + slots_de_overflow` y dispara si supera el 30% de `total_slots` (con un piso `reorg_floor=4` para no reorganizar con casi nada). `reorganize()` reescribe todo compactado y ordenado en el main (`_write_sorted`) y hace `reorganizations += 1`.
- **`bulk_load`**: para construcción inicial masiva — junta todo, ordena con `operator.itemgetter(key_index)` y reescribe de una; evita el O(n²) de insertar uno por uno.
- **`stats()`**: expone `page_size, slots_per_page, num_pages, total_slots, active, main_ordered, overflow, deleted, wasted_ratio, reorganizations` → alimenta el panel de plan (2.1.5).

### 2.7 Índices — `engine/bplus/` y `engine/hashing/`

Contrato común de los tres índices: `insert(key, rid)`, `search(key) → [rid...]`, `delete(key, rid=None)`, `bulk_load(pairs)`, `stats()`, `close()`. Todos cuentan accesos a disco vía `FileManager.disk_accesses`.

#### 2.7.1 B+ no agrupado — `bplus/bplus_tree.py`

- Árbol B+ persistente. Nodos de tamaño fijo (`NodeConfig` calcula el `page_size` según el tipo de clave y el `order`/block_factor). Hojas enlazadas (`next_leaf`) para barridos ordenados.
- `insert` con split de hoja/interno y crecimiento de raíz; `search` (igualdad, puede haber duplicados encadenados por hojas), `range_search(low, high)`, `scan()` (generador ordenado por hojas), `delete` lazy.
- Guarda **RIDs** `(page_id, slot_id)` → índice **secundario** sobre el heap.
- `META_FORMAT` persiste `root_id, height, order, unique, key_type`.

#### 2.7.2 B+ agrupado — `bplus/clustered.py`

- `ClusteredBPlusTree` **envuelve** un `SequentialFile`. El árbol mapea `clave → (posición_en_seq, 0)`; los datos viven en el sequential file ordenado, así que el orden físico coincide con el orden de la clave → **clustered real**.
- **Problema resuelto**: cuando el sequential file reorganiza, las posiciones cambian. El árbol detecta esto comparando `seq.reorganizations` con `self._last_reorg`; si difieren, `rebuild()` reconstruye el árbol con las posiciones nuevas.
- Al construirse, si el árbol está vacío pero el seq ya tiene datos, hace `rebuild()` automático.
- `search_with_pos(key)` devuelve `(posición, campos)` saltando borrados; `search` devuelve solo campos; `range_search`, `delete`, `stats`, `close`.

#### 2.7.3 Extendible Hashing — `hashing/extendible_hash.py`

- Directorio de `2^global_depth` punteros a buckets; cada bucket con `local_depth`. `_dir_index` usa `stable_hash` (FNV-1a, en `boundary.py`) enmascarado a `global_depth` bits.
- `insert`: si el bucket está lleno y se puede separar (`_can_split`: hay al menos 2 hashes distintos), hace `_split` (redistribuye por el bit `local_depth`); si el directorio se queda corto, lo duplica (`_double_directory`). Si no se puede separar (todas las claves colisionan o se alcanzó `MAX_GLOBAL_DEPTH`), usa cadena de **overflow**.
- `search` de **igualdad** (índice secundario, devuelve RIDs). `delete` recorre bucket + overflow.
- Persistencia: `.dir` (header + punteros del directorio) y `.buk` (buckets).

#### 2.7.4 Soporte de páginas y claves — `hashing/page.py`, `hashing/boundary.py`

- **`page.py`**: `BucketConfig`/`Bucket` (empaquetado de un bucket), y `FileManager` (lee/escribe/append de páginas de tamaño fijo y **cuenta `disk_accesses`**). El B+ tree reutiliza `FileManager`.
- **`boundary.py`**: contrato de serialización de claves y RIDs (`key_format`, `pack_key`, `unpack_key`, `pack_rid`, `unpack_rid`, `RID_SIZE`) y `stable_hash` (FNV-1a de 64 bits, determinista entre corridas — importante para que el hash en disco no cambie).

> Nota de cleanup pendiente: `boundary`/`FileManager` viven en `hashing/` pero `bplus/` los importa desde ahí; convendría promoverlos a `common/`.

### 2.8 Algoritmos externos — `engine/external/` y `hashing/external_hash.py`

Parte 2.1.2 de "external algorithms". El sort y el group_by **ya están cableados** al executor (§2.4); el `grace_hash_join` sigue disponible pero sin sintaxis `JOIN` en la gramática:

- **`external/external_sort.py`** — `external_sort(rows, key_fn, mem_budget, reverse)`: genera *runs* ordenados a disco (pickle) cuando el chunk supera `mem_budget`, y luego los fusiona con `heapq.merge` (**k-way merge**). Soporta asc/desc. **Lo usa `ORDER BY`.**
- **`hashing/external_hash.py`**:
  - `external_group_by(...)`: agrupación tipo *Grace hash* — si hay más claves que `mem_budget`, particiona a disco por hash y recursa por partición (con más bits de hash). Acumula `count/sum/min/max/avg`. **Lo usa `GROUP BY` y la agregación global.**
  - `grace_hash_join(left, right, left_key, right_key, ...)`: **hash join** particionado — reparte ambos lados por hash a disco, y por cada par de particiones hace build (dict) + probe. Recursa si una partición no cabe.

### 2.9 Transacciones — `engine/transactions/`

2PL **estricto**, bloqueos exclusivos a nivel de recurso (tabla o página).

- **`models.py`**: `Transaction(transaction_id, thread_id, state)`, `TransactionState (ACTIVE/ENDED)`, `TransactionError`.
- **`resources.py`**: `Resource(tipo, nombre[, id])` — lo que se protege.
- **`lock_manager.py`**: `LockManager` mantiene `owners[resource] = transaction_id`, coordina la espera con `threading.Condition` (timeout 5 s) y registra historial `WAIT/ACQUIRED/RELEASED`.
- **`manager.py`**: `TransactionManager` — una transacción activa por `thread_id`; `begin/current/end/acquire`. `end()` hace `release_all` (libera todo hasta el END → 2PL estricto).
- **`demo.py`**: evidencia de *lost update* — dos hilos sobre un valor inicial 100 (uno +50, otro −30). Sin locks el resultado es 70 (una escritura pisa a la otra); con locks es 120.
- **Límites actuales**: no hay ROLLBACK, ni detección de deadlocks, ni bloqueos compartidos, ni niveles de aislamiento configurables.

### 2.10 Frontend — `frontend/src/`

React + Vite, tema claro estilo pgAdmin.

- **`main.jsx`** monta `<App/>`; **`App.jsx`** guarda estado (`tables`, `result`, `loading`), pide `listTables()` al montar y tras cada query, y ejecuta `runQuery(sql)`.
- **`api/client.js`** → reexporta desde **`api/real.js`** (hay un `mock.js` de respaldo, no usado). `real.js` hace `fetch('/api/tables')` y `fetch('/api/query')` y **normaliza** la respuesta (pasos del plan, statements, filas) para que los componentes reciban siempre la misma forma.
- **`vite.config.js`** proxea `/api` → `http://127.0.0.1:8000` (se usa `127.0.0.1` y no `localhost` para evitar el ECONNREFUSED por IPv6).
- **Componentes**:
  - `FilesPanel` — lista de tablas con columnas, tipo de índice y storage.
  - `QueryPanel` — textarea de SQL + botón "Ejecutar" (`onRun`).
  - `ResultsPanel` — tabla de resultados (`columns`/`rows`) o mensaje/error.
  - `PlanPanel` — pasos del plan de ejecución (op, método, detalle, filas) → punto 2.1.5.

### 2.11 Datos y benchmarks

- **`data/generate_data.py`** — genera CSV (`records_N.csv`, `details_N.csv`) para N = 1k/10k/100k, semilla 2026, parametrizable con `--sizes/--seed/--output-dir`. Es insumo para la parte experimental (2.1.6, otro compañero).
- **`benchmarks/benchmark.ipynb`** — borrador de análisis (mediciones desactivadas hasta cablear todo).

---

## Apéndice — Mapa "qué archivo hace qué" (rápido)

| Necesito entender...                        | Mira aquí |
|---------------------------------------------|-----------|
| Cómo entra una consulta HTTP                | `api/main.py` |
| Cómo se tokeniza/parsea el SQL              | `parser/scanner.py`, `parser/sql_parser.py`, `parser/nodes.py` |
| Cómo se ejecuta y se elige índice vs scan   | `parser/executor.py` (`_filtrar`, `visit_Select`) |
| Cómo se conecta el motor con las tablas     | `catalog.py` (`StorageTable`) |
| Heap (no ordenado) + free list              | `storage/heap/heapfile.py` |
| Sequential file ordenado + overflow + reorg | `storage/sequential/sequential_file.py` |
| B+ no agrupado (RIDs)                        | `bplus/bplus_tree.py` |
| B+ agrupado (clave→posición)                | `bplus/clustered.py` |
| Extendible hashing                          | `hashing/extendible_hash.py` (+ `page.py`, `boundary.py`) |
| External sort (ORDER BY grande)             | `external/external_sort.py` |
| External hashing (GROUP BY / JOIN grandes)  | `hashing/external_hash.py` |
| Transacciones / locks                       | `transactions/` (`manager.py`, `lock_manager.py`) |
| Interfaz web                                | `frontend/src/App.jsx` + `components/` + `api/real.js` |

### Limitaciones conocidas (para no llevarse sorpresas en la demo)

- El `WHERE` acepta **una sola** comparación (sin `AND/OR/BETWEEN`). Igualdad y rango (`> >= < <=`) sobre la columna indexada usan el índice (B+); el resto cae a scan.
- Búsqueda por rango: solo la aprovechan los índices B+ (agrupado y no agrupado) con claves numéricas; el extendible hashing no soporta rangos (cae a scan + filtro).
- **No hay `JOIN`** en la gramática: `grace_hash_join` está implementado pero no es alcanzable desde SQL.
- El catálogo es **persistente**: se siembra solo la primera vez y en arranques posteriores redescubre las tablas leyendo los descriptores `.tbl` de `data/runtime/`. Las tablas creadas en runtime con `CREATE TABLE` también sobreviven a reinicios. Para volver al estado sembrado inicial, borra la carpeta `data/runtime/`.
