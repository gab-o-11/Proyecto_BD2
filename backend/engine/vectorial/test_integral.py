import os
import tempfile

import cv2
import numpy as np

from .kmeans import kmeans
from ..multimedia.extract_features import ColeccionesMultimedia
from ..multimedia.local_features import DescriptorBatch, LocalFeatureExtractor
from ..parser.executor import Executor
from ..parser.scanner import Scanner
from ..parser.sql_parser import Parser

PALABRAS = 48
CLASES = ("tablero", "circulos", "lineas")
IMAGENES_POR_CLASE = 8


class ExtractorSift(LocalFeatureExtractor):
    @property
    def descriptor_id(self):
        return "sift-prueba"

    @property
    def dimension(self):
        return 128

    def extract(self, path):
        imagen = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if imagen is None:
            raise ValueError(f"no se pudo leer la imagen '{path}'")
        _, descriptores = cv2.SIFT_create(nfeatures=200).detectAndCompute(imagen, None)
        if descriptores is None:
            descriptores = np.empty((0, 128), dtype=np.float32)
        return DescriptorBatch(self.descriptor_id, 128, descriptores, source=str(path))


class ExtractorAudio(LocalFeatureExtractor):
    @property
    def descriptor_id(self):
        return "audio-prueba"

    @property
    def dimension(self):
        return 13

    def extract(self, path):
        return DescriptorBatch(self.descriptor_id, 13, np.load(path), source=str(path))


def _dibujar(clase, azar):
    imagen = np.full((192, 192), 255, dtype=np.uint8)
    if clase == "tablero":
        lado = int(azar.integers(14, 20))
        alto = int(azar.integers(0, lado))
        ancho = int(azar.integers(0, lado))
        for fila in range(-alto, 192, lado):
            for columna in range(-ancho, 192, lado):
                if ((fila + alto) // lado + (columna + ancho) // lado) % 2 == 0:
                    imagen[max(fila, 0):fila + lado, max(columna, 0):columna + lado] = 0
    elif clase == "circulos":
        for _ in range(14):
            centro = (int(azar.integers(15, 177)), int(azar.integers(15, 177)))
            cv2.circle(imagen, centro, int(azar.integers(6, 18)), 0, -1)
    else:
        for _ in range(22):
            inicio = (int(azar.integers(0, 192)), int(azar.integers(0, 192)))
            fin = (int(azar.integers(0, 192)), int(azar.integers(0, 192)))
            cv2.line(imagen, inicio, fin, 0, 2)
    return imagen


def _imagenes(carpeta):
    azar = np.random.default_rng(7)
    nombres = []
    for clase in CLASES:
        for numero in range(IMAGENES_POR_CLASE):
            nombre = f"{clase}_{numero}.png"
            cv2.imwrite(os.path.join(carpeta, nombre), _dibujar(clase, azar))
            nombres.append(nombre)
        cv2.imwrite(os.path.join(carpeta, f"consulta_{clase}.png"), _dibujar(clase, azar))
    return nombres


def _vocabulario(extractor, carpeta, nombres, palabras):
    lotes = []
    for nombre in nombres:
        lotes.append(extractor.extract(os.path.join(carpeta, nombre)).values)
    return kmeans(np.vstack(lotes), palabras, semilla=0)[0]


def _ejecutar(executor, sql):
    resultado = executor.run(Parser(Scanner(sql)).parse_program())[-1]
    assert "error" not in resultado, (sql, resultado)
    return resultado


def _insertar(executor, tabla, nombres):
    valores = []
    for posicion, nombre in enumerate(nombres):
        valores.append(f"({posicion + 1}, '{nombre}')")
    _ejecutar(executor, f"INSERT INTO {tabla} (id, ruta) VALUES " + ", ".join(valores) + ";")


def _rutas(resultado):
    rutas = []
    for fila in resultado["rows"]:
        rutas.append(fila["ruta"])
    return rutas


def _plan(executor, sql):
    return "\n".join(_ejecutar(executor, "EXPLAIN " + sql)["explain"]["text"])


def _imagen_completa(media, datos):
    nombres = _imagenes(media)
    extractor = ExtractorSift()
    centroides = _vocabulario(extractor, media, nombres, PALABRAS)
    colecciones = ColeccionesMultimedia(media)
    colecciones.registrar(extractor, centroides)
    catalogo = {}
    executor = Executor(catalogo, data_dir=datos, vectorizador=colecciones.vectorizar)
    _ejecutar(executor, f"CREATE TABLE imagenes (id INT PRIMARY KEY, ruta VARCHAR(40), embedding VECTOR({PALABRAS}));")
    _insertar(executor, "imagenes", nombres)
    assert colecciones.cargar(catalogo["imagenes"], "ruta", "sift-prueba") == len(nombres)
    _ejecutar(executor, "CREATE INDEX idx_ivf ON imagenes (embedding) USING IVF WITH (METRIC=cosine, LISTS=4);")
    _ejecutar(executor, "CREATE INDEX idx_hnsw ON imagenes (embedding) USING HNSW WITH (METRIC=cosine, M=8);")

    misma = _ejecutar(executor, "SELECT ruta, SIMILARITY_SCORE() AS score FROM imagenes WHERE SIMILAR_TO('tablero_3.png', k=1) USING SEQ WITH METRIC=cosine;")
    assert misma["rows"][0]["ruta"] == "tablero_3.png"
    assert abs(misma["rows"][0]["score"] - 1.0) < 1e-5

    k = IMAGENES_POR_CLASE // 2
    for clase in CLASES:
        base = f"FROM imagenes WHERE SIMILAR_TO('consulta_{clase}.png', k={k})"
        exacta = _rutas(_ejecutar(executor, f"SELECT ruta {base} USING SEQ WITH METRIC=cosine;"))
        assert len(exacta) == k
        for ruta in exacta:
            assert ruta.startswith(clase), (clase, exacta)
        ivf = _rutas(_ejecutar(executor, f"SELECT ruta {base} USING IVF WITH METRIC=cosine, PROBES=4;"))
        assert sorted(ivf) == sorted(exacta), (ivf, exacta)
        hnsw = _rutas(_ejecutar(executor, f"SELECT ruta {base} USING HNSW WITH METRIC=cosine, EF_SEARCH=24;"))
        assert sorted(hnsw) == sorted(exacta), (hnsw, exacta)

    consulta = "SELECT ruta FROM imagenes WHERE SIMILAR_TO('consulta_lineas.png', k=3)"
    assert "Vector Index Scan" in _plan(executor, consulta + " USING HNSW WITH METRIC=cosine;")
    assert "Vector Index Scan" in _plan(executor, consulta + " USING IVF WITH METRIC=cosine;")
    assert "Seq Scan on imagenes" in _plan(executor, consulta + " USING SEQ;")
    assert "no existe un índice HNSW con métrica euclidean" in _plan(executor, consulta + " USING HNSW WITH METRIC=euclidean;")

    filtradas = _ejecutar(executor, "SELECT ruta FROM imagenes WHERE ruta LIKE 'lineas%' AND SIMILAR_TO('consulta_lineas.png', k=3) USING SEQ WITH METRIC=cosine;")
    for ruta in _rutas(filtradas):
        assert ruta.startswith("lineas")

    resultado = executor.run(Parser(Scanner("SELECT ruta FROM imagenes WHERE SIMILAR_TO('../fuera.png', k=1);")).parse_program())[-1]
    assert "fuera de la carpeta" in resultado["error"]
    for nombre in catalogo:
        catalogo[nombre].cerrar()


def _audio_completo(media, datos):
    azar = np.random.default_rng(11)
    centros = azar.normal(0, 8, (2, 13))
    nombres = []
    for grupo in range(2):
        for numero in range(6):
            nombre = f"pista_{grupo}_{numero}.npy"
            np.save(os.path.join(media, nombre), centros[grupo] + azar.normal(0, 1, (60, 13)))
            nombres.append(nombre)
    np.save(os.path.join(media, "consulta_1.npy"), centros[1] + azar.normal(0, 1, (60, 13)))
    extractor = ExtractorAudio()
    colecciones = ColeccionesMultimedia(media)
    colecciones.registrar(extractor, _vocabulario(extractor, media, nombres, 8))
    catalogo = {}
    executor = Executor(catalogo, data_dir=datos, vectorizador=colecciones.vectorizar)
    _ejecutar(executor, "CREATE TABLE audios (id INT PRIMARY KEY, ruta VARCHAR(40), embedding VECTOR(8));")
    _insertar(executor, "audios", nombres)
    assert colecciones.cargar(catalogo["audios"], "ruta", "audio-prueba") == len(nombres)
    _ejecutar(executor, "CREATE INDEX idx_audio ON audios (embedding) USING HNSW WITH (METRIC=cosine, M=4);")
    rutas = _rutas(_ejecutar(executor, "SELECT ruta FROM audios WHERE SIMILAR_TO('consulta_1.npy', k=3) USING HNSW WITH METRIC=cosine, EF_SEARCH=12;"))
    assert len(rutas) == 3
    for ruta in rutas:
        assert ruta.startswith("pista_1_"), rutas
    for nombre in catalogo:
        catalogo[nombre].cerrar()


def main():
    with tempfile.TemporaryDirectory(prefix="test_integral_") as raiz:
        for nombre, prueba in (("imagen", _imagen_completa), ("audio", _audio_completo)):
            media = os.path.join(raiz, nombre, "media")
            datos = os.path.join(raiz, nombre, "datos")
            os.makedirs(media)
            os.makedirs(datos)
            prueba(media, datos)
    print("OK: búsqueda por similitud completa con imagen y audio")


if __name__ == "__main__":
    main()
