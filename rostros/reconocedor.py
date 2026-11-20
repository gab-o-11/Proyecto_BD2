import time

import cliente_bd as bd
from config import K_VECINOS, TABLA_PERSONAS, TABLA_ROSTROS, UMBRAL, UMBRAL_CACHE
from detector import alinear, decodificar

ETAPAS = ("decodificacion", "deteccion", "embedding", "cache", "motor", "motor_http", "total")


def milisegundos(desde):
    return (time.perf_counter() - desde) * 1000


def mejores_por_persona(filas):
    mejores = {}
    for fila in filas:
        actual = mejores.get(fila["persona_id"])
        if actual is None or fila["score"] > actual["score"]:
            mejores[fila["persona_id"]] = fila
    return sorted(mejores.values(), key=lambda fila: fila["score"], reverse=True)


def decidir(candidatos, umbral):
    if not candidatos:
        return None, None
    if candidatos[0]["score"] < umbral:
        return None, candidatos[0]["score"]
    return candidatos[0], candidatos[0]["score"]


def buscar_en_motor(vector, metodo="HNSW", k=K_VECINOS, tabla_rostros=TABLA_ROSTROS):
    inicio = time.perf_counter()
    datos = bd.ejecutar(
        f"SELECT persona_id, archivo, SIMILARITY_SCORE() AS score FROM {tabla_rostros} "
        f"WHERE SIMILAR_TO({bd.vector_sql(vector)}, k={k}) USING {metodo} WITH METRIC=cosine ORDER BY score DESC;"
    )
    return mejores_por_persona(datos.get("rows", [])), {"motor": datos["elapsedMs"], "motor_http": milisegundos(inicio)}


def nombre_de(persona_id, tabla_personas=TABLA_PERSONAS):
    inicio = time.perf_counter()
    datos = bd.ejecutar(f"SELECT nombre FROM {tabla_personas} WHERE id = {bd.numero_sql(persona_id)};")
    filas = datos.get("rows", [])
    nombre = filas[0]["nombre"] if filas else None
    return nombre, {"motor": datos["elapsedMs"], "motor_http": milisegundos(inicio)}


def sumar(tiempos, parciales):
    for etapa, valor in parciales.items():
        tiempos[etapa] += valor


class Reconocedor:
    def __init__(self, detector, embedder, cache, umbral=UMBRAL, umbral_cache=UMBRAL_CACHE,
                 tabla_rostros=TABLA_ROSTROS, tabla_personas=TABLA_PERSONAS):
        self.detector = detector
        self.embedder = embedder
        self.cache = cache
        self.umbral = umbral
        self.umbral_cache = umbral_cache
        self.tabla_rostros = tabla_rostros
        self.tabla_personas = tabla_personas

    def identificar(self, vector, usar_cache, tiempos):
        if usar_cache:
            inicio = time.perf_counter()
            encontrado = self.cache.buscar(vector, self.umbral_cache)
            tiempos["cache"] += milisegundos(inicio)
            if encontrado is not None:
                encontrado["fuente"] = "cache"
                return encontrado
        candidatos, parciales = buscar_en_motor(vector, tabla_rostros=self.tabla_rostros)
        sumar(tiempos, parciales)
        ganador, score = decidir(candidatos, self.umbral)
        if ganador is None:
            return {"persona_id": None, "nombre": None, "foto": None, "similitud": score, "fuente": "motor"}
        nombre, parciales = nombre_de(ganador["persona_id"], self.tabla_personas)
        sumar(tiempos, parciales)
        if usar_cache:
            self.cache.registrar(ganador["persona_id"], nombre, ganador["archivo"], vector)
        return {
            "persona_id": ganador["persona_id"],
            "nombre": nombre,
            "foto": ganador["archivo"],
            "similitud": ganador["score"],
            "fuente": "motor",
        }

    def reconocer(self, datos, usar_cache=True):
        tiempos = dict.fromkeys(ETAPAS, 0.0)
        inicio_total = time.perf_counter()
        inicio = time.perf_counter()
        imagen = decodificar(datos)
        tiempos["decodificacion"] = milisegundos(inicio)
        inicio = time.perf_counter()
        caras = self.detector.detectar(imagen)
        tiempos["deteccion"] = milisegundos(inicio)
        inicio = time.perf_counter()
        validas = []
        alineadas = []
        for cara in caras:
            try:
                alineadas.append(alinear(imagen, cara["puntos"]))
            except ValueError:
                continue
            validas.append(cara)
        vectores = self.embedder.calcular(alineadas)
        tiempos["embedding"] = milisegundos(inicio)
        estado = self.cache.estado() if usar_cache else "desactivada"
        resultados = []
        for cara, vector in zip(validas, vectores):
            resultado = self.identificar(vector, estado == "activa", tiempos)
            resultado["caja"] = cara["caja"]
            if resultado["similitud"] is not None:
                resultado["similitud"] = round(float(resultado["similitud"]), 4)
            resultados.append(resultado)
        tiempos["total"] = milisegundos(inicio_total)
        redondeados = {}
        for etapa, valor in tiempos.items():
            redondeados[etapa] = round(valor, 1)
        alto, ancho = imagen.shape[:2]
        return {"ancho": ancho, "alto": alto, "caras": resultados, "cache": estado, "tiempos": redondeados}
