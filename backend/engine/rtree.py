"""Índice R-Tree 2D de puntos, con split cuadrático y búsquedas espaciales."""

import heapq
import math
import os
import struct
from dataclasses import dataclass, field

from engine.hashing.page import FileManager
from engine.spatial import EARTH_RADIUS_METERS, distance, point


def _union(left, right):
    return (min(left[0], right[0]), min(left[1], right[1]),
            max(left[2], right[2]), max(left[3], right[3]))


def _area(bounds):
    return (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])


def _intersects(left, right):
    return (left[0] <= right[2] and left[2] >= right[0]
            and left[1] <= right[3] and left[3] >= right[1])


def _bounds(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("el MBR requiere cuatro coordenadas")
    low, high = point(value[:2]), point(value[2:])
    if low[0] > high[0] or low[1] > high[1]:
        raise ValueError("los mínimos del MBR no pueden superar los máximos")
    return low + high


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, c):
    return (_orientation(a, b, c) == 0
            and min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))


def _crosses(a, b, c, d):
    orientations = (_orientation(a, b, c), _orientation(a, b, d),
                    _orientation(c, d, a), _orientation(c, d, b))
    opposite = lambda x, y: (x < 0 < y) or (y < 0 < x)
    return ((opposite(*orientations[:2]) and opposite(*orientations[2:]))
            or any(_on_segment(*segment) for segment in ((a, b, c), (a, b, d), (c, d, a), (c, d, b))))


def validate_polygon(vertices):
    vertices = tuple(point(vertex) for vertex in vertices)
    if len(vertices) > 1 and vertices[0] == vertices[-1]:
        vertices = vertices[:-1]
    if len(vertices) < 3:
        raise ValueError("el polígono requiere al menos tres vértices")
    origin = vertices[0]
    area = sum((a[0] - origin[0]) * (b[1] - origin[1])
               - (b[0] - origin[0]) * (a[1] - origin[1])
               for a, b in zip(vertices, vertices[1:] + vertices[:1]))
    if not math.isfinite(area) or area == 0:
        raise ValueError("el polígono debe tener área distinta de cero")
    if len(set(vertices)) != len(vertices):
        raise ValueError("el polígono no puede repetir vértices")
    edges = list(zip(vertices, vertices[1:] + vertices[:1]))
    for i, (a, b) in enumerate(edges):
        for j in range(i + 2, len(edges)):
            if i == 0 and j == len(edges) - 1:
                continue
            if _crosses(a, b, *edges[j]):
                raise ValueError("el polígono debe ser simple, sin cruces entre aristas")
    return vertices


def contains_point(vertices, coordinates):
    """Ray casting para un polígono plano simple; incluye sus bordes."""
    x, y = point(coordinates)
    inside = False
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        if _on_segment(a, b, (x, y)):
            return True
        if (a[1] > y) != (b[1] > y):
            if x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
                inside = not inside
    return inside


@dataclass
class _Entry:
    coordinates: tuple
    payload: object
    ordinal: int

    @property
    def bounds(self):
        return self.coordinates + self.coordinates


@dataclass
class _Node:
    leaf: bool = True
    children: list = field(default_factory=list)
    bounds: tuple = None

    def refresh(self):
        self.bounds = None
        for child in self.children:
            self.bounds = child.bounds if self.bounds is None else _union(self.bounds, child.bounds)


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


class RTree:
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

    def knn_iter(self, center, metric="haversine"):
        center = self._query(center, metric)
        raiz = self._leer(self.root_id)
        if raiz.bounds is None:
            return
        pendientes = [(self._lower_bound(center, raiz.bounds, metric), 0, 0, self.root_id)]
        serial = 0
        while pendientes:
            _, tipo, _, item = heapq.heappop(pendientes)
            if tipo == 1:
                yield item.payload
                continue
            nodo = self._leer(item)
            for hijo in nodo.children:
                if nodo.leaf:
                    heapq.heappush(pendientes, (distance(center, hijo.coordinates, metric), 1, hijo.ordinal, hijo))
                else:
                    serial += 1
                    heapq.heappush(pendientes, (self._lower_bound(center, hijo.bounds, metric), 0, serial, hijo.pid))

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

    def __len__(self):
        return self._size

    @staticmethod
    def _geographic(coordinates):
        return -90 <= coordinates[0] <= 90 and -180 <= coordinates[1] <= 180

    def _split(self, node):
        children = node.children
        first, second = max(((i, j) for i in range(len(children))
                             for j in range(i + 1, len(children))),
                            key=lambda ij: _area(_union(children[ij[0]].bounds, children[ij[1]].bounds))
                            - _area(children[ij[0]].bounds) - _area(children[ij[1]].bounds))
        sibling = _Node(node.leaf, [children[second]])
        pending = [child for i, child in enumerate(children) if i not in (first, second)]
        node.children = [children[first]]
        node.refresh()
        sibling.refresh()
        while pending:
            if len(node.children) + len(pending) == self.min_entries:
                node.children.extend(pending)
                break
            if len(sibling.children) + len(pending) == self.min_entries:
                sibling.children.extend(pending)
                break
            def enlargement(target, child):
                return _area(_union(target.bounds, child.bounds)) - _area(target.bounds)
            selected = max(range(len(pending)), key=lambda i: abs(
                enlargement(node, pending[i]) - enlargement(sibling, pending[i])))
            child = pending.pop(selected)
            target = min((node, sibling), key=lambda n: (
                enlargement(n, child), _area(n.bounds), len(n.children)))
            target.children.append(child)
            target.refresh()
        node.refresh()
        sibling.refresh()
        return sibling

    def search(self, bounds):
        return [entry.payload for entry in sorted(self._search(_bounds(bounds)), key=lambda e: e.ordinal)]

    def _query(self, center, metric):
        center = point(center)
        distance(center, center, metric)
        if metric == "haversine" and self._invalid_geo:
            raise ValueError("Haversine requiere puntos geográficos válidos en el índice")
        return center

    def search_radius(self, center, radius, metric="haversine", inclusive=True):
        center = self._query(center, metric)
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius < 0:
            raise ValueError("el radio debe ser un número finito no negativo")
        x, y = center
        if metric == "euclidean":
            boxes = [(x - radius, y - radius, x + radius, y + radius)]
        else:
            angular = min(math.pi, radius / EARTH_RADIUS_METERS)
            latitude = math.degrees(angular)
            low, high = max(-90, x - latitude), min(90, x + latitude)
            if low <= -90 or high >= 90:
                boxes = [(low, -180, high, 180)]
            else:
                longitude = math.degrees(math.asin(min(1, math.sin(angular) / math.cos(math.radians(x)))))
                left, right = y - longitude, y + longitude
                if left < -180:
                    boxes = [(low, -180, high, right), (low, left + 360, high, 180)]
                elif right > 180:
                    boxes = [(low, left, high, 180), (low, -180, high, right - 360)]
                else:
                    boxes = [(low, left, high, right)]
                # ±180 describe la misma longitud, incluso con radio cero.
                if left == -180:
                    boxes.append((low, 180, high, 180))
                if right == 180:
                    boxes.append((low, -180, high, -180))
        candidates = {}
        for bounds in boxes:
            # Protege el envolvente geográfico del redondeo trigonométrico.
            padding = 1e-10 if metric == "haversine" else 0
            padded = (math.nextafter(bounds[0] - padding, -math.inf), math.nextafter(bounds[1] - padding, -math.inf),
                      math.nextafter(bounds[2] + padding, math.inf), math.nextafter(bounds[3] + padding, math.inf))
            for entry in self._search(padded):
                candidates[entry.ordinal] = entry
        result = []
        for entry in sorted(candidates.values(), key=lambda e: e.ordinal):
            actual = distance(center, entry.coordinates, metric)
            if (actual <= radius if inclusive else actual < radius):
                result.append(entry.payload)
        return result

    @staticmethod
    def _lower_bound(center, bounds, metric):
        x, y = center
        if metric == "euclidean":
            return math.hypot(max(bounds[0] - x, 0, x - bounds[2]),
                              max(bounds[1] - y, 0, y - bounds[3]))
        # Máximo producto escalar sobre el MBR esférico, respetando ±180.
        longitude_gap = min(abs(y - min(max(y, bounds[1]), bounds[3])),
                            abs(y + 360 - min(max(y + 360, bounds[1]), bounds[3])),
                            abs(y - 360 - min(max(y - 360, bounds[1]), bounds[3])))
        phi, low, high = map(math.radians, (x, bounds[0], bounds[2]))
        a, b = math.sin(phi), math.cos(phi) * math.cos(math.radians(longitude_gap))
        candidates = [low, high]
        optimum = math.atan2(a, b)
        if low <= optimum <= high:
            candidates.append(optimum)
        dot = max(a * math.sin(lat) + b * math.cos(lat) for lat in candidates)
        # Margen de redondeo conserva la cota inferior cerca de distancia cero.
        return EARTH_RADIUS_METERS * math.acos(min(1, max(-1, dot + 1e-14)))

    def search_polygon(self, vertices):
        vertices = validate_polygon(vertices)
        xs, ys = zip(*vertices)
        entries = self._search((min(xs), min(ys), max(xs), max(ys)))
        return [entry.payload for entry in sorted(entries, key=lambda e: e.ordinal)
                if contains_point(vertices, entry.coordinates)]

    def describir_nodo(self, pid=None, profundidad=0):
        if pid is None:
            pid = self.root_id
        nodo = self._leer(pid)
        salida = {"pagina": pid, "hoja": nodo.leaf, "mbr": None if nodo.bounds is None else list(nodo.bounds)}
        if nodo.leaf:
            salida["puntos"] = [{"coordenadas": list(e.coordinates),
                                 "rid": list(e.payload) if isinstance(e.payload, tuple) else e.payload}
                                for e in nodo.children]
            return salida
        salida["hijos"] = [{"pagina": ref.pid, "mbr": list(ref.bounds), "entradas": ref.count} for ref in nodo.children]
        if profundidad > 0:
            salida["nodos"] = [self.describir_nodo(ref.pid, profundidad - 1) for ref in nodo.children]
        return salida

    def rectangulos(self, niveles, limite):
        salida = []
        actual = [self.root_id]
        for nivel in range(niveles):
            siguiente = []
            for pid in actual:
                nodo = self._leer(pid)
                if nodo.bounds is None:
                    continue
                salida.append({"nivel": nivel, "pagina": pid, "hoja": nodo.leaf, "mbr": list(nodo.bounds)})
                if len(salida) >= limite:
                    return salida
                if not nodo.leaf:
                    siguiente.extend(ref.pid for ref in nodo.children)
            if not siguiente:
                break
            actual = siguiente
        return salida

    def bytes_en_disco(self):
        return os.path.getsize(self.nodes_path) + os.path.getsize(self.meta_path)

    def close(self):
        self.paginas.close()
