# RAG SciELO

Chatbot que responde preguntas sobre artículos científicos en español de
[SciELO](https://huggingface.co/datasets/nglaura/scielo-summarization) usando el motor BD2
como base de datos. Es una aplicación aparte: solo habla con el motor por `POST /api/query`.

```
navegador ─► servidor.py ─► buscador.py ─► generador.py ─► GPT-6 Luna
                               │   ▲
                     embeddings.py (multilingual-e5-small, local)
                               │ SQL por HTTP
                          motor BD2 (puerto 8000)
```

## Qué guarda el motor

| Tabla | Columnas | Índices |
|---|---|---|
| `articulos` | id, codigo, titulo, autores, revista, pais, fecha, anio, url_pdf, abstract | B+ por `id` |
| `chunks` | id, articulo_id, orden, pais, anio, texto, emb `VECTOR(384)` | `FULLTEXT` (BM25) sobre `texto`, `HNSW` coseno sobre `emb` |

`pais` y `anio` se repiten en `chunks` porque `MATCH` y `SIMILAR_TO` no admiten `JOIN`;
así los filtros van en el mismo `WHERE`.

## Búsqueda

| Modo | Consulta al motor |
|---|---|
| BM25 | `SELECT …, SCORE() FROM chunks WHERE MATCH(texto, '…') USING BM25 LIMIT 20` |
| Embeddings | `SELECT …, SIMILARITY_SCORE() FROM chunks WHERE SIMILAR_TO(VECTOR(…), k=20) USING HNSW WITH METRIC=cosine` |
| Híbrido | las dos anteriores, fusionadas con Reciprocal Rank Fusion: `Σ 1 / (60 + posición)` |

La búsqueda usa los últimos tres mensajes del usuario, para que una repregunta
("¿y en niños?") conserve el tema de la conversación.

## Instalación

```bash
pnpm setup:rag
cp rag/.env.example rag/.env
```

Luego escribe tu clave en `rag/.env` (`OPENAI_API_KEY=...`). Ese archivo está en `.gitignore`.

## Ingesta

Con el motor levantado (`pnpm dev:backend`):

```bash
cd rag
.venv/bin/python ingesta.py --limite 50
.venv/bin/python ingesta.py
```

- Descarga el split `test` (1159 artículos, 67 MB) en `data/rag/test/`.
- Limpia el texto: une las palabras y quita encabezados y pies de página repetidos usando sus coordenadas.
- Extrae título, autores y revista con el LLM. Se guardan en `data/rag/test/metadata.jsonl` y no se vuelven a pedir.
- Parte cada artículo en chunks de 200 palabras con 40 de solapamiento y calcula sus embeddings
  (se guardan en `data/rag/test/embeddings_N.npy`).
- Recrea las tablas, inserta por lotes y crea los índices al final.

Opciones: `--limite N` toma N artículos repartidos en todo el split, `--sin-llm` omite la metadata,
`--sin-cargar` prepara todo sin tocar el motor.

## Uso

```bash
pnpm dev:rag
```

Abre http://localhost:8100. `pnpm dev` levanta el motor, el frontend y el RAG juntos.

## Docker

El RAG es un servicio opcional del `docker-compose.yml` (profile `rag`). `docker compose up` sigue
levantando solo el motor y el frontend.

```bash
cp rag/.env.example rag/.env
docker compose --profile rag up -d --build
docker compose --profile rag run --rm rag python ingesta.py
```

Abre http://localhost:8100.

- El motor de Docker guarda sus tablas en el volumen `runtime`, aparte de `data/runtime`, así que la ingesta
  se corre una vez dentro de Docker.
- `data/rag` se monta en el contenedor: si ya están el dataset y los embeddings, la ingesta los reutiliza
  y tarda unos minutos. Si no, los descarga y los calcula (cerca de una hora en CPU).
- El modelo de embeddings se descarga al primer arranque y queda en el volumen `hf_cache`.
- La clave se lee de `rag/.env` en tiempo de ejecución. No entra en la imagen.

## Evaluación

```bash
cd rag
.venv/bin/python evaluacion/generar_preguntas.py --cantidad 200
.venv/bin/python evaluacion/evaluar.py
```

Genera preguntas parafraseadas a partir de chunks al azar y mide, para cada modo, Recall@1/5/10
y MRR a nivel de chunk y de artículo, más la latencia. Los resultados quedan en `benchmarks/rag_results/`.
