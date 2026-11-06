"""Pruebas del registro de MFCC en FeaturePipeline.

Se corren desde la carpeta backend:
    .venv/Scripts/python -m engine.multimedia.test_pipeline_mfcc
"""
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from engine.multimedia.audio_features import MfccExtractor
from engine.multimedia.pipeline import FeaturePipeline
from engine.multimedia.quantization import Vocabulary, save_vocabulary
from engine.parser.executor import Executor
from engine.parser.scanner import Scanner
from engine.parser.sql_parser import Parser

SR = 22050
TONOS = {1: 220, 2: 440, 3: 880, 4: 1500}   # una "canción" por tono


def tono(frecuencia, segundos=3.0, volumen=0.4):
    t = np.arange(int(segundos * SR)) / SR
    senal = np.sin(2 * np.pi * frecuencia * t) + 0.5 * np.sin(2 * np.pi * 2.7 * frecuencia * t)
    return (volumen * senal).astype(np.float32)


def ejecutar(executor, sql):
    resultado = executor.run(Parser(Scanner(sql)).parse_program())[-1]
    assert "error" not in resultado, (sql, resultado)
    return resultado


def test_sin_vocabulario_mfcc():
    # Sin data/modelos/audio_mfcc, la API arranca igual: solo se omite esa modalidad
    with tempfile.TemporaryDirectory() as raiz:
        pipeline = FeaturePipeline(raiz, raiz)
        assert pipeline.modelos() == []


def test_mfcc_registrado():
    extractor = MfccExtractor(max_seconds=30)
    with tempfile.TemporaryDirectory() as raiz:
        raiz = Path(raiz)
        media, modelos, datos = raiz / "media", raiz / "modelos", raiz / "datos"
        for carpeta in (media, modelos / "audio_mfcc", datos):
            carpeta.mkdir(parents=True)

        # Las canciones de la colección, en MP3 si se puede escribir y si no en WAV
        extension = "mp3" if "MP3" in sf.available_formats() else "wav"
        for i, frecuencia in TONOS.items():
            sf.write(media / f"cancion_{i}.{extension}", tono(frecuencia), SR)

        # Vocabulario de prueba: una palabra por canción (el promedio de sus MFCC).
        # Es como un K-means ya resuelto; el real lo entrena entrenar_Kmeans.py.
        centroides = tuple(
            tuple(float(x) for x in extractor.extract(media / f"cancion_{i}.{extension}").values.mean(axis=0))
            for i in TONOS
        )
        save_vocabulary(Vocabulary(extractor.descriptor_id, extractor.dimension, centroides),
                        modelos / "audio_mfcc" / "vocabulary.json")

        # 1. Al arrancar, el pipeline registra audio_mfcc con el descriptor_id correcto
        pipeline = FeaturePipeline(media, modelos)
        modelo = {m["name"]: m for m in pipeline.modelos()}["audio_mfcc"]
        assert modelo["descriptor_id"] == "mfcc:sr22050:n13:fft2048:hop512:sinc0:dur30"
        assert modelo["dimension"] == len(TONOS) and modelo["descriptor_dimension"] == 12

        # 2. Cargar la tabla con MFCC y consultar con un audio NUEVO
        catalogo = {}
        executor = Executor(catalogo, data_dir=str(datos), vectorizador=pipeline.vectorizar)
        ejecutar(executor, f"CREATE TABLE canciones (id INT PRIMARY KEY, nombre VARCHAR(20), "
                           f"ruta VARCHAR(40), v VECTOR({len(TONOS)}));")
        filas = ", ".join(f"({i}, 'Tema {i}', 'cancion_{i}.{extension}')" for i in TONOS)
        ejecutar(executor, f"INSERT INTO canciones (id, nombre, ruta) VALUES {filas};")
        assert pipeline.cargar(catalogo["canciones"], "ruta", extractor.descriptor_id) == len(TONOS)

        # La consulta: la canción 2 (440 Hz), más corta y 4 veces más bajita
        sf.write(media / f"audio_query.{extension}", tono(440, segundos=2.0, volumen=0.1), SR)
        resultado = ejecutar(executor,
            "SELECT nombre, SIMILARITY_SCORE() AS score FROM canciones "
            f"WHERE SIMILAR_TO('audio_query.{extension}', k=2) USING SEQ WITH METRIC=cosine "
            "ORDER BY score DESC;")
        assert resultado["rows"][0]["nombre"] == "Tema 2", resultado["rows"]
        assert resultado["rows"][0]["score"] > 0.99, resultado["rows"]

        for tabla in catalogo.values():
            tabla.cerrar()


if __name__ == "__main__":
    test_sin_vocabulario_mfcc()
    test_mfcc_registrado()
    print("OK: FeaturePipeline registra MFCC y consulta con un audio nuevo")