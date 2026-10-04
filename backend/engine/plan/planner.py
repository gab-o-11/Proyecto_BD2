from . import costos
from .costos import Perfil, ajustar_filas
from .nodos import Agregacion, Filtro, HashJoin, IndexScan, Limite, Modificar, Rango, Resultado, SeqScan, Sort, SpatialIndexScan

DESIGUALDADES = (">", ">=", "<", "<=")


def _soporta_rango(tabla):
    if not hasattr(tabla, "buscar_rango"):
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


def _filas_condicion(perfil, condicion):
    if isinstance(condicion, Rango):
        return ajustar_filas(perfil.filas * perfil.selectividad_rango(condicion.column, condicion.bajo, condicion.alto))
    return ajustar_filas(perfil.filas * perfil.selectividad(condicion))


def acceso_indice(tabla, condicion, secundario=None):
    perfil = Perfil(tabla)
    igualdad = not isinstance(condicion, Rango) and condicion.op == "="
    if not igualdad and not isinstance(condicion, Rango) and condicion.op not in DESIGUALDADES:
        return None
    filas = _filas_condicion(perfil, condicion)
    if secundario is None:
        if condicion.column != tabla.index_column:
            return None
        if not igualdad and not _soporta_rango(tabla):
            return None
        inicio, total = costos.costo_index_scan(perfil, _tipo_indice(tabla), filas)
        return IndexScan(tabla, condicion, not igualdad).estimar(inicio, total, filas, perfil.ancho)
    if condicion.column != secundario.columna:
        return None
    if not igualdad and secundario.tipo == "HASH":
        return None
    altura = 1 if secundario.tipo == "HASH" else secundario.estructura.height
    inicio, total = costos.costo_index_scan(perfil, secundario.tipo, filas, altura)
    return IndexScan(tabla, condicion, not igualdad, secundario).estimar(inicio, total, filas, perfil.ancho)


def escanear(tabla, predicado, selectividad):
    perfil = Perfil(tabla)
    inicio, total = costos.costo_seq_scan(perfil, True)
    return SeqScan(tabla, predicado).estimar(inicio, total, ajustar_filas(perfil.filas * selectividad), perfil.ancho)


def agregar(hijo, tabla, agrupar, specs, nombres, memoria):
    ancho = 8 * (len(nombres) + 1)
    if agrupar is None:
        inicio, total = costos.costo_aggregate(hijo.costo_total, hijo.filas_est, len(specs))
        return Agregacion(hijo, None, specs, nombres, memoria).estimar(inicio, total, 1, ancho)
    grupos = min(Perfil(tabla).n_distinct(agrupar), hijo.filas_est)
    grupos = ajustar_filas(grupos)
    inicio, total = costos.costo_hash_aggregate(hijo.costo_total, hijo.filas_est, grupos, len(specs), hijo.ancho, memoria)
    return Agregacion(hijo, agrupar, specs, nombres, memoria).estimar(inicio, total, grupos, ancho)


def ordenar(hijo, clave, memoria, reverse=False, key_fn=None):
    inicio, total = costos.costo_sort(hijo.costo_total, hijo.filas_est, hijo.ancho, memoria)
    return Sort(hijo, clave, memoria, reverse, key_fn).estimar(inicio, total, hijo.filas_est, hijo.ancho)


def limitar(hijo, cantidad):
    if isinstance(hijo, Sort) and cantidad <= hijo.memoria:
        hijo.limite = cantidad
        entrada = hijo.hijos[0]
        hijo.costo_inicio, hijo.costo_total = costos.costo_sort_topn(entrada.costo_total, entrada.filas_est, cantidad)
        hijo.filas_est = ajustar_filas(min(cantidad, entrada.filas_est))
    filas = min(cantidad, hijo.filas_est)
    fraccion = min(1.0, cantidad / max(1, hijo.filas_est))
    total = hijo.costo_inicio + (hijo.costo_total - hijo.costo_inicio) * fraccion
    return Limite(hijo, cantidad).estimar(hijo.costo_inicio, total, filas, hijo.ancho)


def unir(izquierda, derecha, clave_izquierda, clave_derecha, memoria):
    inicio = izquierda.costo_total + derecha.costo_total
    filas = ajustar_filas(izquierda.filas_est * derecha.filas_est * costos.DEFAULT_EQ_SEL)
    total = inicio + (izquierda.filas_est + derecha.filas_est + filas) * costos.CPU_TUPLE_COST
    return HashJoin(izquierda, derecha, clave_izquierda, clave_derecha, memoria).estimar(inicio, total, filas, izquierda.ancho + derecha.ancho)

def filtrar(hijo, condicion, key_fn=None, detail=None, selectividad=None):
    if selectividad is None:
        selectividad = costos.DEFAULT_EQ_SEL
    total = hijo.costo_total + hijo.filas_est * costos.CPU_OPERATOR_COST
    filas = ajustar_filas(hijo.filas_est * selectividad)
    return Filtro(hijo, condicion, key_fn, detail).estimar(hijo.costo_inicio, total, filas, hijo.ancho)


def modificar(accion, tabla, hijo, aplicar, metodo, detalle):
    nodo = Modificar(accion, tabla, hijo, aplicar, metodo, detalle)
    total = hijo.costo_total + hijo.filas_est * costos.CPU_TUPLE_COST
    return nodo.estimar(hijo.costo_inicio, total, 0, 0)


def resultado(filas, ancho):
    return Resultado(filas).estimar(0.0, costos.CPU_TUPLE_COST * len(filas), len(filas), ancho)


def indice_espacial(tabla, columna, operacion, consulta, detalle, filas, extra_cpu=0.0):
    perfil = Perfil(tabla)
    arbol = tabla.spatial_index(columna)
    filas = ajustar_filas(min(filas, max(perfil.filas, 1)))
    inicio, total = costos.costo_spatial_scan(perfil, arbol.height, arbol.max_entries, filas, extra_cpu)
    return SpatialIndexScan(tabla, columna, operacion, consulta, detalle).estimar(inicio, total, filas, perfil.ancho)
