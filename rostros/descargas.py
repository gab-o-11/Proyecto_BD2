import shutil
import zipfile

import requests

from config import ARCHIVO_LFW, CARPETA_MODELOS, MODELO_ARCFACE, MODELO_YUNET, URL_ARCFACE, URL_LFW, URL_YUNET


def bajar(url, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".parcial")
    print(f"descargando {url}")
    with requests.get(url, stream=True, timeout=60) as respuesta:
        respuesta.raise_for_status()
        with open(temporal, "wb") as archivo:
            for bloque in respuesta.iter_content(1 << 20):
                archivo.write(bloque)
    temporal.replace(destino)


def modelos():
    if not MODELO_YUNET.exists():
        bajar(URL_YUNET, MODELO_YUNET)
    if MODELO_ARCFACE.exists():
        return
    comprimido = CARPETA_MODELOS / "buffalo_l.zip"
    bajar(URL_ARCFACE, comprimido)
    with zipfile.ZipFile(comprimido) as paquete:
        for nombre in paquete.namelist():
            if nombre.endswith("w600k_r50.onnx"):
                with paquete.open(nombre) as origen, open(MODELO_ARCFACE, "wb") as destino:
                    shutil.copyfileobj(origen, destino, 1 << 20)
    comprimido.unlink()
    if not MODELO_ARCFACE.exists():
        raise SystemExit("buffalo_l.zip no trae w600k_r50.onnx")


def lfw():
    if not ARCHIVO_LFW.exists():
        bajar(URL_LFW, ARCHIVO_LFW)
    return ARCHIVO_LFW


if __name__ == "__main__":
    modelos()
    lfw()
    print(f"modelos y LFW listos en {CARPETA_MODELOS.parent}")
