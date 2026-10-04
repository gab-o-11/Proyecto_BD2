import math

SEQ_PAGE_COST = 1.0
RANDOM_PAGE_COST = 4.0
CPU_TUPLE_COST = 0.01
CPU_INDEX_TUPLE_COST = 0.005
CPU_OPERATOR_COST = 0.0025

DEFAULT_EQ_SEL = 0.005
DEFAULT_SPATIAL_SEL = 0.005
EARTH_RADIUS_METERS = 6_371_000.0
DEFAULT_INEQ_SEL = 1.0 / 3.0
DEFAULT_NUM_DISTINCT = 200
DEFAULT_WIDTH = 32
DEFAULT_BLOCK_FACTOR = 32
PAGE_SIZE = 4096


def _es_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def ajustar_filas(filas):
    if filas < 1:
        return 1
    return int(round(filas))


class Perfil:
    def __init__(self, tabla):
        estadisticas = getattr(tabla, "estadisticas", None)
        if hasattr(tabla, "filas_totales"):
            self.filas = tabla.filas_totales()
            self.paginas = max(1, tabla.paginas())
            self.ancho = tabla.ancho()
            self.filas_por_pagina = max(1, tabla.filas_por_pagina())
            self.altura = tabla.altura_indice()
        else:
            self.filas = len(tabla.rows)
            self.ancho = DEFAULT_WIDTH
            self.filas_por_pagina = PAGE_SIZE // DEFAULT_WIDTH
            self.paginas = max(1, math.ceil(self.filas / self.filas_por_pagina))
            self.altura = 1
        indice = getattr(tabla, "index", None)
        self.block_factor = getattr(indice, "block_factor", DEFAULT_BLOCK_FACTOR)
        self.columnas = {}
        if estadisticas:
            self.columnas = estadisticas.get("columnas", {})

    def bbox(self, columna):
        info = self.columnas.get(columna)
        if not info or not info.get("bbox"):
            return None
        return info["bbox"]

    def n_distinct(self, columna):
        info = self.columnas.get(columna)
        if info and info.get("n_distinct"):
            return info["n_distinct"]
        return DEFAULT_NUM_DISTINCT

    def selectividad(self, condicion):
        info = self.columnas.get(condicion.column)
        valor = condicion.value
        if condicion.op in ("=", "!=", "<>"):
            if not info or not info.get("n_distinct"):
                sel = DEFAULT_EQ_SEL
            else:
                sel = 1.0 / info["n_distinct"]
                bajo, alto = info.get("min"), info.get("max")
                if _es_numero(valor) and _es_numero(bajo) and _es_numero(alto):
                    if valor < bajo or valor > alto:
                        sel = 0.0
            if condicion.op in ("!=", "<>"):
                return 1.0 - sel
            return sel
        if not info:
            return DEFAULT_INEQ_SEL
        bajo, alto = info.get("min"), info.get("max")
        if not (_es_numero(valor) and _es_numero(bajo) and _es_numero(alto)):
            return DEFAULT_INEQ_SEL
        if alto == bajo:
            fraccion = 1.0 if valor >= alto else 0.0
        else:
            fraccion = (valor - bajo) / (alto - bajo)
        fraccion = min(1.0, max(0.0, fraccion))
        if condicion.op in ("<", "<="):
            return fraccion
        return 1.0 - fraccion


def costo_seq_scan(perfil, con_filtro):
    total = perfil.paginas * SEQ_PAGE_COST + perfil.filas * CPU_TUPLE_COST
    if con_filtro:
        total += perfil.filas * CPU_OPERATOR_COST
    return 0.0, total


def costo_index_scan(perfil, tipo, filas):
    n = max(perfil.filas, 1)
    if tipo == "HASH":
        inicio = 0.0
        paginas_indice = 1 + filas // perfil.block_factor
    else:
        inicio = math.ceil(math.log2(n + 1)) * CPU_OPERATOR_COST
        inicio += (perfil.altura + 1) * 50 * CPU_OPERATOR_COST
        paginas_indice = perfil.altura - 1 + max(1, math.ceil(filas / perfil.block_factor))
    total = inicio + paginas_indice * RANDOM_PAGE_COST
    total += filas * (CPU_INDEX_TUPLE_COST + CPU_OPERATOR_COST)
    if tipo == "BPLUS_CLUSTERED":
        paginas_datos = max(1, math.ceil(filas / perfil.filas_por_pagina))
        total += RANDOM_PAGE_COST + (paginas_datos - 1) * SEQ_PAGE_COST
    else:
        total += min(filas, perfil.paginas) * RANDOM_PAGE_COST
    total += filas * CPU_TUPLE_COST
    return inicio, total


def paginas_temporales(filas, ancho):
    return max(1, math.ceil(filas * ancho / PAGE_SIZE))


def costo_sort(total_hijo, filas, ancho, memoria):
    n = max(filas, 2)
    inicio = total_hijo + 2 * CPU_OPERATOR_COST * n * math.log2(n)
    if filas > memoria:
        inicio += 2 * paginas_temporales(filas, ancho) * SEQ_PAGE_COST
    return inicio, inicio + CPU_OPERATOR_COST * filas


def costo_hash_aggregate(total_hijo, filas, grupos, agregados, ancho, memoria):
    inicio = total_hijo + filas * CPU_OPERATOR_COST * (1 + agregados)
    if grupos > memoria:
        inicio += 2 * paginas_temporales(filas, ancho) * SEQ_PAGE_COST
    return inicio, inicio + grupos * CPU_TUPLE_COST


def costo_aggregate(total_hijo, filas, agregados):
    inicio = total_hijo + filas * CPU_OPERATOR_COST * max(agregados, 1)
    return inicio, inicio + CPU_TUPLE_COST


def _fraccion_eje(bajo, alto, consulta_bajo, consulta_alto):
    if alto == bajo:
        return 1.0 if consulta_bajo <= bajo <= consulta_alto else 0.0
    solapado = min(alto, consulta_alto) - max(bajo, consulta_bajo)
    return max(0.0, solapado) / (alto - bajo)


def _fraccion_caja(datos, consulta, forma):
    fraccion = _fraccion_eje(datos[0], datos[2], consulta[0], consulta[2])
    fraccion *= _fraccion_eje(datos[1], datos[3], consulta[1], consulta[3])
    contiene = consulta[0] <= datos[0] and consulta[1] <= datos[1] and consulta[2] >= datos[2] and consulta[3] >= datos[3]
    if not contiene:
        fraccion *= forma
    return min(1.0, max(0.0, fraccion))


def selectividad_radio(perfil, columna, centro, radio, metrica):
    datos = perfil.bbox(columna)
    if datos is None:
        return DEFAULT_SPATIAL_SEL
    if metrica == "euclidean":
        delta_lat = delta_lon = radio
    else:
        delta_lat = math.degrees(min(math.pi, radio / EARTH_RADIUS_METERS))
        coseno = math.cos(math.radians(centro[0]))
        delta_lon = 180.0 if coseno < 1e-9 else min(180.0, delta_lat / coseno)
    consulta = (centro[0] - delta_lat, centro[1] - delta_lon, centro[0] + delta_lat, centro[1] + delta_lon)
    return _fraccion_caja(datos, consulta, math.pi / 4)


def _area_poligono(vertices):
    total = 0.0
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        total += a[0] * b[1] - b[0] * a[1]
    return abs(total) / 2


def selectividad_poligono(perfil, columna, vertices):
    datos = perfil.bbox(columna)
    if datos is None:
        return DEFAULT_SPATIAL_SEL
    vertices = list(vertices)
    latitudes = [v[0] for v in vertices]
    longitudes = [v[1] for v in vertices]
    consulta = (min(latitudes), min(longitudes), max(latitudes), max(longitudes))
    area_caja = (consulta[2] - consulta[0]) * (consulta[3] - consulta[1])
    forma = 1.0 if area_caja == 0 else min(1.0, _area_poligono(vertices) / area_caja)
    return _fraccion_caja(datos, consulta, forma)


def costo_spatial_scan(perfil, altura, capacidad, filas, extra_cpu=0.0):
    n = max(perfil.filas, 1)
    inicio = math.ceil(math.log2(n + 1)) * CPU_OPERATOR_COST
    inicio += (altura + 1) * 50 * CPU_OPERATOR_COST
    paginas_indice = altura - 1 + max(1, math.ceil(filas / capacidad))
    total = inicio + paginas_indice * RANDOM_PAGE_COST
    total += filas * (CPU_INDEX_TUPLE_COST + CPU_OPERATOR_COST + extra_cpu)
    total += min(filas, perfil.paginas) * RANDOM_PAGE_COST
    total += filas * CPU_TUPLE_COST
    return inicio, total

