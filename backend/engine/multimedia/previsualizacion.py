import os

from .extract_features import resolver_archivo

TIPOS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


class FormatoNoPrevisualizable(ValueError):
    """La extensión no es de imagen ni de audio."""


def tipo_previsualizacion(ruta):
    """Tipo MIME con el que se muestra el archivo, o None si no es imagen ni audio."""
    return TIPOS.get(os.path.splitext(ruta)[1].lower())


def archivo_previsualizable(carpeta, ruta):
    """Devuelve (ruta absoluta, tipo MIME) de un archivo mostrable de la carpeta multimedia."""
    tipo = tipo_previsualizacion(ruta)
    if tipo is None:
        raise FormatoNoPrevisualizable(f"'{ruta}' no es una imagen ni un audio que se pueda previsualizar")
    return resolver_archivo(carpeta, ruta), tipo