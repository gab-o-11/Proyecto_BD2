import time

import numpy as np
import redis

from config import N_FRECUENTES, URL_REDIS

CLAVE_FRECUENCIA = "rostros:frecuencia"
PREFIJO_PERSONA = "rostros:persona:"
ESPERA_REINTENTO = 10


class Cache:
    def __init__(self, cliente=None, n=N_FRECUENTES):
        if cliente is None:
            cliente = redis.Redis.from_url(URL_REDIS, socket_timeout=0.5, socket_connect_timeout=0.5)
        self.cliente = cliente
        self.n = n
        self.reintentar_desde = 0.0

    def estado(self):
        if time.monotonic() < self.reintentar_desde:
            return "no disponible"
        try:
            self.cliente.ping()
        except redis.RedisError:
            self.reintentar_desde = time.monotonic() + ESPERA_REINTENTO
            return "no disponible"
        return "activa"

    def frecuentes(self):
        ids = self.cliente.zrevrange(CLAVE_FRECUENCIA, 0, self.n - 1)
        canal = self.cliente.pipeline()
        for identificador in ids:
            canal.hgetall(PREFIJO_PERSONA + identificador.decode())
        candidatos = []
        for identificador, datos in zip(ids, canal.execute()):
            if b"suma" not in datos:
                continue
            suma = np.frombuffer(datos[b"suma"], dtype=np.float32)
            candidatos.append({
                "persona_id": int(identificador),
                "nombre": datos[b"nombre"].decode(),
                "foto": datos[b"foto"].decode(),
                "vector": suma / max(float(np.linalg.norm(suma)), 1e-12),
            })
        return candidatos

    def buscar(self, vector, umbral):
        try:
            candidatos = self.frecuentes()
        except redis.RedisError:
            return None
        if not candidatos:
            return None
        matriz = []
        for candidato in candidatos:
            matriz.append(candidato["vector"])
        similitudes = np.stack(matriz) @ np.asarray(vector, dtype=np.float32)
        mejor = int(np.argmax(similitudes))
        if similitudes[mejor] < umbral:
            return None
        elegido = candidatos[mejor]
        return {
            "persona_id": elegido["persona_id"],
            "nombre": elegido["nombre"],
            "foto": elegido["foto"],
            "similitud": float(similitudes[mejor]),
        }

    def registrar(self, persona_id, nombre, foto, vector):
        clave = PREFIJO_PERSONA + str(persona_id)
        try:
            self.cliente.zincrby(CLAVE_FRECUENCIA, 1, str(persona_id))
            suma = np.asarray(vector, dtype=np.float32).copy()
            anterior = self.cliente.hget(clave, "suma")
            if anterior is not None:
                suma += np.frombuffer(anterior, dtype=np.float32)
            self.cliente.hset(clave, mapping={"nombre": nombre, "foto": foto, "suma": suma.tobytes()})
            fuera = self.cliente.zrevrange(CLAVE_FRECUENCIA, self.n, -1)
            if fuera:
                claves = []
                for identificador in fuera:
                    claves.append(PREFIJO_PERSONA + identificador.decode())
                self.cliente.delete(*claves)
        except redis.RedisError:
            pass

    def quitar(self, persona_id):
        try:
            self.cliente.zrem(CLAVE_FRECUENCIA, str(persona_id))
            self.cliente.delete(PREFIJO_PERSONA + str(persona_id))
        except redis.RedisError:
            pass

    def limpiar(self):
        try:
            claves = list(self.cliente.scan_iter(PREFIJO_PERSONA + "*"))
            claves.append(CLAVE_FRECUENCIA)
            self.cliente.delete(*claves)
        except redis.RedisError:
            pass
