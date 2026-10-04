# Comparación espacial de la parte 2

`spatial.py` compara búsqueda secuencial, el `engine.rtree.RTree` del proyecto y PostgreSQL GiST. Las gráficas y los CSV están en [spatial_results](spatial_results/).

[Resultados medidos y conclusiones](RESULTADOS_ESPACIALES.md).

```sh
rtk proxy /home/snah/micromamba/envs/bd2/bin/python -B benchmarks/spatial.py
```

Requiere PostgreSQL con `cube`, `earthdistance` y `pg_buffercache`, y Python con `psycopg2` y `matplotlib`. El programa crea y elimina un clúster PostgreSQL privado en `/tmp`, con socket Unix privado y TCP deshabilitado; no se conecta a servidores existentes. Para una comprobación breve:

```sh
rtk proxy /home/snah/micromamba/envs/bd2/bin/python -B benchmarks/spatial.py --sizes 1000 --queries 2 --output /tmp/bd2-spatial-smoke
```

## Diseño de la medición

- 1 000, 10 000 y 100 000 puntos uniformes en un área de aproximadamente 110 × 109 km alrededor de Lima; los centros de consulta están en el interior. Semilla fija `20261004`; los tamaños menores son prefijos del mismo dataset.
- 100 centros por variante: radio inclusivo de 1, 5 y 10 km; k-NN con k = 10, 50 y 100. Se usa Haversine, en metros, con una esfera de radio 6 371 000 m.
- El barrido usa la misma función `engine.spatial.distance` que el R-Tree, y `heapq.nsmallest` para k-NN. El índice propio usa la implementación actual de páginas en disco, con capacidad de 16 entradas por nodo y carga masiva STR (`bulk_load`).
- GiST indexa `earthdistance` sobre `cube`; se redefine `earth()` antes de cargar datos para usar el mismo radio terrestre. Las búsquedas por radio usan envolvente `earth_box` y filtro exacto `earth_distance`. k-NN usa distancia euclidiana de la cuerda 3D, cuyo orden es monótono con la distancia de gran círculo. [Documentación de earthdistance](https://www.postgresql.org/docs/current/earthdistance.html), [documentación de cube y k-NN GiST](https://www.postgresql.org/docs/current/cube.html).
- Cada consulta verifica todos sus IDs: igualdad de conjuntos en radio e igualdad de la secuencia en k-NN. La verificación queda fuera del tiempo medido. `planes.json` registra un EXPLAIN ANALYZE por variante y verifica que se use `puntos_gist`.
- El P95 usa rango más cercano: posición `ceil(0.95 × n)` en los tiempos ordenados.
- Hay una consulta de calentamiento por técnica y variante. Se rota el orden de las técnicas entre consultas. PostgreSQL tiene 64 MiB de shared buffers; se desactiva el barrido secuencial para medir explícitamente GiST, y el paralelismo de consulta.
- El tiempo incluye producir y devolver los IDs. PostgreSQL incluye planificación, ejecución y viaje por socket local; Python se ejecuta dentro del proceso. La comparación mide estas implementaciones y no aísla el costo algorítmico ni compara el parser/API completos. Se utiliza caché caliente, no lectura de disco en frío.

## Construcción y espacio

La construcción del R-Tree mide `bulk_load`: prepara las entradas, las ordena mediante STR y escribe páginas y metadatos. GiST mide únicamente `CREATE INDEX`, sobre coordenadas 3D previamente materializadas; su carga/conversión se registra por separado en `carga_pg_ms`. El barrido no construye índice. No se mide aquí la inserción incremental ni el mantenimiento ante actualizaciones.

La RAM del dataset Python se calcula como tamaño profundo de los objetos retenidos. **No se mide la RAM total ni el pico de construcción del R-Tree**: `indice_ram_bytes=0` es un marcador del runner y no significa que el índice no use memoria. Los nodos se leen desde páginas; el sistema operativo también puede mantenerlos en caché. GiST informa sus páginas residentes en shared buffers mediante `pg_buffercache`; esta medición no incluye toda la memoria del servidor ni buffers temporales de construcción. Por tanto, no es una comparación exacta del consumo total de los motores. [Documentación de pg_buffercache](https://www.postgresql.org/docs/current/pgbuffercache.html).

En la corrida final adjunta, la caché GiST se mide al final de cada tamaño, **en la misma ejecución que las 100 consultas por variante**. `huella_replica.csv` y `huella_entorno.json` conservan la medición separada anterior como evidencia histórica; no alimentan las cifras finales.

El espacio GiST y de su tabla son archivos reales medidos con `pg_relation_size`. El R-Tree actual mide la suma de sus archivos `.nodes` y `.meta` con `bytes_en_disco()`; el índice puede cerrarse y reabrirse con la misma ruta. La integración SQL usa un directorio temporal y reconstruye sus índices derivados al reiniciar: persistencia del archivo y ciclo de vida de la tabla son aspectos diferentes. `entrada_csv_bytes` describe el tamaño serializado de la entrada reproducible; no representa almacenamiento heap del motor ni se suma al índice. La RAM y el disco tampoco son intercambiables.

## Archivos

| Archivo | Contenido |
|---|---|
| `consultas.csv` | Promedio, percentil 95, cantidad media de resultados y comprobación de igualdad |
| `muestras.csv` | Tiempo y centro de cada consulta individual |
| `construccion.csv` | Construcción, RAM del dataset Python, caché GiST, disco y carga PostgreSQL; RAM R-Tree sin medir |
| `entorno.json` | Versiones, plataforma, semilla, configuración y métrica |
| `planes.json` | Planes PostgreSQL con tiempo y buffers |
| `consultas.png` | Comparación de radio y k-NN en los tres tamaños |
| `construccion_espacio.png` | Construcción y tamaño de los índices |

## Cuándo usar cada técnica

| Técnica | Uso adecuado | Costo o límite |
|---|---|---|
| Secuencial | Consultas ocasionales, datos pequeños, filtros muy poco selectivos o geometrías sin índice | Evalúa todos los puntos en cada búsqueda; no paga construcción |
| R-Tree propio | Búsquedas espaciales repetidas dentro del motor del proyecto, con filtro que reduce candidatos | Carga STR y páginas en disco; radio grande devuelve muchos candidatos; la integración SQL reconstruye índices al reiniciar |
| PostgreSQL GiST | Aplicaciones con almacenamiento persistente y muchas consultas espaciales concurrentes | Construcción y archivo de índice, servicio PostgreSQL y costo de comunicación |

Los resultados corresponden a esta distribución y carga. No permiten generalizar a puntos muy agrupados, índices en frío, otros equipos, latencias de red o concurrencia. La tabla de usos combina los costos medidos con estas propiedades de cada implementación; no afirma un umbral universal de tamaño.

## Pruebas y evidencia visual

Además de verificar los IDs del benchmark, los módulos `engine.test_rtree` y `engine.parser.test_spatial_sql` comprueban inserción, split, borrado, radio, k-NN, polígonos, poda, mantenimiento SQL y recarga de tablas. Una comprobación adicional de 1 000 puntos confirmó carga STR, cierre/reapertura del archivo, radio/k-NN y modificaciones persistentes.

Las [capturas del mapa y sus planes SQL](../documents/visual_spatial/README.md) muestran radio, k-NN y polígonos. Son evidencia funcional; sus tiempos de interfaz no se usan en las gráficas del benchmark.

```sh
cd backend
rtk proxy /home/snah/micromamba/envs/bd2/bin/python -B -m engine.test_rtree
rtk proxy /home/snah/micromamba/envs/bd2/bin/python -B -m engine.parser.test_spatial_sql
```
