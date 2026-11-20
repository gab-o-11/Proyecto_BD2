import json

import comun
import matplotlib.pyplot as plt
import numpy as np

from cache import Cache
from reconocedor import ETAPAS, Reconocedor

EVENTOS = 1000
FRECUENTES = 10
PROPORCION_FRECUENTES = 0.8
PROPORCION_DESCONOCIDOS = 0.05


def secuencia(pruebas, extra, rng):
    por_persona = {}
    for prueba in pruebas:
        por_persona.setdefault(prueba["verdad"], []).append(prueba)
    personas = sorted(por_persona)
    frecuentes = rng.choice(personas, size=FRECUENTES, replace=False).tolist()
    resto = []
    for persona in personas:
        if persona not in frecuentes:
            resto.append(persona)
    eventos = []
    for _ in range(EVENTOS):
        sorteo = rng.random()
        if sorteo < PROPORCION_FRECUENTES:
            persona = frecuentes[int(rng.integers(len(frecuentes)))]
        elif sorteo < 1 - PROPORCION_DESCONOCIDOS:
            persona = resto[int(rng.integers(len(resto)))]
        else:
            eventos.append(extra[int(rng.integers(len(extra)))])
            continue
        opciones = por_persona[persona]
        eventos.append(opciones[int(rng.integers(len(opciones)))])
    return eventos


def correr(reconocedor, eventos, vectores, usar_cache):
    filas = []
    for evento in eventos:
        tiempos = dict.fromkeys(ETAPAS, 0.0)
        resultado = reconocedor.identificar(vectores[evento["posicion"]], usar_cache, tiempos)
        filas.append({
            "cache": "con" if usar_cache else "sin",
            "fuente": resultado["fuente"],
            "verdad": evento["verdad"],
            "prediccion": resultado["persona_id"],
            "busqueda_ms": round(tiempos["cache"] + tiempos["motor_http"], 3),
        })
    return filas


def resumir(filas, nombre):
    tiempos = []
    correctas = 0
    desde_cache = 0
    errores_cache = 0
    for fila in filas:
        tiempos.append(fila["busqueda_ms"])
        if fila["prediccion"] == fila["verdad"]:
            correctas += 1
        if fila["fuente"] == "cache":
            desde_cache += 1
            if fila["prediccion"] != fila["verdad"]:
                errores_cache += 1
    return {
        "cache": nombre,
        "eventos": len(filas),
        "respondidas_por_cache": round(desde_cache / len(filas), 4),
        "errores_desde_cache": errores_cache,
        "exactitud": round(correctas / len(filas), 4),
        "mediana_ms": round(comun.percentil(tiempos, 50), 3),
        "p95_ms": round(comun.percentil(tiempos, 95), 3),
        "promedio_ms": round(float(np.mean(tiempos)), 3),
    }


def graficar(resumen):
    figura, eje = plt.subplots(figsize=(6, 4))
    nombres = []
    medianas = []
    p95 = []
    for fila in resumen:
        nombres.append(f"{fila['cache']} caché")
        medianas.append(fila["mediana_ms"])
        p95.append(fila["p95_ms"])
    posiciones = np.arange(len(nombres))
    eje.bar(posiciones - 0.2, medianas, width=0.4, label="mediana")
    eje.bar(posiciones + 0.2, p95, width=0.4, label="p95")
    eje.set_xticks(posiciones, nombres)
    eje.set_ylabel("ms por búsqueda")
    eje.set_title(f"Caché Redis: {resumen[1]['respondidas_por_cache']:.0%} de respuestas desde la caché")
    eje.grid(axis="y", alpha=0.3)
    eje.legend()
    figura.tight_layout()
    figura.savefig(comun.CARPETA_RESULTADOS / "cache.png", dpi=150)


def main():
    cache = Cache()
    if cache.estado() != "activa":
        raise SystemExit("Redis no responde; levántalo con 'pnpm dev:redis'")
    _, vectores, por_persona = comun.embeddings_lfw()
    registros, pruebas = comun.particion(por_persona, 5, np.random.default_rng(comun.SEMILLA + 5))
    rng = np.random.default_rng(comun.SEMILLA)
    eventos = secuencia(pruebas, comun.desconocidos(por_persona, rng), rng)
    comun.cargar_galeria(registros, vectores)
    reconocedor = Reconocedor(
        None, None, cache, tabla_rostros=comun.TABLA_EVAL_ROSTROS, tabla_personas=comun.TABLA_EVAL_PERSONAS
    )
    try:
        cache.limpiar()
        sin = correr(reconocedor, eventos, vectores, False)
        cache.limpiar()
        con = correr(reconocedor, eventos, vectores, True)
    finally:
        cache.limpiar()
        comun.borrar_galeria()
    resumen = [resumir(sin, "sin"), resumir(con, "con")]
    comun.guardar_csv("cache_muestras.csv", sin + con)
    comun.guardar_csv("cache.csv", resumen)
    graficar(resumen)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
