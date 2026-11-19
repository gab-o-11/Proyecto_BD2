import json
import time

import comun
import matplotlib.pyplot as plt
import numpy as np

from config import UMBRAL
from reconocedor import buscar_en_motor

FOTOS = (1, 3, 5)
UMBRALES = np.round(np.arange(0.10, 0.81, 0.01), 2)
MARGEN_CACHE = 0.10


def evaluar(n, por_persona, vectores, extra):
    registros, pruebas = comun.particion(por_persona, n, np.random.default_rng(comun.SEMILLA + n))
    comun.cargar_galeria(registros, vectores)
    resultados = []
    inicio = time.time()
    try:
        for prueba in pruebas + extra:
            candidatos, _ = buscar_en_motor(vectores[prueba["posicion"]], tabla_rostros=comun.TABLA_EVAL_ROSTROS)
            mejor = candidatos[0] if candidatos else None
            resultados.append({
                "fotos": n,
                "tipo": "conocida" if prueba["verdad"] is not None else "desconocida",
                "verdad": prueba["verdad"],
                "prediccion": mejor["persona_id"] if mejor else None,
                "score": round(float(mejor["score"]), 4) if mejor else -1.0,
            })
    finally:
        comun.borrar_galeria()
    personas = set()
    for registro in registros:
        personas.add(registro["persona_id"])
    print(
        f"  {n} foto(s): {len(personas)} personas registradas, {len(pruebas)} pruebas conocidas "
        f"y {len(extra)} desconocidas ({time.time() - inicio:.0f} s)"
    )
    return resultados


def curvas(resultados, n):
    conocidas = []
    desconocidas = []
    for resultado in resultados:
        if resultado["tipo"] == "conocida":
            conocidas.append(resultado)
        else:
            desconocidas.append(resultado)
    filas = []
    for umbral in UMBRALES:
        aciertos = 0
        for resultado in conocidas:
            if resultado["prediccion"] == resultado["verdad"] and resultado["score"] >= umbral:
                aciertos += 1
        rechazos = 0
        for resultado in desconocidas:
            if resultado["score"] < umbral:
                rechazos += 1
        aceptadas = 0
        errores = 0
        for resultado in conocidas + desconocidas:
            if resultado["score"] >= umbral:
                aceptadas += 1
                if resultado["prediccion"] != resultado["verdad"]:
                    errores += 1
        filas.append({
            "fotos": n,
            "umbral": float(umbral),
            "acierto_conocidas": round(aciertos / len(conocidas), 4),
            "rechazo_desconocidas": round(rechazos / len(desconocidas), 4),
            "error_aceptadas": round(errores / aceptadas, 4) if aceptadas else 0.0,
        })
    return filas


def elegir(filas):
    mejor = max(filas, key=lambda fila: fila["acierto_conocidas"] + fila["rechazo_desconocidas"])
    return mejor["umbral"], round(mejor["umbral"] + MARGEN_CACHE, 2)


def graficar(filas):
    figura, (izquierda, derecha) = plt.subplots(1, 2, figsize=(11, 4))
    for n in FOTOS:
        umbrales = []
        aciertos = []
        rechazos = []
        for fila in filas:
            if fila["fotos"] == n:
                umbrales.append(fila["umbral"])
                aciertos.append(fila["acierto_conocidas"])
                rechazos.append(fila["rechazo_desconocidas"])
        izquierda.plot(umbrales, aciertos, label=f"{n} foto(s)")
        derecha.plot(umbrales, rechazos, label=f"{n} foto(s)")
    izquierda.set_title("Personas registradas reconocidas")
    derecha.set_title("Desconocidos rechazados")
    for eje in (izquierda, derecha):
        eje.set_xlabel("umbral de similitud coseno")
        eje.set_ylim(0, 1.02)
        eje.grid(alpha=0.3)
        eje.legend()
    figura.tight_layout()
    figura.savefig(comun.CARPETA_RESULTADOS / "acierto.png", dpi=150)


def main():
    _, vectores, por_persona = comun.embeddings_lfw()
    extra = comun.desconocidos(por_persona, np.random.default_rng(comun.SEMILLA))
    muestras = []
    filas = []
    for n in FOTOS:
        resultados = evaluar(n, por_persona, vectores, extra)
        muestras.extend(resultados)
        filas.extend(curvas(resultados, n))
    calibracion = []
    for fila in filas:
        if fila["fotos"] == 5:
            calibracion.append(fila)
    umbral, umbral_cache = elegir(calibracion)
    resumen = {"umbral": umbral, "umbral_cache": umbral_cache, "fotos_calibracion": 5, "umbral_inicial": UMBRAL}
    for fila in filas:
        if fila["umbral"] == umbral:
            resumen[f"acierto_{fila['fotos']}_fotos"] = fila["acierto_conocidas"]
            resumen[f"rechazo_{fila['fotos']}_fotos"] = fila["rechazo_desconocidas"]
        if fila["umbral"] == umbral_cache and fila["fotos"] == 5:
            resumen["acierto_5_fotos_con_umbral_cache"] = fila["acierto_conocidas"]
    comun.guardar_csv("acierto_muestras.csv", muestras)
    comun.guardar_csv("acierto.csv", filas)
    comun.guardar_json("umbrales.json", resumen)
    graficar(filas)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
