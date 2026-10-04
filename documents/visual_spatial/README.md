# Verificación visual del mapa

Capturas revisadas el 4 de octubre de 2026 con Chromium headless shell. Se usaron las respuestas reales del API, ejecutadas con tres tiendas de prueba en un backend temporal; las tablas del proyecto no se modificaron.

| Caso | Resultado comprobado | Captura |
|---|---|---|
| Radio de 5 km | IDs 1 y 2, marcadores naranjas y plan `RTREE-radius` | [Escritorio](radio_desktop.png) |
| k-NN, k = 2, `SELECT id` | IDs 1 y 2; las ubicaciones siguen resaltadas aunque no se proyectan | [Escritorio](knn_desktop.png) |
| Intersección con polígono | IDs 1 y 2, marcadores naranjas y plan `RTREE-polygon` | [Escritorio](polygon_desktop.png) |
| Pantalla estrecha | Mapa, tabla y plan legibles, sin recorte horizontal | [390 píxeles de ancho](knn_mobile.png) |

Los estados de resultados se capturaron en una vista temporal que monta los componentes reales con las respuestas del API y `React.StrictMode`. También se revisó el frontend completo con los puntos cargados. Las teselas OpenStreetMap cargaron correctamente.

Se corrigió la distribución a una columna para pantallas de hasta 800 píxeles: antes, la barra lateral de 250 píxeles y el plan de 320 píxeles recortaban el contenido. La leyenda ahora distingue el total de puntos del número de resultados resaltados.

Esta revisión comprueba el renderizado. No se automatizaron clics, arrastre ni zoom en estas capturas. La compilación de producción pasó después de las correcciones.
