# 🚀 Instalación y primeros pasos

## Requisitos

| Herramienta | Versión |
|---|---|
| Python | 3.11 o superior |
| Node.js | 18 o superior |
| pnpm | 9 (`corepack enable` lo instala) |

## Levantar todo con un comando

```bash
pnpm install
pnpm run setup
pnpm dev
```

- `pnpm install` instala [mprocs](https://github.com/pvolok/mprocs), que corre backend y frontend en la misma terminal.
- `pnpm run setup` se corre una sola vez: crea `backend/.venv`, instala las dependencias de Python e instala las del frontend.
- `pnpm dev` levanta el backend en <http://localhost:8000> y el frontend en <http://localhost:5173>.

> [!IMPORTANT]
> El backend tiene que quedar en el puerto **8000**: el frontend reenvía `/api` a ese puerto (`frontend/vite.config.js`).

<details>
<summary>Levantar cada parte por separado</summary>

```bash
pnpm dev:backend
pnpm dev:frontend
```

O sin pnpm:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

</details>

## Datos de demo

El repositorio no guarda CSV. Este script genera seis tablas relacionadas, con ubicaciones dentro de Lima, en `data/demo/`:

```bash
python3 data/generar_demo.py
```

Siempre produce los mismos datos (semilla fija). Impórtalos desde el panel **Archivos** con esta configuración:

| CSV | Filas | Tipo de índice | Columna índice | Columnas POINT |
|---|---:|---|---|---|
| `clientes.csv` | 10 000 | B+ Tree | `id` | `ubicacion` |
| `productos.csv` | 10 000 | B+ Tree clustered | `id` | |
| `tiendas.csv` | 10 000 | Hash extensible | `id` | `ubicacion` |
| `pedidos.csv` | 10 000 | B+ Tree | `id` | |
| `detalle_pedidos.csv` | 12 007 | Hash extensible | `pedido_id` | |
| `repartos.csv` | 7 974 | B+ Tree | `pedido_id` | `destino` |

Así la base usa todas las estructuras a la vez. El orden de importación no importa. Cada columna `POINT` recibe su R-Tree automáticamente.

> [!TIP]
> Después de importar, crea un índice secundario para ver al planificador elegirlo:
> ```sql
> CREATE INDEX idx_pedidos_estado ON pedidos (estado);
> ```

## Dónde se guardan los datos

Las tablas viven en `data/runtime/`: un descriptor `.tbl`, las estadísticas `.stats`, el archivo de datos (`.dat` o `.seq`) y un par de archivos por índice. Al reiniciar el backend, todo se vuelve a abrir desde disco.

- Para usar otra carpeta, define `BD2_DATA_DIR` antes de levantar el backend.
- Para empezar de cero, usa el botón **Borrar base de datos** del panel Archivos o ejecuta `DROP TABLE` sobre cada tabla.

## Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `Address already in use` al hacer `pnpm dev` | Otro proceso usa el puerto 8000 o 5173. Ciérralo o busca cuál es con `ss -ltnp \| grep -E ':(8000\|5173)'`. |
| `ERR_PNPM_... packages field missing or empty` | Hay un `pnpm-workspace.yaml` incompleto en `frontend/`. Bórralo. |
| `la columna 't.ubicacion' no existe` | La tabla se importó con otro CSV. Revisa sus columnas en el panel Archivos, haz `DROP TABLE` y vuelve a importar. |
| `la tabla 'x' se creó sin soporte para NULL` | La tabla es anterior al formato con valores nulos. Vuelve a crearla o importarla. |

---

<div align="center">

[Inicio](../README.md) · [SQL →](02-sql.md)

</div>
