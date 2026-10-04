# Resultados de la comparación espacial

Corrida final iniciada el **2026-10-04T11:20:57-0500**: **1 800 consultas distintas, cada una ejecutada con las tres técnicas**. Se verificaron 5 400 ejecuciones, 54 resúmenes y 18 planes GiST. Todos los IDs coinciden; también el orden de los vecinos. Son 100 consultas por combinación de tamaño y parámetro. [Metodología y reproducción](README_espacial.md).

## Consultas con 100 000 puntos

Tiempo promedio en milisegundos; menor es mejor.

| Consulta | Secuencial | R-Tree | PostgreSQL GiST |
|---|---:|---:|---:|
| Radio 1 km | 536.091 | 0.633 | 0.803 |
| Radio 5 km | 514.473 | 6.546 | 3.536 |
| Radio 10 km | 545.037 | 26.607 | 11.276 |
| k-NN, k=10 | 549.195 | 2.235 | 0.652 |
| k-NN, k=50 | 523.677 | 3.263 | 0.734 |
| k-NN, k=100 | 522.520 | 4.189 | 0.829 |

El R-Tree reduce el tiempo del barrido entre **20.5× y 847.0×** en estas variantes de 100 000 puntos. Los tiempos incluyen producir y devolver IDs; GiST incluye el viaje por socket local. Estas cifras corresponden a esta carga y equipo, no aíslan el costo algorítmico.

![Consultas en todos los tamaños](spatial_results/consultas.png)

## Construcción y tamaño del índice

| Puntos | Construcción R-Tree (s) | Construcción GiST (s) | RAM R-Tree (MiB) | Caché GiST (MiB) | Disco GiST (MiB) |
|---:|---:|---:|---:|---:|---:|
| 1 000 | 0.095 | 0.012 | 0.248 | 0.078 | 0.078 |
| 10 000 | 1.168 | 0.205 | 2.532 | 0.734 | 0.734 |
| 100 000 | 14.281 | 1.727 | 25.378 | 7.789 | 7.789 |

El barrido no construye índice. El R-Tree mide inserciones; GiST mide CREATE INDEX sobre coordenadas ya materializadas, con carga/conversión registrada por separado en el CSV. El índice R-Tree es volátil y ocupa cero bytes de disco.

**RAM y caché son medidas distintas**: objetos Python retenidos frente a páginas GiST residentes en shared buffers; no incluyen toda la memoria de cada motor. La caché GiST de esta corrida final se midió **después de las 100 consultas por variante y los EXPLAIN de cada tamaño**, dentro de la misma ejecución. La réplica anterior permanece como evidencia histórica en `huella_replica.csv` y `huella_entorno.json`; no se usa en las cifras finales.

![Construcción, RAM y disco](spatial_results/construccion_espacio.png)

## Evidencia y límites

- [Resultados completos y percentil 95](spatial_results/consultas.csv), [muestras individuales](spatial_results/muestras.csv), [construcción/espacio](spatial_results/construccion.csv). El P95 usa rango más cercano: posición `ceil(0.95 × n)` en los tiempos ordenados.
- [Entorno y versiones](spatial_results/entorno.json), [planes EXPLAIN ANALYZE](spatial_results/planes.json). Todos los planes medidos usan `puntos_gist`.
- Índices calientes, puntos uniformes y consultas sin concurrencia. La comparación de §2.2.4 usa radios en km y k-NN, con la misma métrica esférica en las tres técnicas. No se midieron polígonos ni Euclidiana.
- Se comparan algoritmos espaciales con devolución de IDs, no el tiempo del parser/API ni todo el ejecutor SQL. No se fijan umbrales de aprobación de latencia, porque el enunciado no define presupuestos.
- [Cuándo usar cada técnica](README_espacial.md#cuándo-usar-cada-técnica). Estos resultados no establecen un umbral universal de tamaño.
