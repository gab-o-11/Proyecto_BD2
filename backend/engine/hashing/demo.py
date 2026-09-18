import os
import tempfile

from engine.hashing import ExtendibleHashIndex, external_group_by, grace_hash_join


def demo_index():
    path = os.path.join(tempfile.gettempdir(), "demo_hash")
    for suffix in (".dir", ".buk"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)

    idx = ExtendibleHashIndex(path, key_type="int", block_factor=3)
    claves = [10, 13, 34, 6, 23, 12, 15, 73, 28, 19, 67, 17, 41, 87, 57, 27, 11]
    for i, k in enumerate(claves):
        idx.insert(k, (i, 0))

    print("stats:", idx.stats())
    print("search(23):", idx.search(23))
    print("search(999):", idx.search(999))

    idx.insert(23, (99, 1))
    print("search(23) con duplicado:", idx.search(23))

    idx.delete(10)
    print("search(10) tras delete:", idx.search(10))
    idx.close()

    reopened = ExtendibleHashIndex.open(path)
    print("persistencia search(73):", reopened.search(73))
    print("persistencia global_depth:", reopened.stats()["global_depth"])
    reopened.close()


def _first(row):
    return row[0]


def _second(row):
    return row[1]


def _pedido_id(pair):
    pedido = pair[1]
    return pedido[0]


def demo_group_by():
    ventas = [
        ("ana", 100), ("beto", 50), ("ana", 200), ("caro", 75),
        ("beto", 25), ("ana", 10), ("caro", 300), ("dora", 40),
    ]
    specs = [("count", None), ("sum", _second), ("max", _second)]
    result = sorted(external_group_by(ventas, key_fn=_first, specs=specs, mem_budget=2))
    print("group_by (mem_budget=2, fuerza spill):")
    for grupo, aggs in result:
        print("  ", grupo, "-> count,sum,max =", aggs)


def demo_join():
    clientes = [(1, "ana"), (2, "beto"), (3, "caro")]
    pedidos = [(10, 1), (11, 1), (12, 2), (13, 99)]
    joined = sorted(
        grace_hash_join(clientes, pedidos, left_key=_first, right_key=_second, mem_budget=1),
        key=_pedido_id,
    )
    print("grace_hash_join (mem_budget=1, fuerza spill/recursion):")
    for cliente, pedido in joined:
        print("  ", "pedido", pedido[0], "->", cliente[1])


if __name__ == "__main__":
    demo_index()
    print()
    demo_group_by()
    print()
    demo_join()
