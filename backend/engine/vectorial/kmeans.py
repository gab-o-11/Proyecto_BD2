import numpy as np

from .metricas import COSINE, EUCLIDEAN, distancias

ITERACIONES = 50
TOLERANCIA = 1e-4
TAMANO_LOTE = 2048


def asignar(matriz, centroides, metrica):
    asignaciones = np.empty(len(matriz), dtype=np.int64)
    distancia_propia = np.empty(len(matriz), dtype=np.float32)
    if metrica == COSINE:
        normas = np.linalg.norm(centroides, axis=1, keepdims=True)
        centroides = np.divide(centroides, normas, out=np.zeros_like(centroides), where=normas > 0)
    for inicio in range(0, len(matriz), TAMANO_LOTE):
        lote = matriz[inicio:inicio + TAMANO_LOTE]
        if metrica == COSINE:
            normas = np.linalg.norm(lote, axis=1, keepdims=True)
            lote = np.divide(lote, normas, out=np.zeros_like(lote), where=normas > 0)
            valores = 1.0 - lote @ centroides.T
        else:
            valores = (
                np.einsum("ij,ij->i", lote, lote)[:, None]
                - 2.0 * (lote @ centroides.T)
                + np.einsum("ij,ij->i", centroides, centroides)
            )
        cercanos = np.argmin(valores, axis=1)
        asignaciones[inicio:inicio + len(lote)] = cercanos
        distancia_propia[inicio:inicio + len(lote)] = valores[np.arange(len(lote)), cercanos]
    return asignaciones, distancia_propia


def kmeans(matriz, k, metrica=EUCLIDEAN, iteraciones=ITERACIONES, tolerancia=TOLERANCIA, semilla=0):
    matriz = np.asarray(matriz, dtype=np.float32)
    if matriz.ndim != 2 or matriz.shape[0] == 0:
        raise ValueError("k-means necesita una matriz (N, D) con datos")
    if metrica not in (EUCLIDEAN, COSINE):
        raise ValueError("k-means solo agrupa con distancia euclidiana o coseno")
    if not 1 <= k <= len(matriz):
        raise ValueError(f"k debe estar entre 1 y {len(matriz)}")
    azar = np.random.default_rng(semilla)
    centroides = matriz[azar.choice(len(matriz), k, replace=False)].copy()
    asignaciones = None
    for _ in range(iteraciones):
        nuevas, propias = asignar(matriz, centroides, metrica)
        if asignaciones is not None and np.array_equal(nuevas, asignaciones):
            break
        asignaciones = nuevas
        anteriores = centroides.copy()
        sumas = np.zeros_like(centroides, dtype=np.float64)
        np.add.at(sumas, asignaciones, matriz)
        conteos = np.bincount(asignaciones, minlength=k)
        ocupados = conteos > 0
        centroides[ocupados] = (sumas[ocupados] / conteos[ocupados, None]).astype(np.float32)
        vacios = np.flatnonzero(~ocupados)
        if vacios.size:
            lejanos = np.argsort(propias)[::-1][:vacios.size]
            centroides[vacios] = matriz[lejanos]
        elif np.linalg.norm(centroides - anteriores, axis=1).max() <= tolerancia:
            break
    asignaciones, _ = asignar(matriz, centroides, metrica)
    return centroides, asignaciones


def centroides_cercanos(consulta, centroides, metrica, cantidad):
    valores = distancias(consulta, centroides, metrica)
    return np.argsort(valores, kind="stable")[:cantidad]
