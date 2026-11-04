import numpy as np

TAMANO_LOTE = 2048


def _matrices(descriptores, centroides):
    centroides = np.asarray(centroides, dtype=np.float32)
    if centroides.ndim != 2 or centroides.shape[0] == 0:
        raise ValueError("el vocabulario debe ser una matriz (K, D) con al menos una palabra")
    descriptores = np.asarray(descriptores, dtype=np.float32)
    if descriptores.size == 0:
        descriptores = descriptores.reshape(0, centroides.shape[1])
    if descriptores.ndim != 2 or descriptores.shape[1] != centroides.shape[1]:
        raise ValueError(f"se esperaban descriptores (N, {centroides.shape[1]}) y llegó {descriptores.shape}")
    return descriptores, centroides


def asignar_palabras(descriptores, centroides):
    descriptores, centroides = _matrices(descriptores, centroides)
    normas = np.einsum("ij,ij->i", centroides, centroides)
    palabras = np.empty(len(descriptores), dtype=np.int64)
    for inicio in range(0, len(descriptores), TAMANO_LOTE):
        lote = descriptores[inicio:inicio + TAMANO_LOTE]
        palabras[inicio:inicio + len(lote)] = np.argmin(normas - 2.0 * (lote @ centroides.T), axis=1)
    return palabras


def construir_histograma(descriptores, centroides):
    centroides = np.asarray(centroides, dtype=np.float32)
    return np.bincount(asignar_palabras(descriptores, centroides), minlength=centroides.shape[0])
