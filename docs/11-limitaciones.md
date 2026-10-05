# ⚠️ Alcance y limitaciones

Lo que el sistema **no** hace, para no buscarlo:

## SQL

- Cada `ON` es **una sola igualdad** entre columnas. Las demás condiciones van en el `WHERE`.
- No hay `LEFT JOIN`, `RIGHT JOIN` ni `FULL JOIN`.
- No hay subconsultas, `DISTINCT`, `HAVING`, `OFFSET`, `UNION` ni alias de columnas.
- `GROUP BY` y `ORDER BY` aceptan una sola columna o expresión.
- No hay aritmética en las expresiones (`SET edad = edad + 1`).
- No hay `INSERT ... SELECT` ni `CREATE TABLE ... FROM FILE`: los CSV se importan desde la interfaz o la API.
- `DELETE` exige `WHERE`.

## Planificador

- Los `JOIN` se ejecutan en el orden escrito; no se busca el mejor orden.
- `OR`, `IN`, `LIKE` y la comparación entre columnas no usan índices.
- La selectividad usa mínimo, máximo y cantidad de valores distintos. No hay lista de valores más frecuentes (MCV) ni histogramas, así que una columna con valores muy desbalanceados se estima mal.

## Índices y almacenamiento

- Una tabla tiene un solo índice principal, fijado al crearla.
- `CREATE INDEX` no admite columnas `POINT`, que ya tienen su R-Tree, ni índices agrupados.
- Las tablas creadas antes del mapa de bits de `NULL` no admiten valores nulos hasta recrearlas.
- La columna del índice principal no admite `NULL`.

## Transacciones

- No hay `ROLLBACK`: una transacción no deshace lo que ya escribió.
- Los bloqueos son por tabla, no por fila.
- No hay detección de interbloqueos; los corta el tiempo de espera de 5 s.
- `BEGIN` y `END` tienen que enviarse en la misma petición a la API.

---

<div align="center">

[← Pruebas](10-pruebas.md) · [Inicio](../README.md)

</div>
