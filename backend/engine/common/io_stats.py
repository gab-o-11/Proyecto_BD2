import threading

_local = threading.local()


class IOCounter:
    def __init__(self):
        self.accesos = 0
        self.paginas = set()

    def leidas(self):
        return len(self.paginas)

    def aciertos(self):
        return self.accesos - len(self.paginas)


def _activos():
    pila = getattr(_local, "pila", None)
    if pila is None:
        pila = []
        _local.pila = pila
    return pila


def touch(archivo, pagina):
    for contador in _activos():
        contador.accesos += 1
        contador.paginas.add((archivo, pagina))


def activar(contador):
    _activos().append(contador)


def desactivar(contador):
    pila = _activos()
    for i in range(len(pila) - 1, -1, -1):
        if pila[i] is contador:
            del pila[i]
            return
