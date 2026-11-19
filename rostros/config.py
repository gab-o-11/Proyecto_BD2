import os
from pathlib import Path

RAIZ_ROSTROS = Path(__file__).resolve().parent
RAIZ_PROYECTO = RAIZ_ROSTROS.parent

URL_MOTOR = os.environ.get("BD2_URL", "http://localhost:8000")
URL_REDIS = os.environ.get("ROSTROS_REDIS", "redis://localhost:6379/0")
PUERTO = int(os.environ.get("ROSTROS_PUERTO", "8200"))

CARPETA_DATOS = Path(os.environ.get("ROSTROS_DATOS", RAIZ_PROYECTO / "data" / "rostros"))
CARPETA_MODELOS = CARPETA_DATOS / "modelos"
CARPETA_IMPORTAR = CARPETA_DATOS / "carpeta"
CARPETA_FOTOS = Path(os.environ.get("ROSTROS_FOTOS", CARPETA_DATOS / "fotos"))
CARPETA_PROPIAS = CARPETA_FOTOS / "propias"

URL_LFW = "https://huggingface.co/datasets/bitmind/lfw/resolve/main/data/train-00000-of-00001.parquet"
URL_YUNET = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
URL_ARCFACE = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
ARCHIVO_LFW = CARPETA_DATOS / "lfw.parquet"
ARCHIVO_EMBEDDINGS = CARPETA_DATOS / "embeddings_lfw.npz"
MODELO_YUNET = CARPETA_MODELOS / "face_detection_yunet_2023mar.onnx"
MODELO_ARCFACE = CARPETA_MODELOS / "w600k_r50.onnx"

DIMENSION = 512
LADO_ALINEADO = 112
CONFIANZA_DETECCION = 0.8
LADO_MINIMO_CARA = 40
MAX_CARAS = 5
K_VECINOS = 5
UMBRAL = float(os.environ.get("ROSTROS_UMBRAL", "0.40"))
UMBRAL_CACHE = float(os.environ.get("ROSTROS_UMBRAL_CACHE", "0.55"))
N_FRECUENTES = 20
FOTOS_REGISTRO = 5
LARGO_NOMBRE = 60
LOTE_INSERT = 40

TABLA_PERSONAS = os.environ.get("ROSTROS_TABLA_PERSONAS", "personas")
TABLA_ROSTROS = os.environ.get("ROSTROS_TABLA_ROSTROS", "rostros")
