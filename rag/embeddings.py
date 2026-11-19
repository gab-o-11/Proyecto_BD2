import numpy as np

from config import DIMENSION, MODELO_EMBEDDINGS

_modelo = None


def modelo():
    global _modelo
    if _modelo is None:
        from sentence_transformers import SentenceTransformer
        _modelo = SentenceTransformer(MODELO_EMBEDDINGS, device="cpu")
        if _modelo.get_embedding_dimension() != DIMENSION:
            raise RuntimeError(f"{MODELO_EMBEDDINGS} no produce vectores de {DIMENSION}")
    return _modelo


def pasajes(textos, lote=32, progreso=False):
    entradas = []
    for texto in textos:
        entradas.append("passage: " + texto)
    vectores = modelo().encode(entradas, batch_size=lote, normalize_embeddings=True, show_progress_bar=progreso)
    return np.asarray(vectores, dtype=np.float32)


def consulta(texto):
    vector = modelo().encode(["query: " + texto], normalize_embeddings=True)
    return np.asarray(vector[0], dtype=np.float32)
