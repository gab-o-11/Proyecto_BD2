"""Índice R-Tree 2D de puntos, con split cuadrático y búsquedas espaciales."""

import heapq
import math
from dataclasses import dataclass, field

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


class RTree:
    def __init__(self, max_entries=16):
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 2:
            raise ValueError("max_entries debe ser un entero mayor o igual a 2")
        self.max_entries = max_entries
        self.min_entries = max(1, max_entries // 2)
        self.root = _Node()
        self._size = 0
        self._ordinal = 0
        self._invalid_geo = 0

    def __len__(self):
        return self._size

    @property
    def height(self):
        node, height = self.root, 1
        while not node.leaf:
            node = node.children[0]
            height += 1
        return height

    @staticmethod
    def _geographic(coordinates):
        return -90 <= coordinates[0] <= 90 and -180 <= coordinates[1] <= 180

    def insert(self, coordinates, payload):
        coordinates = point(coordinates)
        hash(payload)
        entry = _Entry(coordinates, payload, self._ordinal)
        self._insert_entry(entry)
        self._ordinal += 1
        self._size += 1
        self._invalid_geo += not self._geographic(coordinates)

    def _insert_entry(self, entry):
        sibling = self._insert(self.root, entry)
        if sibling is not None:
            self.root = _Node(False, [self.root, sibling])
            self.root.refresh()

    def _insert(self, node, entry):
        if node.leaf:
            node.children.append(entry)
        else:
            child = min(node.children, key=lambda c: (
                _area(_union(c.bounds, entry.bounds)) - _area(c.bounds),
                _area(c.bounds), len(c.children)))
            sibling = self._insert(child, entry)
            if sibling is not None:
                node.children.append(sibling)
        node.refresh()
        return self._split(node) if len(node.children) > self.max_entries else None

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

    @staticmethod
    def _entries(node):
        if node.leaf:
            yield from node.children
        else:
            for child in node.children:
                yield from RTree._entries(child)

    def delete(self, coordinates, payload):
        coordinates = point(coordinates)
        orphaned = []
        def remove(node):
            if node.leaf:
                for i, entry in enumerate(node.children):
                    if entry.coordinates == coordinates and entry.payload == payload:
                        del node.children[i]
                        node.refresh()
                        return True
            else:
                for child in list(node.children):
                    if _intersects(child.bounds, coordinates + coordinates) and remove(child):
                        if len(child.children) < self.min_entries:
                            node.children.remove(child)
                            orphaned.extend(self._entries(child))
                        node.refresh()
                        return True
            return False
        if not remove(self.root):
            return False
        while not self.root.leaf and len(self.root.children) == 1:
            self.root = self.root.children[0]
        if not self.root.children:
            self.root = _Node()
        for entry in orphaned:
            self._insert_entry(entry)
        self._size -= 1
        self._invalid_geo -= not self._geographic(coordinates)
        return True

    def _search(self, bounds):
        pending = [self.root]
        while pending:
            node = pending.pop()
            if node.bounds is None or not _intersects(node.bounds, bounds):
                continue
            for child in node.children:
                if _intersects(child.bounds, bounds):
                    if node.leaf:
                        yield child
                    else:
                        pending.append(child)

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

    def knn(self, center, k, metric="haversine"):
        center = self._query(center, metric)
        if isinstance(k, bool) or not isinstance(k, int) or k < 0:
            raise ValueError("k debe ser un entero no negativo")
        if k == 0 or self.root.bounds is None:
            return []
        pending = [(self._lower_bound(center, self.root.bounds, metric), 0, self.root)]
        serial, best = 0, []
        while pending:
            lower, _, node = heapq.heappop(pending)
            if len(best) == k and lower > -best[0][0]:
                break
            for child in node.children:
                if node.leaf:
                    actual = distance(center, child.coordinates, metric)
                    candidate = (-actual, -child.ordinal, child)
                    if len(best) < k:
                        heapq.heappush(best, candidate)
                    elif (actual, child.ordinal) < (-best[0][0], -best[0][1]):
                        heapq.heapreplace(best, candidate)
                else:
                    bound = self._lower_bound(center, child.bounds, metric)
                    if len(best) < k or bound <= -best[0][0]:
                        serial += 1
                        heapq.heappush(pending, (bound, serial, child))
        return [entry.payload for _, _, entry in sorted(best, key=lambda item: (-item[0], -item[1]))]

    def knn_iter(self, center, metric="haversine"):
        center = self._query(center, metric)
        if self.root.bounds is None:
            return
        pending = [(self._lower_bound(center, self.root.bounds, metric), 0, 0, self.root)]
        serial = 0
        while pending:
            _, tipo, _, item = heapq.heappop(pending)
            if tipo == 1:
                yield item.payload
                continue
            for child in item.children:
                if item.leaf:
                    heapq.heappush(pending, (distance(center, child.coordinates, metric), 1, child.ordinal, child))
                else:
                    serial += 1
                    heapq.heappush(pending, (self._lower_bound(center, child.bounds, metric), 0, serial, child))

    def search_polygon(self, vertices):
        vertices = validate_polygon(vertices)
        xs, ys = zip(*vertices)
        entries = self._search((min(xs), min(ys), max(xs), max(ys)))
        return [entry.payload for entry in sorted(entries, key=lambda e: e.ordinal)
                if contains_point(vertices, entry.coordinates)]
