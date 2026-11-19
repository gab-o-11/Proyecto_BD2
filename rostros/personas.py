import shutil
import threading

import requests

import cliente_bd as bd
from config import CARPETA_FOTOS, CARPETA_PROPIAS, FOTOS_REGISTRO, LARGO_NOMBRE, TABLA_PERSONAS, TABLA_ROSTROS
from detector import alinear, decodificar

candado = threading.Lock()


class ErrorSolicitud(Exception):
    def __init__(self, mensaje, estado=400, foto=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado
        self.foto = foto

    def contenido(self):
        salida = {"error": self.mensaje}
        if self.foto is not None:
            salida["foto"] = self.foto
        return salida


def validar_nombre(nombre):
    limpio = " ".join((nombre or "").split())
    if not limpio:
        raise ErrorSolicitud("el nombre no puede estar vacío")
    if len(limpio.encode("utf-8")) > LARGO_NOMBRE:
        raise ErrorSolicitud(f"el nombre es demasiado largo (máximo {LARGO_NOMBRE} bytes)")
    return limpio


def vectores_de_fotos(fotos, detector, embedder):
    alineadas = []
    for indice, datos in enumerate(fotos, start=1):
        try:
            imagen = decodificar(datos)
        except ValueError:
            raise ErrorSolicitud(f"la foto {indice} no se pudo leer", foto=indice) from None
        caras = detector.detectar(imagen, maximo=None)
        if not caras:
            raise ErrorSolicitud(f"la foto {indice} no tiene un rostro", foto=indice)
        if len(caras) > 1:
            raise ErrorSolicitud(f"la foto {indice} tiene {len(caras)} rostros; debe tener uno solo", foto=indice)
        try:
            alineadas.append(alinear(imagen, caras[0]["puntos"]))
        except ValueError:
            raise ErrorSolicitud(f"el rostro de la foto {indice} no se pudo alinear", foto=indice) from None
    return embedder.calcular(alineadas)


def siguiente_id(tabla):
    return (bd.filas(f"SELECT MAX(id) FROM {tabla};")[0]["max_id"] or 0) + 1


def persona_propia(persona_id):
    filas = bd.filas(f"SELECT id, nombre, origen FROM {TABLA_PERSONAS} WHERE id = {int(persona_id)};")
    if not filas or filas[0]["origen"] != "propia":
        raise ErrorSolicitud(f"no existe una persona propia con id {persona_id}", estado=404)
    return filas[0]


def fotos_de(persona_id):
    filas = bd.filas(f"SELECT id, archivo FROM {TABLA_ROSTROS} WHERE persona_id = {int(persona_id)};")
    return sorted(filas, key=lambda fila: fila["id"])


def detalle(persona_id):
    persona = persona_propia(persona_id)
    fotos = []
    for fila in fotos_de(persona_id):
        fotos.append({"id": fila["id"], "archivo": fila["archivo"]})
    return {"id": persona["id"], "nombre": persona["nombre"], "fotos": fotos}


def listar():
    personas = bd.filas(f"SELECT id, nombre FROM {TABLA_PERSONAS} WHERE origen = 'propia';")
    if not personas:
        return []
    ids = []
    for persona in personas:
        ids.append(persona["id"])
    filas = bd.filas(f"SELECT id, persona_id, archivo FROM {TABLA_ROSTROS} WHERE persona_id IN {bd.lista_sql(ids)};")
    por_persona = {}
    for fila in sorted(filas, key=lambda fila: fila["id"]):
        por_persona.setdefault(fila["persona_id"], []).append(fila)
    salida = []
    for persona in sorted(personas, key=lambda persona: persona["nombre"].lower()):
        fotos = por_persona.get(persona["id"], [])
        salida.append({
            "id": persona["id"],
            "nombre": persona["nombre"],
            "fotos": len(fotos),
            "portada": fotos[0]["archivo"] if fotos else None,
        })
    return salida


def guardar_archivos(persona_id, ids, fotos):
    rutas = []
    for rostro_id, datos in zip(ids, fotos):
        relativa = f"propias/{persona_id}/{rostro_id}.jpg"
        destino = CARPETA_FOTOS / relativa
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
        rutas.append(relativa)
    return rutas


def borrar_archivos(rutas):
    for ruta in rutas:
        (CARPETA_FOTOS / ruta).unlink(missing_ok=True)


def insertar_rostros(persona_id, ids, rutas, vectores):
    valores = []
    for rostro_id, ruta, vector in zip(ids, rutas, vectores):
        valores.append(f"({rostro_id}, {persona_id}, {bd.texto_sql(ruta)}, {bd.vector_sql(vector)})")
    return f"INSERT INTO {TABLA_ROSTROS} VALUES " + ", ".join(valores) + ";"


def deshacer(sentencias, rutas):
    try:
        bd.ejecutar(" ".join(sentencias))
    except (bd.ErrorMotor, requests.RequestException):
        pass
    borrar_archivos(rutas)


def registrar(nombre, fotos, detector, embedder):
    nombre = validar_nombre(nombre)
    if len(fotos) != FOTOS_REGISTRO:
        raise ErrorSolicitud(f"se necesitan {FOTOS_REGISTRO} fotos y llegaron {len(fotos)}")
    vectores = vectores_de_fotos(fotos, detector, embedder)
    with candado:
        repetidas = bd.filas(
            f"SELECT id FROM {TABLA_PERSONAS} WHERE nombre = {bd.texto_sql(nombre)} AND origen = 'propia';"
        )
        if repetidas:
            raise ErrorSolicitud(f"ya existe una persona llamada '{nombre}'; agrégale fotos desde Mis rostros")
        persona_id = siguiente_id(TABLA_PERSONAS)
        primero = siguiente_id(TABLA_ROSTROS)
        ids = list(range(primero, primero + len(fotos)))
        rutas = guardar_archivos(persona_id, ids, fotos)
        try:
            bd.ejecutar(
                "BEGIN TRANSACTION; "
                f"INSERT INTO {TABLA_PERSONAS} VALUES ({persona_id}, {bd.texto_sql(nombre)}, 'propia'); "
                f"{insertar_rostros(persona_id, ids, rutas, vectores)} "
                "END TRANSACTION;"
            )
        except (bd.ErrorMotor, requests.RequestException):
            deshacer([
                f"DELETE FROM {TABLA_ROSTROS} WHERE persona_id = {persona_id};",
                f"DELETE FROM {TABLA_PERSONAS} WHERE id = {persona_id};",
            ], rutas)
            raise
    return detalle(persona_id)


def agregar_fotos(persona_id, fotos, detector, embedder, cache):
    persona_propia(persona_id)
    if not fotos:
        raise ErrorSolicitud("no llegó ninguna foto")
    vectores = vectores_de_fotos(fotos, detector, embedder)
    with candado:
        primero = siguiente_id(TABLA_ROSTROS)
        ids = list(range(primero, primero + len(fotos)))
        rutas = guardar_archivos(persona_id, ids, fotos)
        try:
            bd.ejecutar(insertar_rostros(persona_id, ids, rutas, vectores))
        except (bd.ErrorMotor, requests.RequestException):
            sentencias = []
            for rostro_id in ids:
                sentencias.append(f"DELETE FROM {TABLA_ROSTROS} WHERE id = {rostro_id};")
            deshacer(sentencias, rutas)
            raise
    cache.quitar(persona_id)
    return detalle(persona_id)


def eliminar_persona(persona_id, cache):
    persona_propia(persona_id)
    rutas = []
    for fila in fotos_de(persona_id):
        rutas.append(fila["archivo"])
    bd.ejecutar(
        "BEGIN TRANSACTION; "
        f"DELETE FROM {TABLA_ROSTROS} WHERE persona_id = {int(persona_id)}; "
        f"DELETE FROM {TABLA_PERSONAS} WHERE id = {int(persona_id)}; "
        "END TRANSACTION;"
    )
    borrar_archivos(rutas)
    shutil.rmtree(CARPETA_PROPIAS / str(int(persona_id)), ignore_errors=True)
    cache.quitar(persona_id)
    return {"eliminada": int(persona_id)}


def eliminar_rostro(rostro_id, cache):
    filas = bd.filas(f"SELECT id, persona_id, archivo FROM {TABLA_ROSTROS} WHERE id = {int(rostro_id)};")
    if not filas:
        raise ErrorSolicitud(f"no existe el rostro {rostro_id}", estado=404)
    persona_id = filas[0]["persona_id"]
    persona_propia(persona_id)
    if len(fotos_de(persona_id)) == 1:
        eliminar_persona(persona_id, cache)
        return {"persona_eliminada": True, "persona_id": persona_id}
    bd.ejecutar(f"DELETE FROM {TABLA_ROSTROS} WHERE id = {int(rostro_id)};")
    borrar_archivos([filas[0]["archivo"]])
    cache.quitar(persona_id)
    return {"persona_eliminada": False, "persona_id": persona_id}
