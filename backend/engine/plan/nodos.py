import math
import operator
import time

from ..common import io_stats
from ..external import external_sort
from ..hashing import external_group_by

COMPARADORES = {
    "=": operator.eq, "!=": operator.ne,
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
}

PARTICIONES_HASH = 16

_FIN = object()


def literal(valor):
    if isinstance(valor, str):
        return "'" + valor + "'"
    return str(valor)


def condicion_texto(condicion):
    return condicion.column + " " + condicion.op + " " + literal(condicion.value)


def _grupo_unico(fila):
    return 0


class Instrumento:
    def __init__(self):
        self.inicio = None
        self.total = 0.0
        self.filas = 0
        self.loops = 1
        self.io = io_stats.IOCounter()


class Nodo:
    tipo = ""

    def __init__(self, hijos=None):
        self.hijos = hijos or []
        self.costo_inicio = 0.0
        self.costo_total = 0.0
        self.filas_est = 1
        self.ancho = 0
        self.real = None

    def estimar(self, inicio, total, filas, ancho):
        self.costo_inicio = inicio
        self.costo_total = total
        self.filas_est = filas
        self.ancho = ancho
        return self

    def titulo(self):
        return self.tipo

    def relacion(self):
        return None

    def indice(self):
        return None

    def detalles(self):
        return []

    def detalles_reales(self):
        return []

    def producir(self):
        raise NotImplementedError

    def paso(self):
        return None

    def filas_paso(self):
        if self.real is None:
            return 0
        return self.real.filas

    def iterar(self):
        instrumento = Instrumento()
        self.real = instrumento
        generador = self.producir()
        while True:
            io_stats.activar(instrumento.io)
            comienzo = time.perf_counter()
            try:
                fila = next(generador, _FIN)
            finally:
                instrumento.total += time.perf_counter() - comienzo
                io_stats.desactivar(instrumento.io)
            if fila is _FIN:
                break
            if instrumento.inicio is None:
                instrumento.inicio = instrumento.total
            instrumento.filas += 1
            yield fila
        if instrumento.inicio is None:
            instrumento.inicio = instrumento.total

    def traza(self):
        pasos = []
        for hijo in self.hijos:
            pasos.extend(hijo.traza())
        paso = self.paso()
        if paso is not None:
            paso["rows"] = self.filas_paso()
            pasos.append(paso)
        return pasos


def base_de(tabla):
    if getattr(tabla, "is_clustered", False):
        return "sequential"
    return "heap"


class SeqScan(Nodo):
    tipo = "Seq Scan"

    def __init__(self, tabla, condicion=None):
        super().__init__()
        self.tabla = tabla
        self.condicion = condicion
        self.removidas = 0

    def titulo(self):
        return "Seq Scan on " + self.tabla.name

    def relacion(self):
        return self.tabla.name

    def detalles(self):
        if self.condicion is None:
            return []
        return ["Filter: (" + condicion_texto(self.condicion) + ")"]

    def detalles_reales(self):
        if self.condicion is None:
            return []
        return ["Rows Removed by Filter: " + str(self.removidas)]

    def _fuente(self):
        if hasattr(self.tabla, "_iter_rows"):
            return self.tabla._iter_rows()
        return iter(self.tabla.scan())

    def producir(self):
        self.removidas = 0
        if self.condicion is None:
            yield from self._fuente()
            return
        columna = self.condicion.column
        valor = self.condicion.value
        comparar = COMPARADORES[self.condicion.op]
        for fila in self._fuente():
            if comparar(fila[columna], valor):
                yield fila
            else:
                self.removidas += 1

    def paso(self):
        if self.condicion is None:
            return {"op": "Sequential Scan", "method": base_de(self.tabla), "detail": self.tabla.name}
        return {"op": "Sequential Scan + Filter", "method": base_de(self.tabla), "detail": condicion_texto(self.condicion)}


class IndexScan(Nodo):
    tipo = "Index Scan"

    def __init__(self, tabla, condicion, rango):
        super().__init__()
        self.tabla = tabla
        self.condicion = condicion
        self.rango = rango

    def tipo_indice(self):
        return str(self.tabla.index_kind)

    def indice(self):
        return self.tabla.name + "_" + str(self.tabla.index_column) + "_" + self.tipo_indice().lower()

    def titulo(self):
        return "Index Scan using " + self.indice() + " on " + self.tabla.name

    def relacion(self):
        return self.tabla.name

    def detalles(self):
        return ["Index Cond: (" + condicion_texto(self.condicion) + ")"]

    def producir(self):
        if self.rango:
            filas = self.tabla.search_range(self.condicion.op, self.condicion.value)
            if filas is None:
                comparar = COMPARADORES[self.condicion.op]
                filas = [f for f in self.tabla.scan() if comparar(f[self.condicion.column], self.condicion.value)]
        else:
            filas = self.tabla.search(self.condicion.column, self.condicion.value)
        yield from filas

    def paso(self):
        metodo = self.tipo_indice() + "(" + str(self.tabla.index_column) + ")"
        op = "Index Search"
        if self.rango:
            op = "Range Search"
        return {"op": op, "method": metodo, "detail": condicion_texto(self.condicion)}


class Sort(Nodo):
    tipo = "Sort"

    def __init__(self, hijo, clave, memoria):
        super().__init__([hijo])
        self.clave = clave
        self.memoria = memoria

    def detalles(self):
        return ["Sort Key: " + self.clave]

    def detalles_reales(self):
        if self.real is None:
            return []
        runs = max(1, math.ceil(self.real.filas / self.memoria))
        return ["Sort Method: external k-way merge  Runs: " + str(runs) + "  Memory: " + str(self.memoria) + " rows"]

    def producir(self):
        yield from external_sort(self.hijos[0].iterar(), key_fn=operator.itemgetter(self.clave), mem_budget=self.memoria)

    def paso(self):
        return {"op": "Order By", "method": "external-merge", "detail": self.clave}


class Agregacion(Nodo):
    def __init__(self, hijo, agrupar, specs, nombres, memoria):
        super().__init__([hijo])
        self.agrupar = agrupar
        self.specs = specs
        self.nombres = nombres
        self.memoria = memoria
        self.tipo = "Aggregate"
        if agrupar is not None:
            self.tipo = "HashAggregate"

    def detalles(self):
        if self.agrupar is None:
            return []
        return ["Group Key: " + self.agrupar]

    def detalles_reales(self):
        if self.agrupar is None or self.real is None:
            return []
        if self.real.filas > self.memoria:
            return ["Batches: " + str(PARTICIONES_HASH) + "  Memory: " + str(self.memoria) + " groups  Disk: spilled"]
        return ["Batches: 1  Memory: " + str(self.real.filas) + " groups"]

    def producir(self):
        entrada = self.hijos[0].iterar()
        if self.agrupar is not None:
            clave_fn = operator.itemgetter(self.agrupar)
            for clave, valores in external_group_by(entrada, key_fn=clave_fn, specs=self.specs, mem_budget=self.memoria):
                fila = {self.agrupar: clave}
                for i in range(len(self.nombres)):
                    fila[self.nombres[i]] = valores[i]
                yield fila
            return
        fila = {}
        for clave, valores in external_group_by(entrada, key_fn=_grupo_unico, specs=self.specs, mem_budget=self.memoria):
            for i in range(len(self.nombres)):
                fila[self.nombres[i]] = valores[i]
        if not fila:
            for nombre in self.nombres:
                fila[nombre] = 0
        yield fila

    def paso(self):
        if self.agrupar is not None:
            return {"op": "Group By", "method": "external-hash", "detail": self.agrupar}
        return {"op": "Aggregate", "method": "external-hash", "detail": ",".join(self.nombres)}


class Resultado(Nodo):
    tipo = "Result"

    def __init__(self, fila):
        super().__init__()
        self.fila = fila

    def producir(self):
        yield self.fila


class Modificar(Nodo):
    def __init__(self, accion, tabla, hijo, aplicar, metodo, detalle):
        super().__init__([hijo])
        self.tipo = accion
        self.tabla = tabla
        self.aplicar = aplicar
        self.metodo = metodo
        self.detalle = detalle
        self.afectadas = 0

    def titulo(self):
        return self.tipo + " on " + self.tabla.name

    def relacion(self):
        return self.tabla.name

    def detalles_reales(self):
        return ["Rows Affected: " + str(self.afectadas)]

    def producir(self):
        filas = list(self.hijos[0].iterar())
        self.afectadas = self.aplicar(filas)
        registrar = getattr(self.tabla, "registrar_cambios", None)
        if registrar is not None:
            registrar(self.afectadas)
        return
        yield

    def filas_paso(self):
        return self.afectadas

    def paso(self):
        return {"op": self.tipo, "method": self.metodo, "detail": self.detalle}
