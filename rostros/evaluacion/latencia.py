import json

import comun
import matplotlib.pyplot as plt
import numpy as np

import lfw
from cache import Cache
from config import ARCHIVO_LFW
from detector import Detector
from embeddings import Embedder
from reconocedor import Reconocedor, buscar_en_motor

MUESTRAS = 500
CALENTAMIENTO = 20
ETAPAS = ("deteccion", "embedding", "motor", "motor_http", "total")


def etapas(reconocedor, fotos):
    for foto in fotos[:CALENTAMIENTO]:
        reconocedor.reconocer(foto["datos"], usar_cache=False)
    muestras = []
    for foto in fotos:
        resultado = reconocedor.reconocer(foto["datos"], usar_cache=False)
        if not resultado["caras"]:
            continue
        fila = {"archivo": foto["archivo"], "caras": len(resultado["caras"])}
        for etapa in ETAPAS:
            fila[etapa] = resultado["tiempos"][etapa]
        muestras.append(fila)
    return muestras


def indices(vectores, posiciones):
    filas = []
    for metodo in ("HNSW", "SEQ"):
        for posicion in posiciones[:CALENTAMIENTO]:
            buscar_en_motor(vectores[posicion], metodo=metodo)
        for posicion in posiciones:
            candidatos, tiempos = buscar_en_motor(vectores[posicion], metodo=metodo)
            filas.append({
                "metodo": metodo,
                "posicion": int(posicion),
                "primero": candidatos[0]["persona_id"] if candidatos else None,
                "motor_ms": tiempos["motor"],
                "http_ms": round(tiempos["motor_http"], 2),
            })
    return filas


def resumen_etapas(muestras):
    filas = []
    for etapa in ETAPAS:
        valores = []
        for muestra in muestras:
            valores.append(muestra[etapa])
        filas.append({
            "etapa": etapa,
            "mediana_ms": round(comun.percentil(valores, 50), 2),
            "p95_ms": round(comun.percentil(valores, 95), 2),
            "promedio_ms": round(float(np.mean(valores)), 2),
        })
    return filas


def resumen_indices(filas):
    primeros = {"HNSW": {}, "SEQ": {}}
    for fila in filas:
        primeros[fila["metodo"]][fila["posicion"]] = fila["primero"]
    iguales = 0
    for posicion, primero in primeros["HNSW"].items():
        if primero == primeros["SEQ"][posicion]:
            iguales += 1
    salida = []
    for metodo in ("HNSW", "SEQ"):
        motor = []
        http = []
        for fila in filas:
            if fila["metodo"] == metodo:
                motor.append(fila["motor_ms"])
                http.append(fila["http_ms"])
        salida.append({
            "metodo": metodo,
            "motor_mediana_ms": round(comun.percentil(motor, 50), 2),
            "motor_p95_ms": round(comun.percentil(motor, 95), 2),
            "http_mediana_ms": round(comun.percentil(http, 50), 2),
            "http_p95_ms": round(comun.percentil(http, 95), 2),
            "top1_igual_a_seq": round(iguales / len(primeros["HNSW"]), 4) if metodo == "HNSW" else 1.0,
        })
    return salida


def graficar(etapas_resumen, indices_resumen):
    figura, (izquierda, derecha) = plt.subplots(1, 2, figsize=(11, 4))
    nombres = []
    medianas = []
    extras = []
    for fila in etapas_resumen:
        nombres.append(fila["etapa"])
        medianas.append(fila["mediana_ms"])
        extras.append(fila["p95_ms"] - fila["mediana_ms"])
    izquierda.bar(nombres, medianas, yerr=[[0] * len(extras), extras], capsize=4)
    izquierda.axhline(100, color="red", linestyle="--", linewidth=1, label="100 ms")
    izquierda.set_title("Tiempo por etapa (mediana y p95)")
    izquierda.set_ylabel("ms")
    izquierda.legend()
    metodos = []
    motor = []
    http = []
    for fila in indices_resumen:
        metodos.append(fila["metodo"])
        motor.append(fila["motor_mediana_ms"])
        http.append(fila["http_mediana_ms"])
    posiciones = np.arange(len(metodos))
    derecha.bar(posiciones - 0.2, motor, width=0.4, label="motor (interno)")
    derecha.bar(posiciones + 0.2, http, width=0.4, label="petición HTTP")
    derecha.set_xticks(posiciones, metodos)
    derecha.set_title("Búsqueda en el motor: HNSW contra SEQ (mediana)")
    derecha.set_ylabel("ms")
    derecha.legend()
    for eje in (izquierda, derecha):
        eje.grid(axis="y", alpha=0.3)
    figura.tight_layout()
    figura.savefig(comun.CARPETA_RESULTADOS / "latencia.png", dpi=150)


def main():
    if not ARCHIVO_LFW.exists():
        raise SystemExit("falta LFW; corre 'descargas.py'")
    rng = np.random.default_rng(comun.SEMILLA)
    _, vectores, por_persona = comun.embeddings_lfw()
    fotos = lfw.leer(ARCHIVO_LFW)
    elegidas = []
    for indice in sorted(rng.choice(len(fotos), size=MUESTRAS, replace=False).tolist()):
        elegidas.append(fotos[indice])
    muestras = etapas(Reconocedor(Detector(), Embedder(), Cache()), elegidas)
    detectadas = []
    for posiciones in por_persona.values():
        detectadas.extend(posiciones)
    filas = indices(vectores, rng.choice(detectadas, size=MUESTRAS, replace=False).tolist())
    etapas_resumen = resumen_etapas(muestras)
    indices_resumen = resumen_indices(filas)
    comun.guardar_csv("latencia_muestras.csv", muestras)
    comun.guardar_csv("latencia.csv", etapas_resumen)
    comun.guardar_csv("hnsw_vs_seq_muestras.csv", filas)
    comun.guardar_csv("hnsw_vs_seq.csv", indices_resumen)
    graficar(etapas_resumen, indices_resumen)
    print(json.dumps({"etapas": etapas_resumen, "indices": indices_resumen}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
