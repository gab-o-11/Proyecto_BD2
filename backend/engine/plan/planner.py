from . import costos
from .costos import Perfil, ajustar_filas
from .nodos import Agregacion, IndexScan, Modificar, Resultado, SeqScan, Sort

DESIGUALDADES = (">", ">=", "<", "<=")


def _soporta_rango(tabla):
    if not hasattr(tabla, "search_range"):
        return False
    if getattr(tabla, "key_kind", None) not in ("int", "float"):
        return False
    return str(tabla.index_kind) != "HASH"


def _tipo_indice(tabla):
    tipo = str(tabla.index_kind).upper()
    if tipo in ("HASH", "BPLUS", "BPLUS_CLUSTERED"):
        return tipo
    return "BPLUS"


def acceso(tabla, condicion):
    perfil = Perfil(tabla)
    if condicion is None:
        inicio, total = costos.costo_seq_scan(perfil, False)
        return SeqScan(tabla).estimar(inicio, total, ajustar_filas(perfil.filas), perfil.ancho)
    filas = ajustar_filas(perfil.filas * perfil.selectividad(condicion))
    en_indice = condicion.column == tabla.index_column
    if en_indice and condicion.op == "=":
        inicio, total = costos.costo_index_scan(perfil, _tipo_indice(tabla), filas)
        return IndexScan(tabla, condicion, False).estimar(inicio, total, filas, perfil.ancho)
    if en_indice and condicion.op in DESIGUALDADES and _soporta_rango(tabla):
        inicio, total = costos.costo_index_scan(perfil, _tipo_indice(tabla), filas)
        return IndexScan(tabla, condicion, True).estimar(inicio, total, filas, perfil.ancho)
    inicio, total = costos.costo_seq_scan(perfil, True)
    return SeqScan(tabla, condicion).estimar(inicio, total, filas, perfil.ancho)


def agregar(hijo, tabla, agrupar, specs, nombres, memoria):
    ancho = 8 * (len(nombres) + 1)
    if agrupar is None:
        inicio, total = costos.costo_aggregate(hijo.costo_total, hijo.filas_est, len(specs))
        return Agregacion(hijo, None, specs, nombres, memoria).estimar(inicio, total, 1, ancho)
    grupos = min(Perfil(tabla).n_distinct(agrupar), hijo.filas_est)
    grupos = ajustar_filas(grupos)
    inicio, total = costos.costo_hash_aggregate(hijo.costo_total, hijo.filas_est, grupos, len(specs), hijo.ancho, memoria)
    return Agregacion(hijo, agrupar, specs, nombres, memoria).estimar(inicio, total, grupos, ancho)


def ordenar(hijo, clave, memoria):
    inicio, total = costos.costo_sort(hijo.costo_total, hijo.filas_est, hijo.ancho, memoria)
    return Sort(hijo, clave, memoria).estimar(inicio, total, hijo.filas_est, hijo.ancho)


def modificar(accion, tabla, hijo, aplicar, metodo, detalle):
    nodo = Modificar(accion, tabla, hijo, aplicar, metodo, detalle)
    total = hijo.costo_total + hijo.filas_est * costos.CPU_TUPLE_COST
    return nodo.estimar(hijo.costo_inicio, total, 0, 0)


def resultado(fila, ancho):
    return Resultado(fila).estimar(0.0, costos.CPU_TUPLE_COST, 1, ancho)
