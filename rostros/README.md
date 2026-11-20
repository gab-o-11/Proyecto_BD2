# Reconocimiento facial

App móvil que reconoce rostros en tiempo real usando el motor BD2 como base de datos
(Parte 5, opción D). Es una aplicación aparte: el servicio solo habla con el motor por `POST /api/query`.

```
iPhone (Expo Go) ─► servicio rostros (FastAPI, :8200) ─► motor BD2 (:8000)
                      │  YuNet (OpenCV) detecta y alinea
                      │  ArcFace (ONNX) da un vector de 512
                      └─► Redis (:6379): personas frecuentes
```

## Qué guarda el motor

| Tabla | Columnas | Índices |
|---|---|---|
| `personas` | id, nombre, origen (`lfw` o `propia`) | HASH por `id` |
| `rostros` | id, persona_id, archivo, emb `VECTOR(512)` | `HNSW` coseno sobre `emb`, HASH sobre `persona_id` |

Una fila de `rostros` por foto. `SIMILAR_TO` no admite `JOIN`, así que el nombre se busca con una
segunda consulta por `id`. Registrar o eliminar a una persona usa `BEGIN … END TRANSACTION`; como el
motor no tiene `ROLLBACK`, el servicio valida las fotos antes y, si una sentencia falla, borra lo insertado.

La base de rostros es [LFW](https://huggingface.co/datasets/bitmind/lfw): 13 233 fotos de 5 749 personas.
Las fotos propias se agregan desde la app o desde una carpeta.

## Reconocer un cuadro

1. YuNet detecta hasta 5 caras y sus 5 puntos (ojos, nariz y comisuras).
2. Cada cara se alinea a 112×112 y ArcFace (`w600k_r50`) calcula su vector normalizado. No se entrena nada.
3. Si la caché está activa, se compara contra las 20 personas más reconocidas; si la similitud supera
   `UMBRAL_CACHE` (0,44), responde la caché.
4. Si no, el motor busca las 5 caras más parecidas:
   `SELECT persona_id, archivo, SIMILARITY_SCORE() AS score FROM rostros WHERE SIMILAR_TO(VECTOR(…), k=5) USING HNSW WITH METRIC=cosine ORDER BY score DESC`.
   Si la mejor similitud no llega a `UMBRAL` (0,34), la cara es "desconocido".

## API del servicio

| Método y ruta | Uso |
|---|---|
| `GET /salud` | Estado del motor y de Redis |
| `POST /reconocer?cache=true\|false` | Campo `imagen` (JPEG). Devuelve caras, nombres, similitud, fuente y tiempos |
| `GET /personas` | Personas registradas desde la app o la carpeta |
| `POST /personas` | Campos `nombre` y 5 `fotos`, cada una con un solo rostro |
| `GET /personas/{id}` | Fotos de la persona |
| `POST /personas/{id}/fotos` | Agrega fotos |
| `DELETE /personas/{id}` | Elimina a la persona y sus fotos |
| `DELETE /rostros/{id}` | Borra una foto; si era la última, elimina a la persona |
| `GET /fotos/<ruta>` | Archivos de `data/rostros/fotos/` |

Solo se pueden modificar las personas con origen `propia`; LFW queda intacto.

## La app

- **Reconocer:** la cámara envía un cuadro de 640 px cada vez que llega la respuesta anterior (como mínimo
  cada 0,5 s). Muestra un recuadro animado sobre cada cara con el nombre y la similitud, la foto guardada
  con la que coincidió, los tiempos de cada etapa, si respondió el motor o la caché y un interruptor para
  apagar la caché.
- **Mis rostros:** lista de las personas propias. Se registra a alguien con 5 fotos guiadas (de frente, a
  la izquierda, a la derecha, arriba y abajo) y se pueden agregar o borrar fotos y eliminar personas.

## Cómo levantarlo

1. `pnpm setup:rostros`
2. `cd rostros && .venv/bin/python descargas.py` (descarga LFW, 188 MB, y los modelos, unos 290 MB comprimidos; quedan en `data/rostros/`).
3. `pnpm dev:backend`
4. `cd rostros && .venv/bin/python ingesta.py` (unos 17 min en CPU la primera vez; carga 5 749 personas y
   13 233 rostros). Para incluir fotos propias desde el inicio, ponerlas en `data/rostros/carpeta/<Nombre>/`
   antes de cargar. `--reiniciar` recrea las tablas y borra también las personas registradas desde la app.
5. `pnpm dev:redis` (Docker) y `pnpm dev:rostros`.
6. `pnpm --dir rostros/app install` y `pnpm dev:rostros-app`.
7. En el iPhone: instalar Expo Go, iniciar sesión con la misma cuenta que `npx expo login` en la laptop
   y escanear el QR. Laptop e iPhone tienen que estar en la misma red.

`pnpm dev` levanta todo junto con `mprocs`.

### Si la app no se conecta

- La app arma la URL del servicio con la IP de la laptop que Expo Go ya conoce (`http://<ip>:8200`).
- Con `ufw` activo hay que abrir los puertos: `sudo ufw allow 8200/tcp && sudo ufw allow 8081/tcp`.
- Muchas redes universitarias aíslan a los dispositivos: conectar la laptop al hotspot del iPhone.
- Para otra URL: `EXPO_PUBLIC_ROSTROS_URL=http://<ip>:8200 pnpm dev:rostros-app`.
- En el iPhone, el interruptor de silencio apaga el sonido de la cámara en el modo continuo.

## Pruebas

```
cd rostros
.venv/bin/python test_ingesta.py
.venv/bin/python test_cache.py
.venv/bin/python test_reconocedor.py
.venv/bin/python test_modelos.py
.venv/bin/python test_punta_a_punta.py
```

`test_punta_a_punta.py` necesita el motor levantado; usa las tablas `prueba_personas` y `prueba_rostros` y las borra al terminar.

## Evaluación

Con el motor y Redis levantados y el servicio detenido:

```
cd rostros
.venv/bin/python evaluacion/acierto.py
.venv/bin/python evaluacion/latencia.py
.venv/bin/python evaluacion/medir_cache.py
```

Los resultados quedan en `benchmarks/rostros_results/`. Las cifras de abajo son de un i7-12700H sin GPU.

### Acierto según la cantidad de fotos (umbral 0,34)

Se registra a cada persona de LFW con 1, 3 o 5 de sus fotos y se la reconoce con otras fotos suyas que
no se usaron para registrar. Los desconocidos son 1000 personas de LFW con una sola foto, que no están registradas.

| Fotos por persona | Personas | Registradas reconocidas | Desconocidos rechazados |
|---|---|---|---|
| 1 | 1680 | 99,4 % | 99,6 % |
| 3 | 610 | 99,8 % | 99,7 % |
| 5 | 311 | 99,7 % | 100 % |

El umbral 0,34 maximiza la suma de ambos porcentajes con 5 fotos. El de la caché lleva un margen de +0,10
(0,44) porque solo compara contra 20 personas; con él, el acierto con 5 fotos sigue en 99,6 %.
Fuente: `umbrales.json` y `acierto.png`.

### Latencia (500 fotos de LFW, ms)

| Etapa | Mediana | p95 |
|---|---|---|
| Detección | 1,7 | 3,0 |
| Embedding | 82,7 | 149,6 |
| Búsqueda en el motor (interna) | 5,2 | 18,8 |
| Búsqueda en el motor (HTTP) | 9,0 | 24,7 |
| Total | 94,2 | 176,3 |

La búsqueda en el motor queda muy por debajo de los 100 ms que pide el enunciado; el costo está en el embedding.

| Método | Motor, mediana | Motor, p95 | Top-1 igual a SEQ |
|---|---|---|---|
| HNSW | 3,4 | 5,8 | 100 % |
| SEQ | 24,3 | 45,5 | — |

Fuente: `latencia.csv`, `hnsw_vs_seq.csv` y `latencia.png`. Las fotos de LFW miden 250×250; en el
iPhone el cuadro mide unos 480×640 y la detección tarda algo más.

### Caché Redis (1000 búsquedas, 80 % de 10 personas frecuentes)

| Caché | Respondidas por la caché | Errores de la caché | Exactitud | Mediana (ms) | p95 (ms) |
|---|---|---|---|---|---|
| Sin | 0 % | 0 | 99,9 % | 5,6 | 6,8 |
| Con | 76,9 % | 0 | 99,9 % | 0,5 | 6,6 |

Fuente: `cache.csv` y `cache.png`.

## Decisiones

- El embedding se calcula en el servicio de la app y no en el teléfono: hacerlo en el iPhone exige un
  development build y la cuenta paga de Apple. El servicio es parte de la app, no del motor.
- Expo Go no da acceso a los cuadros del video, así que "tiempo real" es la vista en vivo de la cámara más
  un reconocimiento que se actualiza varias veces por segundo con fotos de baja resolución.
- La app muestra la similitud coseno real; con ArcFace una coincidencia correcta suele quedar entre 50 % y 80 %.
- Los modelos preentrenados de InsightFace son de uso no comercial; aquí se usan con fines académicos.
