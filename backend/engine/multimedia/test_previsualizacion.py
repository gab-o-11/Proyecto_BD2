"""Pruebas de la previsualización de archivos multimedia.

Se corren desde la carpeta backend:
    .venv/Scripts/python -m engine.multimedia.test_previsualizacion
"""
import os
import tempfile
from pathlib import Path

from engine.multimedia.previsualizacion import (
    FormatoNoPrevisualizable,
    archivo_previsualizable,
    tipo_previsualizacion,
)


def debe_fallar(funcion, error, caso):
    """Comprueba que funcion() lance ese tipo de error (o uno que herede de él) y lo devuelve."""
    try:
        funcion()
    except error as lanzado:
        return lanzado
    raise AssertionError(f"debía fallar con {error.__name__} y no falló: {caso}")


def test_tipos():
    # La extensión decide el tipo, sin importar mayúsculas (Tiny ImageNet usa .JPEG)
    assert tipo_previsualizacion("tiny-imagenet-200/val/images/val_0.JPEG") == "image/jpeg"
    assert tipo_previsualizacion("fotos/a.png") == "image/png"
    assert tipo_previsualizacion("audio/fma_small/000/000002.mp3") == "audio/mpeg"
    assert tipo_previsualizacion("audio/tema.WAV") == "audio/wav"
    # Lo que no es imagen ni audio no se previsualiza
    assert tipo_previsualizacion("audio/MillionSongSubset/A/A/A/TRAAAAW128F429D538.h5") is None
    assert tipo_previsualizacion("tiny-imagenet-200/manifest.csv") is None
    assert tipo_previsualizacion("sin_extension") is None


def test_archivos():
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "multimedia"
        (carpeta / "imagenes").mkdir(parents=True)
        foto = carpeta / "imagenes" / "foto.PNG"
        foto.write_bytes(b"png")
        (carpeta / "datos.csv").write_text("a,b\n", encoding="utf-8")
        fuera = Path(tmp) / "secreto.png"
        fuera.write_bytes(b"png")

        # 1. Un archivo válido devuelve su ruta absoluta y su tipo
        ruta, tipo = archivo_previsualizable(str(carpeta), "imagenes/foto.PNG")
        assert Path(ruta) == foto.resolve() and tipo == "image/png"

        # 2. Extensión que no es imagen ni audio: 415 en la API
        debe_fallar(lambda: archivo_previsualizable(str(carpeta), "datos.csv"),
                    FormatoNoPrevisualizable, "csv")

        # 3. Archivo inexistente o fuera de la carpeta: 404 en la API, y no es un error de formato
        for ruta_mala, caso in [
            ("imagenes/no_existe.png", "archivo que no existe"),
            ("../secreto.png", "salir de la carpeta con .."),
            ("imagenes/../../secreto.png", "salir de la carpeta desde una subcarpeta"),
            (str(fuera), "ruta absoluta fuera de la carpeta"),
        ]:
            error = debe_fallar(lambda: archivo_previsualizable(str(carpeta), ruta_mala), ValueError, caso)
            assert not isinstance(error, FormatoNoPrevisualizable), caso

        # 4. Una carpeta con nombre de imagen no es un archivo
        (carpeta / "album.png").mkdir()
        error = debe_fallar(lambda: archivo_previsualizable(str(carpeta), "album.png"), ValueError, "carpeta")
        assert not isinstance(error, FormatoNoPrevisualizable)
        assert os.path.isfile(fuera)  # nada se borró ni se movió


if __name__ == "__main__":
    test_tipos()
    print("OK: tipos de previsualización")
    test_archivos()
    print("OK: archivos dentro y fuera de la carpeta multimedia")