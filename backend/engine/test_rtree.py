"""Regresiones del R-Tree: ejecutar python -m engine.test_rtree."""

import math
import os
import random
import tempfile

import engine.rtree as rtree_module
from engine.rtree import contains_point, validate_polygon
from engine.spatial import distance

_DIRECTORIO = tempfile.TemporaryDirectory(prefix="test_rtree_")
_CONTADOR = [0]


def _arbol(max_entries=16):
    _CONTADOR[0] += 1
    return rtree_module.RTree(os.path.join(_DIRECTORIO.name, "arbol%d" % _CONTADOR[0]), max_entries)


def _check_structure(tree):
    depths, ordinals = set(), []
    def visit(pid, depth, root=False):
        node = tree._leer(pid)
        assert len(node.children) <= tree.max_entries
        if not root:
            assert len(node.children) >= tree.min_entries
        if node.children:
            expected = (min(c.bounds[0] for c in node.children), min(c.bounds[1] for c in node.children),
                        max(c.bounds[2] for c in node.children), max(c.bounds[3] for c in node.children))
            assert node.bounds == expected
        else:
            assert root and node.leaf and node.bounds is None
        if node.leaf:
            depths.add(depth)
            ordinals.extend(e.ordinal for e in node.children)
        else:
            assert not root or len(node.children) >= 2
            for child in node.children:
                assert tree._leer(child.pid).bounds == child.bounds
                assert len(tree._leer(child.pid).children) == child.count
                visit(child.pid, depth + 1)
    visit(tree.root_id, 1, True)
    assert depths == {tree.height}
    assert len(ordinals) == len(tree) == len(set(ordinals))


def _random_queries():
    rng = random.Random(487)
    records = [((rng.uniform(-90, 90), rng.uniform(-180, 180)), i) for i in range(450)]
    for capacity in (2, 3, 4, 16):
        tree = _arbol(capacity)
        for coordinates, payload in records:
            tree.insert(coordinates, payload)
        _check_structure(tree)
        for _ in range(45):
            center = (rng.uniform(-90, 90), rng.uniform(-180, 180))
            for metric, radius in (("euclidean", rng.uniform(0, 100)),
                                   ("haversine", rng.uniform(0, 22_000_000))):
                expected = [rid for p, rid in records if distance(center, p, metric) <= radius]
                assert tree.search_radius(center, radius, metric) == expected
                for k in (0, 1, 8, 500):
                    expected = [rid for p, rid in sorted(records, key=lambda item: (distance(center, item[0], metric), item[1]))[:k]]
                    assert tree.knn(center, k, metric) == expected
            x1, x2 = sorted((rng.uniform(-90, 90), rng.uniform(-90, 90)))
            y1, y2 = sorted((rng.uniform(-180, 180), rng.uniform(-180, 180)))
            assert tree.search((x1, y1, x2, y2)) == [rid for (x, y), rid in records if x1 <= x <= x2 and y1 <= y <= y2]
        remaining = list(records)
        removed = rng.sample(records, 400)
        for coordinates, payload in removed:
            assert tree.delete(coordinates, payload)
            remaining.remove((coordinates, payload))
            _check_structure(tree)
        for coordinates, payload in removed:
            tree.insert(coordinates, payload)
            remaining.append((coordinates, payload))
        _check_structure(tree)
        assert tree.search((-90, -180, 90, 180)) == [rid for _, rid in remaining]
        for coordinates, payload in remaining:
            assert tree.delete(coordinates, payload)
            _check_structure(tree)
        assert len(tree) == 0 and tree.height == 1


def _edges_and_polygons():
    tree = _arbol(4)
    coordinates = [(0, 180), (0, -180), (90, 0), (90, 180), (-90, 30),
                   (0, 0), (0, 0), (0, 1), (0, -1), (1, 0)]
    for rid, p in enumerate(coordinates):
        tree.insert(p, rid)
    for center in ((0, 179.99), (0, -179.99), (90, -180), (-90, 180), (0, 0)):
        for radius in (0, 100, 2000, 100000, math.pi * 6_371_000):
            for inclusive in (True, False):
                expected = [i for i, p in enumerate(coordinates)
                            if (distance(center, p) <= radius if inclusive else distance(center, p) < radius)]
                assert tree.search_radius(center, radius, inclusive=inclusive) == expected
        assert tree.knn(center, 10) == sorted(range(10), key=lambda i: (distance(center, coordinates[i]), i))
    radius = distance((0, 0), (0, 1))
    assert 7 in tree.search_radius((0, 0), radius)
    assert 7 not in tree.search_radius((0, 0), radius, inclusive=False)
    assert tree.delete((0, 0), 5)
    assert not tree.delete((0, 0), 5)
    assert tree.knn((0, 0), 1, "euclidean") == [6]
    rng = random.Random(33)
    for _ in range(100):
        center = (rng.uniform(-90, 90), rng.uniform(-180, 180))
        rid = rng.choice([0, 1, 2, 3, 4, 6, 7, 8, 9])
        assert rid in tree.search_radius(center, distance(center, coordinates[rid]))
    duplicate = _arbol(2)
    for _ in range(9):
        duplicate.insert((1, 1), (5, 8))
    for count in range(9, 0, -1):
        assert len(duplicate.search((1, 1, 1, 1))) == count
        assert duplicate.delete((1, 1), (5, 8))
        _check_structure(duplicate)
    polygon = validate_polygon([(0, 0), (4, 0), (4, 4), (2, 2), (0, 4), (0, 0)])
    positions = [(0, 0), (2, 0), (2, 2), (2, 3), (1, 3), (3, 3), (4, 2), (5, 1), (1, 1)]
    indexed = _arbol(2)
    for rid, p in enumerate(positions):
        indexed.insert(p, rid)
    assert indexed.search_polygon(polygon) == [0, 1, 2, 4, 5, 6, 8]
    assert contains_point(polygon, (1, 3))
    assert not contains_point(polygon, (2, 3))


def _lower_bounds_and_pruning():
    rng = random.Random(808)
    for _ in range(3000):
        center = (rng.uniform(-90, 90), rng.uniform(-180, 180))
        xs = sorted((rng.uniform(-90, 90), rng.uniform(-90, 90)))
        ys = sorted((rng.uniform(-180, 180), rng.uniform(-180, 180)))
        bounds = (xs[0], ys[0], xs[1], ys[1])
        lower = rtree_module.RTree._lower_bound(center, bounds, "haversine")
        for p in ((xs[0], ys[0]), (xs[1], ys[1]), (rng.uniform(*xs), rng.uniform(*ys))):
            assert lower <= distance(center, p) + 1e-6
    tree = _arbol(4)
    for i in range(500):
        tree.insert((i * 10, i * 10), i)
    original = rtree_module.distance
    calls = 0
    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)
    rtree_module.distance = counted
    try:
        assert tree.knn((0, 0), 3, "euclidean") == [0, 1, 2]
        assert calls < 100, calls
    finally:
        rtree_module.distance = original


def _validation():
    tree = _arbol()
    checks = [lambda: _arbol(1), lambda: tree.insert((float("nan"), 0), 1),
              lambda: tree.search((1, 0, -1, 0)), lambda: tree.search_radius((0, 0), -1),
              lambda: tree.knn((0, 0), -1), lambda: tree.knn((0, 0), 1, "unknown"),
              lambda: validate_polygon([(0, 0), (1, 1), (2, 2)]),
              lambda: validate_polygon([(0, 0), (1, 1)]),
              lambda: validate_polygon([(0, 0), (3, 3), (0, 2), (2, 0)]),
              lambda: validate_polygon([(0, 0), (2, 0), (0, 0), (0, 2)])]
    for check in checks:
        try:
            check()
        except ValueError:
            pass
        else:
            raise AssertionError("se esperaba ValueError")
    tree.insert((100, 200), 1)
    assert tree.knn((100, 200), 1, "euclidean") == [1]
    try:
        tree.knn((0, 0), 1)
    except ValueError:
        pass
    else:
        raise AssertionError("se esperaba validación geográfica")
    assert tree.delete((100, 200), 1)
    assert tree.knn((0, 0), 1) == []


if __name__ == "__main__":
    _random_queries()
    _edges_and_polygons()
    _lower_bounds_and_pruning()
    _validation()
    print("R-Tree: inserción, split, borrado, radio, kNN y polígonos verificados")
