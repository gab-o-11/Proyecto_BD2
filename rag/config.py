import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ_RAG = Path(__file__).resolve().parent
RAIZ_PROYECTO = RAIZ_RAG.parent

load_dotenv(RAIZ_RAG / ".env")

URL_MOTOR = os.environ.get("BD2_URL", "http://localhost:8000")
CARPETA_DATOS = Path(os.environ.get("RAG_DATOS", RAIZ_PROYECTO / "data" / "rag"))
URL_DATASET = "https://huggingface.co/datasets/nglaura/scielo-summarization/resolve/main"
SPLIT = os.environ.get("RAG_SPLIT", "test")

MODELO_LLM = os.environ.get("RAG_MODELO_LLM", "gpt-6-luna")
ESFUERZO_LLM = os.environ.get("RAG_ESFUERZO", "low")
MODELO_EMBEDDINGS = "intfloat/multilingual-e5-small"
DIMENSION = 384

PALABRAS_CHUNK = 200
SOLAPAMIENTO = 40
PALABRAS_CABECERA = 350

K_CANDIDATOS = 20
K_CONTEXTO = 5
RRF_K = 60
LOTE_INSERT = 40

TABLA_ARTICULOS = "articulos"
TABLA_CHUNKS = "chunks"
INDICE_TEXTO = "ft_chunks"
INDICE_VECTORES = "hnsw_chunks"

PUERTO = int(os.environ.get("RAG_PUERTO", "8100"))
