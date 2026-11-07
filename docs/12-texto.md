# 🔎 Búsqueda de texto

## Índice FULLTEXT

```sql
CREATE TABLE documentos (id INT PRIMARY KEY, titulo VARCHAR(40), contenido TEXT);
CREATE INDEX idx_contenido ON documentos (contenido) USING FULLTEXT;
DROP INDEX idx_contenido;
```

- Solo se indexan columnas `TEXT` y cada una admite un índice `FULLTEXT`.
- El índice se construye con **SPIMI** al crearlo. Las filas con `NULL` no entran.
- Si la tabla cambia (`INSERT`, `UPDATE`, `DELETE`), el índice queda marcado como desactualizado y se reconstruye en la siguiente búsqueda. La marca sobrevive a un reinicio.

## Consultas

```sql
SELECT * FROM documentos
WHERE MATCH(contenido, 'base de datos vectorial')
USING TF_IDF LIMIT 10;

SELECT *, SCORE() AS relevancia FROM documentos
WHERE MATCH(contenido, 'machine learning')
USING BM25
ORDER BY relevancia DESC;

SELECT id, titulo, SCORE() FROM documentos
WHERE MATCH(contenido, 'inflación') AND titulo LIKE '%Perú%'
USING BM25 WITH K1=1.5, B=0.6
LIMIT 5;
```

| Parte | Qué hace |
|---|---|
| `MATCH(col, 'texto')` | devuelve los documentos que contienen al menos un término de la consulta, del más al menos relevante |
| `USING TF_IDF` / `USING BM25` | elige el ranking; sin `USING` se usa `BM25` |
| `WITH K1=…, B=…` | parámetros de BM25 (por defecto `K1=1.2`, `B=0.75`; `B` entre 0 y 1) |
| `SCORE() [AS alias]` | agrega la relevancia como columna; sin alias se llama `score` |
| `ORDER BY alias DESC` | ya es el orden del índice, no agrega un `Sort` |
| `LIMIT k` | el índice calcula solo los k mejores si no hay otras condiciones ni otro orden |

- `MATCH` va solo en el `WHERE` de un `SELECT`, una vez por consulta, y se combina con otras condiciones únicamente con `AND`. Las demás condiciones se aplican como `Filter` sobre los resultados.
- No admite `JOIN` ni alias de tabla.
- En `EXPLAIN` aparece como `Text Index Scan` con los términos ya procesados y el ranking usado:

```
Limit  (cost=… rows=1 …)
  ->  Filter
        Filter: id > 1
        ->  Text Index Scan using idx_doc on documentos
              Match: contenido @@ 'vectorial'
              Terms: vectorial
              Ranking: BM25 (k1=1.5, b=0.5) top=all
```

## Preprocesamiento

Documentos y consultas pasan por los mismos pasos que en el laboratorio 9:

1. Minúsculas.
2. Tokens con la expresión `[a-záéíóúñü]+`. Los números y signos se descartan.
3. Se quitan las 608 stopwords de `backend/engine/fulltext/stoplist.txt`.
4. Stemming Snowball en español (`snowballstemmer`). Cada palabra se procesa una vez y su raíz queda en caché.

`"La INFLACIÓN y la inflación, en el Perú!"` → `inflacion inflacion peru`.

## SPIMI

```
documentos ──► diccionario en memoria  término → [(doc, tf), …]
                 │  se llena el bloque (200 postings)
                 ▼
               bloque .blk0, .blk1, …  (términos ordenados)
                 │  merge k-way con un heap, de 64 bloques a la vez
                 ▼
               .lex   término → (df, offset)
               .post  postings (doc, tf), 8 bytes cada uno
               .docs  doc → (RID, longitud, norma)
               .ftmeta N, longitud promedio, términos, bloques
```

- Cada documento recibe un número en orden de lectura. Como los bloques se escriben en ese orden, al unir las postings de un mismo término basta con concatenarlas y siguen ordenadas por documento.
- Si hay más de 64 bloques, el merge se hace por niveles para no abrir demasiados archivos a la vez.
- En la última pasada del merge se conoce el `df` final de cada término, así que ahí se calcula la norma TF-IDF de cada documento sin volver a leer nada.
- El léxico y la tabla de documentos se cargan en memoria al abrir el índice. Las postings se leen del disco por término, y sus páginas de 4096 bytes cuentan en `EXPLAIN ANALYZE`.

## Ranking

**TF-IDF + coseno**: peso `w = log10(1 + tf) · log10(N / df)` para documentos y consulta. El puntaje es el producto punto dividido entre las dos normas. Es la misma fórmula del laboratorio 9; con `news_es.csv` devuelve el mismo top-5.

**BM25**:

```
score(D, Q) = Σ  qtf · IDF(t) · tf · (k1 + 1) / (tf + k1 · (1 − b + b · |D| / avgdl))
             t∈Q
IDF(t) = ln((N − df + 0.5) / (df + 0.5) + 1)
```

- `k1` controla la **saturación**: después de unas cuantas apariciones, repetir el término casi no suma.
- `b` controla la **normalización por longitud**: con `b = 1` un documento largo se penaliza por completo y con `b = 0` no se penaliza.
- `|D|` es el número de términos del documento después del preprocesamiento y `avgdl` su promedio en la colección.

Los dos rankings recorren las postings término por término acumulando puntajes y se quedan con los k mejores usando un heap.

---

<div align="center">

[← Alcance y limitaciones](11-limitaciones.md) · [Inicio](../README.md)

</div>
