import numpy as np

EUCLIDEAN = "euclidean"
COSINE = "cosine"
DOT = "dot"
METRICAS = (EUCLIDEAN, COSINE, DOT)


def validar_metrica(metrica):
    if metrica not in METRICAS:
        raise ValueError(f"métrica desconocida '{metrica}'; usa {', '.join(METRICAS)}")
    return metrica


def distancias(consulta, matriz, metrica):
    validar_metrica(metrica)
    consulta = np.asarray(consulta, dtype=np.float32)
    matriz = np.asarray(matriz, dtype=np.float32)
    if metrica == EUCLIDEAN:
        diferencia = matriz - consulta
        return np.sqrt(np.einsum("ij,ij->i", diferencia, diferencia))
    producto = matriz @ consulta
    if metrica == DOT:
        return -producto
    normas = np.linalg.norm(matriz, axis=1) * np.linalg.norm(consulta)
    coseno = np.divide(producto, normas, out=np.zeros_like(producto), where=normas > 0)
    return 1.0 - np.clip(coseno, -1.0, 1.0)


def distancias_entre(matriz, metrica):
    validar_metrica(metrica)
    matriz = np.asarray(matriz, dtype=np.float32)
    producto = matriz @ matriz.T
    if metrica == DOT:
        return -producto
    cuadrados = np.diag(producto)
    if metrica == EUCLIDEAN:
        return np.sqrt(np.maximum(cuadrados[:, None] + cuadrados[None, :] - 2.0 * producto, 0.0))
    normas = np.sqrt(cuadrados)
    denominador = normas[:, None] * normas[None, :]
    coseno = np.divide(producto, denominador, out=np.zeros_like(producto), where=denominador > 0)
    return 1.0 - np.clip(coseno, -1.0, 1.0)


def distancia(a, b, metrica):
    return float(distancias(a, np.asarray(b, dtype=np.float32).reshape(1, -1), metrica)[0])


def score(valor, metrica):
    validar_metrica(metrica)
    if metrica == EUCLIDEAN:
        return 1.0 / (1.0 + valor)
    if metrica == COSINE:
        return 1.0 - valor
    return -valor
