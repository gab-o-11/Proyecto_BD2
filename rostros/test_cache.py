import fakeredis
import numpy as np
import redis

from cache import Cache


def _unitario(*valores):
    vector = np.zeros(512, dtype=np.float32)
    vector[:len(valores)] = valores
    return vector / np.linalg.norm(vector)


def _nueva(n=20):
    cache = Cache(fakeredis.FakeRedis(), n=n)
    cache.limpiar()
    return cache


def _busqueda():
    cache = _nueva()
    assert cache.estado() == "activa"
    assert cache.buscar(_unitario(1), 0.5) is None
    cache.registrar(1, "Ana", "lfw/a.jpg", _unitario(1))
    encontrado = cache.buscar(_unitario(1), 0.5)
    assert encontrado["persona_id"] == 1 and encontrado["nombre"] == "Ana" and encontrado["foto"] == "lfw/a.jpg"
    assert abs(encontrado["similitud"] - 1.0) < 1e-5
    assert cache.buscar(_unitario(0, 1), 0.5) is None


def _promedio():
    cache = _nueva()
    cache.registrar(1, "Ana", "a", _unitario(1))
    cache.registrar(1, "Ana", "a", _unitario(0, 1))
    assert abs(cache.buscar(_unitario(1), 0.0)["similitud"] - np.sqrt(0.5)) < 1e-5


def _frecuentes():
    cache = _nueva(n=2)
    for _ in range(3):
        cache.registrar(1, "P1", "f", _unitario(1))
    for _ in range(2):
        cache.registrar(2, "P2", "f", _unitario(0, 1))
    cache.registrar(3, "P3", "f", _unitario(0, 0, 1))
    ids = []
    for candidato in cache.frecuentes():
        ids.append(candidato["persona_id"])
    assert sorted(ids) == [1, 2]
    assert cache.buscar(_unitario(0, 0, 1), 0.5) is None
    cache.quitar(1)
    assert cache.buscar(_unitario(1), 0.5) is None
    assert cache.buscar(_unitario(0, 1), 0.5)["persona_id"] == 2


def _redis_caido():
    cache = Cache(redis.Redis(host="localhost", port=1, socket_connect_timeout=0.2, socket_timeout=0.2))
    assert cache.estado() == "no disponible"
    assert cache.buscar(_unitario(1), 0.5) is None
    cache.registrar(1, "Ana", "a", _unitario(1))
    cache.quitar(1)
    cache.limpiar()


def main():
    _busqueda()
    _promedio()
    _frecuentes()
    _redis_caido()
    print("OK: búsqueda, promedio, personas frecuentes y Redis caído")


if __name__ == "__main__":
    main()
