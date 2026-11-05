"""Pruebas de la Parte 4.1: extracción de patrones locales.

Se corren desde la carpeta backend:
    .venv/Scripts/python -m engine.multimedia.test_local_features
"""
import tempfile
from pathlib import Path

import cv2
import numpy as np
import soundfile as sf

from engine.multimedia.local_features import DescriptorBatch, SiftExtractor
from engine.multimedia.audio_features import MfccExtractor

def debe_fallar(funcion, caso):
    """Comprueba que funcion() lance ValueError. Si no lanza nada, la prueba falla."""
    try:
        funcion()
    except ValueError:
        return
    raise AssertionError(f"debía fallar y no falló: {caso}")


def test_descriptor_batch():
    # 1. Caso válido: una lista de enteros queda como matriz float32 (N, D)
    b = DescriptorBatch("t", 3, [[1, 2, 3], [4, 5, 6]])
    assert b.descriptor_id == "t"
    assert len(b) == 2
    assert b.values.dtype == np.float32 and b.values.shape == (2, 3)

    # 2. Lote vacío (imagen sin keypoints): forma (0, D), no (0,)
    vacio = DescriptorBatch("t", 128, [])
    assert len(vacio) == 0 and vacio.values.shape == (0, 128)

    # 3. Tiempos de MFCC como vector (N,): se guardan como columna (N, 1)
    audio = DescriptorBatch("t", 3, [[1, 2, 3], [4, 5, 6]], positions=[0.0, 0.023])
    assert audio.positions.shape == (2, 1)

    # 4. Lo que se debe rechazar
    debe_fallar(lambda: DescriptorBatch("t", 3, [[1, 2]]), "dimensión distinta")
    debe_fallar(lambda: DescriptorBatch("t", 3, [[1, 2, 3]], positions=np.zeros((2, 4))),
                "positions con otra cantidad de filas")
    debe_fallar(lambda: DescriptorBatch("t", 3, [[1, np.nan, 3]]), "valor NaN")
    debe_fallar(lambda: DescriptorBatch("t", 0, []), "dimensión 0")


def imagen_con_formas(alto=480, ancho=640):
    """Imagen sintética con bordes, esquinas y texto: SIFT encuentra keypoints."""
    img = np.full((alto, ancho), 40, np.uint8)
    cv2.rectangle(img, (60, 60), (220, 260), 200, -1)
    cv2.circle(img, (470, 200), 90, 140, -1)
    cv2.putText(img, "BD2", (230, 420), cv2.FONT_HERSHEY_SIMPLEX, 3, 255, 8)
    ruido = np.random.default_rng(0).integers(0, 25, img.shape, dtype=np.uint8)
    return cv2.GaussianBlur(cv2.add(img, ruido), (3, 3), 0)


def guardar(img, ruta):
    """cv2.imwrite también falla con tildes en Windows: se codifica en memoria
    y se escribe con numpy."""
    ok, buffer = cv2.imencode(".png", img)
    assert ok
    buffer.tofile(str(ruta))


def test_sift():
    ext = SiftExtractor(max_side=320, nfeatures=200)
    assert ext.descriptor_id == "sift:gray:max320:nf200"
    assert ext.dimension == 128

    with tempfile.TemporaryDirectory() as carpeta:
        carpeta = Path(carpeta)

        # 1. Imagen con estructura y con tildes en el nombre
        ruta = carpeta / "polo_azúl_ñ.png"
        guardar(imagen_con_formas(), ruta)
        b = ext.extract(ruta)
        n = len(b)
        assert n > 0, "una imagen con formas debe tener keypoints"
        assert b.values.shape == (n, 128) and b.positions.shape == (n, 4)
        assert b.descriptor_id == ext.descriptor_id and b.source == str(ruta)

        # 2. OpenCV entrega enteros entre 0 y 255 (por eso caben en uint8)
        assert b.values.min() >= 0 and b.values.max() <= 255
        assert np.array_equal(b.values, np.round(b.values))

        # 3. Posiciones en píxeles de la imagen ORIGINAL (640 x 480), aunque
        #    SIFT trabajó sobre la reducida (320 x 240): hay keypoints con x > 320
        x, y = b.positions[:, 0], b.positions[:, 1]
        assert x.min() >= 0 and x.max() < 640 and y.min() >= 0 and y.max() < 480
        assert x.max() > 320, "las posiciones no se reescalaron a la imagen original"

        # 4. Imagen lisa: 0 keypoints → lote vacío con las formas correctas
        lisa = carpeta / "lisa.png"
        guardar(np.full((200, 200), 128, np.uint8), lisa)
        v = ext.extract(lisa)
        assert len(v) == 0
        assert v.values.shape == (0, 128) and v.positions.shape == (0, 4)

        # 5. Archivos que no son imágenes
        falsa = carpeta / "falsa.jpg"
        falsa.write_bytes(b"esto no es una imagen")
        debe_fallar(lambda: ext.extract(falsa), "archivo que no es imagen")
        vacio = carpeta / "vacio.jpg"
        vacio.write_bytes(b"")
        debe_fallar(lambda: ext.extract(vacio), "archivo vacío")


def senal_de_prueba(segundos=2.0, sr=22050):
    """Dos tonos (440 Hz y 1200 Hz) con un poco de ruido."""
    t = np.arange(int(segundos * sr)) / sr
    ruido = 0.02 * np.random.default_rng(0).standard_normal(t.size)
    return (0.5 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 1200 * t) + ruido).astype(np.float32)


def test_mfcc():
    ext = MfccExtractor()
    assert ext.descriptor_id == "mfcc:sr22050:n13:fft2048:hop512:sinc0"
    assert ext.dimension == 12
    assert MfccExtractor(include_c0=True).dimension == 13
    assert MfccExtractor(max_seconds=30).descriptor_id.endswith(":dur30")
    assert MfccExtractor(max_seconds=30.0).descriptor_id == MfccExtractor(max_seconds=30).descriptor_id

    with tempfile.TemporaryDirectory() as carpeta:
        carpeta = Path(carpeta)
        senal = senal_de_prueba()

        # 1. Audio con tildes en el nombre: una fila por ventana
        # (subtype="FLOAT" guarda sin redondear; ver el punto 3)
        ruta = carpeta / "canción_niño.wav"
        sf.write(ruta, senal, 22050, subtype="FLOAT")
        b = ext.extract(ruta)
        ventanas = 1 + len(senal) // 512          # 1 + 44100 // 512 = 87
        assert b.values.shape == (ventanas, 12)
        assert b.descriptor_id == ext.descriptor_id and b.source == str(ruta)

        # 2. Posiciones: el tiempo de cada ventana, de 512/22050 ≈ 0,023 s en 0,023 s
        assert b.positions.shape == (ventanas, 1)
        assert b.positions[0, 0] == 0
        assert np.isclose(b.positions[1, 0], 512 / 22050)

        # 3. Volumen: la misma señal 4 veces más bajita. Se guarda en FLOAT
        #    porque un WAV de 16 bits redondea cada muestra, y a la señal
        #    bajita el redondeo le pesa más: la diferencia ya no sería ~0.
        bajito = carpeta / "bajito.wav"
        sf.write(bajito, senal * 0.25, 22050, subtype="FLOAT")
        assert np.allclose(ext.extract(bajito).values, b.values, atol=1e-3), \
            "sin c0, el volumen no debe cambiar los descriptores"
        con_c0 = MfccExtractor(include_c0=True)
        fuerte, suave = con_c0.extract(ruta).values, con_c0.extract(bajito).values
        assert not np.allclose(fuerte[:, 0], suave[:, 0]), "c0 sí depende del volumen"
        assert np.allclose(fuerte[:, 1:], suave[:, 1:], atol=1e-3)

        # 4. Estéreo a 44 100 Hz: se convierte a mono y a 22 050 Hz
        t44 = np.arange(len(senal) * 2) / 44100
        mono44 = np.interp(t44, np.arange(len(senal)) / 22050, senal).astype(np.float32)
        estereo = carpeta / "estereo.wav"
        sf.write(estereo, np.stack([mono44, mono44], axis=1), 44100)
        assert ext.extract(estereo).values.shape == (ventanas, 12)

        # 5. MP3 (solo si la librería de audio instalada sabe escribirlo)
        if "MP3" in sf.available_formats():
            mp3 = carpeta / "tema.mp3"
            sf.write(mp3, senal, 22050, format="MP3")
            assert len(ext.extract(mp3)) > 0

        # 6. Más corto que una ventana (100 muestras < 2048): lote vacío
        corto = carpeta / "corto.wav"
        sf.write(corto, senal[:100], 22050)
        v = ext.extract(corto)
        assert len(v) == 0 and v.values.shape == (0, 12) and v.positions.shape == (0, 1)

        # 7. Silencio total: nada que describir → lote vacío
        silencio = carpeta / "silencio.wav"
        sf.write(silencio, np.zeros(22050, np.float32), 22050)
        assert len(ext.extract(silencio)) == 0

        # 8. Tope de duración: con max_seconds=1 solo se lee el primer segundo
        assert len(MfccExtractor(max_seconds=1).extract(ruta)) == 1 + 22050 // 512

        # 9. Archivos que no son audio
        falso = carpeta / "falso.wav"
        falso.write_bytes(b"esto no es un audio")
        debe_fallar(lambda: ext.extract(falso), "archivo que no es audio")
        vacio = carpeta / "vacio.wav"
        vacio.write_bytes(b"")
        debe_fallar(lambda: ext.extract(vacio), "archivo vacío")

if __name__ == "__main__":
    test_descriptor_batch()
    print("OK: DescriptorBatch")
    test_sift()
    print("OK: SiftExtractor")
    test_mfcc()
    print("OK: MfccExtractor")