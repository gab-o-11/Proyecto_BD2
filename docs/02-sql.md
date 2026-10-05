# 📝 SQL

Varias sentencias se separan con `;`. Los comentarios de una línea empiezan con `--`. Las palabras reservadas no distinguen mayúsculas.

## Tablas

```sql
CREATE TABLE clientes (
  id INT PRIMARY KEY,
  nombre VARCHAR(20) NOT NULL,
  edad INT,
  promedio FLOAT,
  registro DATE,
  ubicacion POINT
) USING BPLUS;

DROP TABLE [IF EXISTS] clientes;
```

| Tipo | Ocupa | Notas |
|---|---|---|
| `INT` | 4 B | entero de 32 bits |
| `FLOAT` | 4 B | |
| `VARCHAR(n)` | 4·n B | 32 B si no se indica `n` |
| `DATE` | como texto | formato `YYYY-MM-DD`, validado |
| `POINT` | 16 B | `POINT(latitud, longitud)`; recibe un R-Tree automático |

- `USING` elige el **índice principal**: `HASH` (por defecto), `BPLUS` o `BPLUS_CLUSTERED`.
- El índice principal va sobre la columna `PRIMARY KEY` o, si no hay, sobre la primera columna que no sea `POINT`.
- `PRIMARY KEY` exige valores únicos y no nulos. `NOT NULL` impide valores nulos.

## Índices secundarios

```sql
CREATE INDEX idx_clientes_nombre ON clientes (nombre) USING BPLUS;
CREATE INDEX idx_clientes_edad ON clientes (edad) USING HASH;
DROP INDEX [IF EXISTS] idx_clientes_nombre;
```

`BPLUS` (B+ no agrupado) es el valor por defecto. Detalles en [Índices](05-indices.md#índices-secundarios).

## Insertar, actualizar y borrar

```sql
INSERT INTO clientes VALUES (1, 'Ana', 25, 17.5, '2026-10-04', POINT(-12.0464, -77.0428));
INSERT INTO clientes (id, nombre) VALUES (2, 'Luis'), (3, 'Mia');

UPDATE clientes SET edad = 30, promedio = NULL WHERE nombre = 'Ana';
DELETE FROM clientes WHERE id IN (2, 3);
```

- Las columnas que no aparecen en la lista quedan en `NULL`.
- Un `INSERT` con varias filas se valida completo antes de escribir: si una fila falla, no se inserta ninguna.
- `DELETE` exige `WHERE`.
- Los literales se convierten al tipo de la columna: `id = '1'` se evalúa como `id = 1`.

## Consultar

```sql
SELECT * FROM clientes WHERE id = 1;
SELECT nombre, edad FROM clientes WHERE edad >= 18 ORDER BY edad DESC LIMIT 10;
SELECT distrito, COUNT(*), AVG(edad), MIN(edad), MAX(edad), SUM(edad) FROM clientes GROUP BY distrito;
SELECT COUNT(*) FROM clientes;
```

### Condiciones del WHERE

| Forma | Ejemplo |
|---|---|
| Comparación con un literal | `edad >= 18`, `nombre != 'Ana'`, `id <> 3` |
| Comparación entre columnas | `c.distrito = t.distrito`, `precio > costo` |
| Rango | `edad BETWEEN 20 AND 30`, `nombre NOT BETWEEN 'A' AND 'C'` |
| Lista | `id IN (1, 2, 3)`, `estado NOT IN ('cancelado')` |
| Patrón | `nombre LIKE 'L%'`, `nombre NOT LIKE '_i%'` (`%` = cualquier texto, `_` = un carácter) |
| Nulos | `edad IS NULL`, `edad IS NOT NULL` |
| Combinación | `NOT (a = 1 OR b = 2) AND c > 3` |

La precedencia es `NOT`, luego `AND`, luego `OR`. Con paréntesis se cambia.

> [!NOTE]
> Una comparación con `NULL` nunca es verdadera, como en SQL estándar. `edad = NULL` da un error que sugiere `IS NULL`.

### JOIN

```sql
SELECT c.nombre, p.total, t.nombre
FROM clientes c
JOIN pedidos p ON c.id = p.cliente_id
INNER JOIN tiendas AS t ON p.tienda_id = t.id
WHERE p.estado = 'entregado' AND c.distrito = t.distrito;
```

- Se pueden encadenar todos los `JOIN` que se quieran.
- Cada `ON` es **una igualdad** entre una columna de la tabla nueva y una de las anteriores.
- Si un nombre de columna existe en varias tablas, hay que calificarlo (`c.id`).
- Las columnas del resultado se llaman `alias.columna`.

### NULL en los resultados

| Operación | Comportamiento |
|---|---|
| `COUNT(*)` | cuenta todas las filas |
| `COUNT(col)`, `SUM`, `AVG`, `MIN`, `MAX` | ignoran los `NULL` |
| `ORDER BY col` | `NULL` al final (al inicio con `DESC`) |
| `GROUP BY col` | los `NULL` forman un grupo |
| `JOIN` | una clave `NULL` no se empareja |

## Consultas espaciales

```sql
SELECT * FROM tiendas WHERE distancia(ubicacion, POINT(-12.0464, -77.0428)) < 5000;
SELECT * FROM tiendas ORDER BY distancia(ubicacion, mi_ubicacion) LIMIT 10;
SELECT * FROM tiendas WHERE distancia(ubicacion, POINT(0, 0), 'euclidean') < 0.5;
SELECT id FROM tiendas WHERE intersecta(ubicacion,
  POLYGON(POINT(-12.1, -77.1), POINT(-12, -77.1), POINT(-12, -77), POINT(-12.1, -77)));
```

`mi_ubicacion` es un parámetro que envía la interfaz (el punto elegido en el mapa). Detalles en [Consultas espaciales](08-espacial.md).

## Planes y estadísticas

```sql
EXPLAIN SELECT ...;
EXPLAIN ANALYZE SELECT ...;
EXPLAIN ANALYZE UPDATE ...;
ANALYZE clientes;
```

- `EXPLAIN` acepta `SELECT`, `INSERT`, `UPDATE` y `DELETE`.
- `EXPLAIN ANALYZE` **ejecuta** la sentencia: un `EXPLAIN ANALYZE DELETE` borra filas.

Detalles en [Planificador y EXPLAIN](06-planificador.md).

## Transacciones

```sql
BEGIN TRANSACTION;
UPDATE cuentas SET saldo = 50 WHERE id = 1;
UPDATE cuentas SET saldo = 150 WHERE id = 2;
END TRANSACTION;
```

`BEGIN` y `END` tienen que enviarse en la misma petición. Detalles en [Transacciones](07-transacciones.md).

---

<div align="center">

[← Instalación](01-instalacion.md) · [Inicio](../README.md) · [Arquitectura →](03-arquitectura.md)

</div>
