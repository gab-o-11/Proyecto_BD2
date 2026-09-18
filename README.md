# Proyecto_BD2 — MiniGestor de Base de Datos Multimodal

Monorepo del proyecto integrador de Base de Datos 2 (Ciclo 2026-2).

## Estructura

```
Proyecto_BD2/
├── backend/
│   ├── engine/
│   │   ├── storage/
│   │   │   ├── heap/            heapfile.py
│   │   │   └── sequential/      sequential_file.py
│   │   ├── hashing/            indice extendible + external hashing (group by / join)
│   │   ├── parser/             scanner, parser y ejecutor SQL
│   │   ├── transactions/       transacciones y control de concurrencia
│   │   └── common/             contrato compartido (RID, record, page)
│   ├── api/                    API REST (FastAPI)
│   └── requirements.txt
├── frontend/                   interfaz (React + Vite)
├── data/                       generador de datos y archivos generados (ignorados por git)
└── README.md
```

## Desarrollo con un comando (pnpm)

```
pnpm install    # instala concurrently (raíz)
pnpm setup      # solo 1ra vez: crea backend/.venv, instala requirements y deps del frontend
pnpm dev        # levanta backend (8000) + frontend (5173) juntos
```

`pnpm dev` usa el binario del venv directo (`backend/.venv/bin/uvicorn`),
sin necesidad de activarlo. El puerto del backend debe seguir en 8000
porque `frontend/vite.config.js` proxea `/api` hacia ahí.

## Backend

Por separado (equivale a `pnpm dev:backend`):

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload
```

API en http://localhost:8000 (health: `/api/health`, demo: `/api/hashing/demo`).

Demo del motor de hashing sin servidor:

```
cd backend
python -m engine.hashing.demo
```

## Transacciones y control de concurrencia

El módulo `backend/engine/transactions/` administra el ciclo de vida de las
transacciones y evita que dos operaciones modifiquen al mismo tiempo un mismo
recurso. El desarrollo se organizó en los siguientes avances.

### 1. Contexto transaccional

Una transacción representa una secuencia de operaciones que debe conservar un
estado consistente. La clase `Transaction` almacena:

- `transaction_id`: identifica de forma única a la transacción.
- `thread_id`: relaciona la transacción con el hilo que la está ejecutando.
- `state`: indica si la transacción está activa (`ACTIVE`) o terminó (`ENDED`).

`TransactionManager.begin()` crea la transacción y la registra usando el
identificador del hilo actual. Esto permite que varios hilos trabajen con el
mismo administrador, pero cada uno encuentre únicamente su propia transacción.
No se permite iniciar una segunda transacción activa en el mismo hilo.

### 2. Bloqueos exclusivos por recurso

`Resource` identifica aquello que se desea proteger. Un recurso puede
representar una tabla o una página mediante su tipo, nombre e identificador.

`LockManager` mantiene qué transacción es propietaria de cada recurso. El
bloqueo es exclusivo: mientras una transacción lo posee, las demás deben
esperar. La espera se coordina con `threading.Condition` y tiene un tiempo
máximo para evitar que un hilo espere indefinidamente.

Los eventos `WAIT`, `ACQUIRED` y `RELEASED` permiten observar cuándo una
transacción esperó, obtuvo o liberó un recurso.

### 3. Retención de bloqueos hasta END TRANSACTION

Los bloqueos obtenidos por una transacción se mantienen durante todas sus
operaciones. `TransactionManager.end()` libera todos sus recursos mediante
`release_all()`, cambia su estado a `ENDED` y elimina su relación con el hilo.

Este comportamiento corresponde a la idea principal del protocolo 2PL
estricto: los bloqueos exclusivos no se liberan antes de finalizar la
transacción. De esta manera, otra transacción no puede observar ni sobrescribir
un recurso mientras la primera todavía está trabajando con él.

### 4. Conexión de BEGIN y END TRANSACTION con el ejecutor

El ejecutor SQL utiliza una instancia de `TransactionManager` para conectar
las sentencias del parser con el control de concurrencia:

1. `BEGIN TRANSACTION` llama a `begin()`.
2. `SELECT`, `INSERT` y `DELETE` solicitan un bloqueo sobre la tabla cuando hay
   una transacción activa.
3. Si otra transacción posee la tabla, la operación espera.
4. `END TRANSACTION` llama a `end()` y libera los bloqueos retenidos.

Las operaciones ejecutadas fuera de una transacción explícita conservan el
comportamiento normal del ejecutor y no solicitan estos bloqueos.

### 5. Evidencia de ejecución simultánea

`demo.py` compara dos ejecuciones sobre un valor inicial de `100`. Un hilo suma
`50` y otro resta `30`.

Sin bloqueo, ambos hilos leen el mismo valor inicial y una escritura reemplaza
a la otra. El resultado es `70`, aunque el resultado correcto debería ser
`120`. Este problema se conoce como actualización perdida.

Con bloqueo exclusivo, la segunda transacción espera a que la primera termine.
Luego lee el valor actualizado y el resultado final es `120`.

La demostración se ejecuta desde `backend/`:

```
python -m engine.transactions.demo
```

La salida permite comprobar:

```
Escenario sin bloqueos
Resultado esperado: 120
Resultado obtenido: 70
Actualización perdida: True

Escenario con bloqueos
Resultado esperado: 120
Resultado obtenido: 120
Espera detectada: True
```

### Flujo completo

```
BEGIN TRANSACTION
        |
        v
crear Transaction y asociarla al hilo
        |
        v
solicitar bloqueo del recurso
        |
        +---- ocupado ----> esperar
        |                     |
        <---------------------+
        |
        v
ejecutar SELECT, INSERT o DELETE
        |
        v
END TRANSACTION
        |
        v
liberar recursos y finalizar la transacción
```

### Capacidades y límites actuales

La implementación permite:

- Mantener una transacción activa diferente por hilo.
- Asignar identificadores independientes a las transacciones.
- Aplicar bloqueos exclusivos a tablas o páginas.
- Hacer esperar a una transacción cuando el recurso está ocupado.
- Liberar todos los bloqueos al finalizar la transacción.
- Detectar secuencias inválidas de `BEGIN` y `END`.
- Detectar una espera que supera el tiempo máximo.

En esta etapa no se implementan `ROLLBACK`, detección de deadlocks, bloqueos
compartidos ni niveles de aislamiento configurables.

## Frontend

Por separado (equivale a `pnpm dev:frontend`):

```
cd frontend
npm install
npm run dev
```

Interfaz en http://localhost:5173 (proxy `/api` hacia el backend en el puerto 8000).

## Datos para benchmarks

```
python data/generate_data.py
```

Genera `records_N.csv` (`id,category,value`) y `details_N.csv`
(`id,record_id,value`) en `data/generated/` para N = 1 000, 10 000 y
100 000. Cada detalle referencia un registro; hay dos detalles por registro.
La semilla predeterminada es 2026. Se pueden cambiar los tamaños, la semilla
y la ruta con `--sizes`, `--seed` y `--output-dir`.

El borrador del análisis está en `benchmarks/benchmark.ipynb`; sus mediciones
están desactivadas hasta conectar las estructuras restantes.
