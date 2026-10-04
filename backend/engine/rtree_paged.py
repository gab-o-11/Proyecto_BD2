import heapq
import math
import os
import struct
from dataclasses import dataclass

from engine.hashing.page import FileManager
from engine.rtree import RTree, _Entry, _Node, _intersects
from engine.spatial import distance, point

HEADER_FORMAT = "<ii"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
ENTRY_FORMAT = "<ddqbqq"
ENTRY_SIZE = struct.calcsize(ENTRY_FORMAT)
REF_FORMAT = "<ddddii"
REF_SIZE = struct.calcsize(REF_FORMAT)
META_FORMAT = "<iiqqqi"
META_SIZE = struct.calcsize(META_FORMAT)

PAYLOAD_INT = 1
PAYLOAD_PAR = 2


@dataclass
class _Ref:
    bounds: tuple
    pid: int
    count: int


def _codificar(payload):
    if isinstance(payload, bool):
        raise ValueError("el payload del R-Tree en disco debe ser un entero o un par de enteros")
    if isinstance(payload, int):
        return PAYLOAD_INT, payload, 0
    if isinstance(payload, (tuple, list)) and len(payload) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in payload):
        return PAYLOAD_PAR, payload[0], payload[1]
    raise ValueError("el payload del R-Tree en disco debe ser un entero o un par de enteros")


def _decodificar(tipo, a, b):
    if tipo == PAYLOAD_INT:
        return a
    return (a, b)


def _centro(item):
    bounds = item.bounds
    return ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)


class PagedRTree(RTree):
    def __init__(self, path, max_entries=16):
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 2:
            raise ValueError("max_entries debe ser un entero mayor o igual a 2")
        self.path = path
        self.meta_path = path + ".meta"
        self.nodes_path = path + ".nodes"
        self.nuevo = not os.path.exists(self.meta_path)
        if self.nuevo:
            self.max_entries = max_entries
            self._reiniciar_contadores()
        else:
            self._cargar_meta()
        self.min_entries = max(1, self.max_entries // 2)
        self.page_size = HEADER_SIZE + self.max_entries * max(ENTRY_SIZE, REF_SIZE)
        if self.nuevo and os.path.exists(self.nodes_path):
            os.remove(self.nodes_path)
        self.paginas = FileManager(self.nodes_path, self.page_size)
        if self.nuevo:
            self.root_id = self._nueva(_Node(True, []))
            self._guardar_meta()

    def _reiniciar_contadores(self):
        self.root_id = 0
        self._height = 1
        self._size = 0
        self._ordinal = 0
        self._invalid_geo = 0

    def _cargar_meta(self):
        with open(self.meta_path, "rb") as f:
            datos = struct.unpack(META_FORMAT, f.read(META_SIZE))
        self.root_id, self._height, self._size, self._ordinal, self._invalid_geo, self.max_entries = datos

    def _guardar_meta(self):
        with open(self.meta_path, "wb") as f:
            f.write(struct.pack(META_FORMAT, self.root_id, self._height, self._size,
                                self._ordinal, self._invalid_geo, self.max_entries))

    @property
    def height(self):
        return self._height

    def _empaquetar(self, nodo):
        salida = struct.pack(HEADER_FORMAT, 1 if nodo.leaf else 0, len(nodo.children))
        for hijo in nodo.children:
            if nodo.leaf:
                tipo, a, b = _codificar(hijo.payload)
                salida += struct.pack(ENTRY_FORMAT, hijo.coordinates[0], hijo.coordinates[1], hijo.ordinal, tipo, a, b)
            else:
                salida += struct.pack(REF_FORMAT, *hijo.bounds, hijo.pid, hijo.count)
        return salida.ljust(self.page_size, b"\x00")

    def _desempaquetar(self, crudo):
        hoja, cantidad = struct.unpack_from(HEADER_FORMAT, crudo, 0)
        hijos = []
        posicion = HEADER_SIZE
        for _ in range(cantidad):
            if hoja:
                lat, lon, ordinal, tipo, a, b = struct.unpack_from(ENTRY_FORMAT, crudo, posicion)
                hijos.append(_Entry((lat, lon), _decodificar(tipo, a, b), ordinal))
                posicion += ENTRY_SIZE
            else:
                b0, b1, b2, b3, pid, conteo = struct.unpack_from(REF_FORMAT, crudo, posicion)
                hijos.append(_Ref((b0, b1, b2, b3), pid, conteo))
                posicion += REF_SIZE
        nodo = _Node(bool(hoja), hijos)
        nodo.refresh()
        return nodo

    def _leer(self, pid):
        return self._desempaquetar(self.paginas.read_raw(pid))

    def _escribir(self, pid, nodo):
        self.paginas.write_raw(pid, self._empaquetar(nodo))

    def _nueva(self, nodo):
        return self.paginas.append_raw(self._empaquetar(nodo))

    def insert(self, coordinates, payload):
        coordinates = point(coordinates)
        _codificar(payload)
        entrada = _Entry(coordinates, payload, self._ordinal)
        self._insert_entry(entrada)
        self._ordinal += 1
        self._size += 1
        self._invalid_geo += not self._geographic(coordinates)
        self._guardar_meta()

    def _insert_entry(self, entry):
        propia, hermano = self._insertar(self.root_id, entry)
        if hermano is not None:
            raiz = _Node(False, [propia, hermano])
            raiz.refresh()
            self.root_id = self._nueva(raiz)
            self._height += 1

    def _insertar(self, pid, entry):
        nodo = self._leer(pid)
        if nodo.leaf:
            nodo.children.append(entry)
        else:
            hijos = nodo.children
            i = min(range(len(hijos)), key=lambda j: (
                self._ampliacion(hijos[j], entry), self._area_de(hijos[j]), hijos[j].count))
            propia, hermano = self._insertar(hijos[i].pid, entry)
            hijos[i] = propia
            if hermano is not None:
                hijos.append(hermano)
        nodo.refresh()
        if len(nodo.children) > self.max_entries:
            otro = self._split(nodo)
            otro_id = self._nueva(otro)
            self._escribir(pid, nodo)
            return _Ref(nodo.bounds, pid, len(nodo.children)), _Ref(otro.bounds, otro_id, len(otro.children))
        self._escribir(pid, nodo)
        return _Ref(nodo.bounds, pid, len(nodo.children)), None

    @staticmethod
    def _area_de(item):
        b = item.bounds
        return (b[2] - b[0]) * (b[3] - b[1])

    @staticmethod
    def _ampliacion(item, entry):
        b, e = item.bounds, entry.bounds
        union = (min(b[0], e[0]), min(b[1], e[1]), max(b[2], e[2]), max(b[3], e[3]))
        return (union[2] - union[0]) * (union[3] - union[1]) - (b[2] - b[0]) * (b[3] - b[1])

    def _entradas(self, pid):
        nodo = self._leer(pid)
        if nodo.leaf:
            yield from nodo.children
        else:
            for ref in nodo.children:
                yield from self._entradas(ref.pid)

    def _entradas_de(self, nodo):
        if nodo.leaf:
            yield from nodo.children
        else:
            for ref in nodo.children:
                yield from self._entradas(ref.pid)

    def delete(self, coordinates, payload):
        coordinates = point(coordinates)
        huerfanos = []
        encontrado, _ = self._quitar(self.root_id, coordinates, payload, huerfanos)
        if not encontrado:
            return False
        raiz = self._leer(self.root_id)
        while not raiz.leaf and len(raiz.children) == 1:
            self.root_id = raiz.children[0].pid
            self._height -= 1
            raiz = self._leer(self.root_id)
        if not raiz.children and not raiz.leaf:
            self.root_id = self._nueva(_Node(True, []))
            self._height = 1
        for entrada in huerfanos:
            self._insert_entry(entrada)
        self._size -= 1
        self._invalid_geo -= not self._geographic(coordinates)
        self._guardar_meta()
        return True

    def _quitar(self, pid, coordinates, payload, huerfanos):
        nodo = self._leer(pid)
        if nodo.leaf:
            for i, entrada in enumerate(nodo.children):
                if entrada.coordinates == coordinates and entrada.payload == payload:
                    del nodo.children[i]
                    nodo.refresh()
                    self._escribir(pid, nodo)
                    return True, nodo
            return False, None
        for i, ref in enumerate(nodo.children):
            if not _intersects(ref.bounds, coordinates + coordinates):
                continue
            encontrado, hijo = self._quitar(ref.pid, coordinates, payload, huerfanos)
            if not encontrado:
                continue
            if len(hijo.children) < self.min_entries:
                del nodo.children[i]
                huerfanos.extend(self._entradas_de(hijo))
            else:
                nodo.children[i] = _Ref(hijo.bounds, ref.pid, len(hijo.children))
            nodo.refresh()
            self._escribir(pid, nodo)
            return True, nodo
        return False, None

    def _search(self, bounds):
        pendientes = [self.root_id]
        while pendientes:
            nodo = self._leer(pendientes.pop())
            if nodo.bounds is None or not _intersects(nodo.bounds, bounds):
                continue
            for hijo in nodo.children:
                if _intersects(hijo.bounds, bounds):
                    if nodo.leaf:
                        yield hijo
                    else:
                        pendientes.append(hijo.pid)

    def knn(self, center, k, metric="haversine"):
        center = self._query(center, metric)
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            raise ValueError("k debe ser un entero no negativo")
        raiz = self._leer(self.root_id)
        if k == 0 or raiz.bounds is None:
            return []
        pendientes = [(self._lower_bound(center, raiz.bounds, metric), 0, self.root_id)]
        serial, mejores = 0, []
        while pendientes:
            cota, _, pid = heapq.heappop(pendientes)
            if len(mejores) == k and cota > -mejores[0][0]:
                break
            nodo = self._leer(pid)
            for hijo in nodo.children:
                if nodo.leaf:
                    actual = distance(center, hijo.coordinates, metric)
                    candidato = (-actual, -hijo.ordinal, hijo)
                    if len(mejores) < k:
                        heapq.heappush(mejores, candidato)
                    elif (actual, hijo.ordinal) < (-mejores[0][0], -mejores[0][1]):
                        heapq.heapreplace(mejores, candidato)
                else:
                    cota_hijo = self._lower_bound(center, hijo.bounds, metric)
                    if len(mejores) < k or cota_hijo <= -mejores[0][0]:
                        serial += 1
                        heapq.heappush(pendientes, (cota_hijo, serial, hijo.pid))
        return [entrada.payload for _, _, entrada in sorted(mejores, key=lambda item: (-item[0], -item[1]))]

    def recrear(self):
        self.paginas.close()
        for ruta in (self.meta_path, self.nodes_path):
            if os.path.exists(ruta):
                os.remove(ruta)
        self._reiniciar_contadores()
        self.paginas = FileManager(self.nodes_path, self.page_size)
        self.nuevo = True

    def bulk_load(self, items):
        self.recrear()
        nivel = []
        for coordinates, payload in items:
            coordinates = point(coordinates)
            _codificar(payload)
            nivel.append(_Entry(coordinates, payload, self._ordinal))
            self._ordinal += 1
            self._invalid_geo += not self._geographic(coordinates)
        self._size = len(nivel)
        if not nivel:
            self.root_id = self._nueva(_Node(True, []))
            self._guardar_meta()
            return
        hoja = True
        while True:
            refs = []
            for grupo in self._str(nivel):
                nodo = _Node(hoja, grupo)
                nodo.refresh()
                refs.append(_Ref(nodo.bounds, self._nueva(nodo), len(grupo)))
            if len(refs) == 1:
                self.root_id = refs[0].pid
                break
            nivel = refs
            hoja = False
            self._height += 1
        self._guardar_meta()

    def _str(self, items):
        capacidad = self.max_entries
        hojas = math.ceil(len(items) / capacidad)
        franjas = math.ceil(math.sqrt(hojas))
        por_franja = franjas * capacidad
        ordenados = sorted(items, key=lambda item: _centro(item)[0])
        grupos = []
        for inicio in range(0, len(ordenados), por_franja):
            franja = sorted(ordenados[inicio:inicio + por_franja], key=lambda item: _centro(item)[1])
            for desde in range(0, len(franja), capacidad):
                grupos.append(franja[desde:desde + capacidad])
        return grupos

    def bytes_en_disco(self):
        return os.path.getsize(self.nodes_path) + os.path.getsize(self.meta_path)

    def close(self):
        self.paginas.close()
