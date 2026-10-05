# Análisis relacional

**Almacenamiento.** Con 100,000 filas, cargar Heap tomó **5.915 s** y secuencial
**26.007 s**. La igualdad sin índice tomó **98.414 ms**
por consulta en Heap y **0.227 ms** en secuencial.
Los datos ocuparon **1.539 MiB** y **1.915 MiB**, respectivamente.
El secuencial reduce la búsqueda por clave manteniendo orden, pero ese orden tiene costo de mantenimiento.
Aunque Heap ya llena sus páginas, cada inserción revisa encabezados para buscar espacios
libres antes de añadir una fila. Al crecer el archivo, esa revisión aumenta el trabajo
por inserción; el costo proviene de la implementación actual, no de una obligación de
la organización Heap. Su igualdad sin índice, además, recorre todas las páginas.

**Corrección de la comparación antigua.** Para 1,000 filas, el Heap actual ocupa **20,480 bytes**.
La ejecución anterior reportaba aproximadamente **4,1 MB** porque creaba una página por registro.
Las afirmaciones anteriores de “204 veces menos espacio” y “22 veces más rápido” para secuencial
se retiran: mezclaban rendimiento con ese defecto ya corregido.

**Igualdad y construcción.** En 100,000 claves, la menor mediana al devolver filas completas fue
**Hash dinámico**, con **0.0360 ms/consulta**.
La menor mediana de construcción fue **Hash dinámico**, con
**9.924 s** sobre datos preexistentes.
Para agrupado, la carga física ordenada previa costó
**0.128 s** adicionales.

**Rangos y orden.** Para rangos que devuelven 1 % de las filas, la menor mediana fue
**B+ no agrupado**, con **11.543 ms/consulta**.
Para devolver todas las filas ordenadas, fue **Hash dinámico**, con
**1.243 s**.
Hash debe recorrer datos y, para ordenar, ejecutar mezcla externa; no ofrece navegación ordenada.
El costo de los B+ crece con las filas recuperadas, por eso se muestran tres selectividades.
Las bandas de ambos B+ se solapan para rango de 1 %, y las tres técnicas se solapan en
ordenamiento: las menores medianas observadas no establecen una ventaja concluyente en
esas comparaciones. El buen tiempo de Hash en orden proviene de su fallback de mezcla
externa con caché disponible, no de un índice hash ordenado.

**Modificaciones.** La menor mediana del tiempo acumulado de los tres ciclos completos fue
**Hash dinámico**, con **7.500 s** en la escala mayor.
Se suman los seis lotes de cada repetición antes de calcular esa mediana, incluyendo los
picos de reorganización. El lote de reinserción más lento del agrupado tomó
**20.044 s** frente a su mediana de
**4.450 s**. El agrupado realizó **9 reorganizaciones automáticas**
en toda la batería. Estas escrituras incluyen datos e índice en las tres técnicas, a diferencia
de la comparación anterior. Nueve lotes por técnica/tamaño dejan ver variación entre ciclos.
Hash tuvo borrados rápidos, pero el Heap subyacente revisa encabezados para localizar
espacios libres al reinsertar. En esta implementación, el costo de almacenamiento puede
dominar al del índice y cambia la recomendación que sugerían las pruebas de índice aislado.

**Algoritmos externos.** En 100,000 registros, ORDER BY, GROUP BY y JOIN externos tardaron
**0.425 s**,
**0.380 s** y
**2.136 s**.
Todos los resultados coinciden con la referencia, incluidos los **200,000 pares** del JOIN.
La referencia en memoria no impone el presupuesto de los algoritmos externos.

**Límites.** Son resultados de esta máquina, datos y caché disponible: tres repeticiones,
sin carga concurrente y con registros pequeños (`iii`). No establecen un ganador universal,
no representan E/S física ni miden consultas completas a través del API. Las bandas muestran
variación observada; diferencias pequeñas deben interpretarse con esa variación.
