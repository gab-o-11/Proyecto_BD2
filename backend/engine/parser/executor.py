import operator
import math
import re
import struct
import time
from .visitor import PrintVisitor, Visitor
from .nodes import And, Between, ColumnRef, Compare, Distance, IsNull, Like, Not, Or, Point, Intersection, aggregate_name, condition_columns, expression_columns
from ..catalog import StorageTable, nombres_de_indices
from ..transactions import LockError, LockMode, Resource, TransactionError, TransactionManager
from ..plan import Predicado, Rango, base_de, planner, reporte
from ..plan import costos
from ..plan.costos import Perfil
from ..plan.nodos import COMPARADORES, Calificar, IndexScan, SpatialIndexScan
from ..spatial import distance, point
from ..spatial_table import SpatialTable
from ..rtree import contains_point, validate_polygon
from dataclasses import replace
from datetime import date


class SemanticError(Exception):
    pass


def _y(funciones, fila):
    resultado = True
    for funcion in funciones:
        valor = funcion(fila)
        if valor is False:
            return False
        if valor is None:
            resultado = None
    return resultado


def _o(funciones, fila):
    resultado = False
    for funcion in funciones:
        valor = funcion(fila)
        if valor is True:
            return True
        if valor is None:
            resultado = None
    return resultado


def _con_nulos(tabla, columna, rids, limite=None):
    entregados = 0
    for rid in rids:
        entregados += 1
        yield rid
    if limite is not None and entregados >= limite:
        return
    for fila in tabla.scan():
        if fila[columna] is None:
            yield tabla.spatial_id(fila)


def _patron_like(patron):
    partes = []
    for caracter in patron:
        if caracter == "%":
            partes.append(".*")
        elif caracter == "_":
            partes.append(".")
        else:
            partes.append(re.escape(caracter))
    return re.compile("".join(partes), re.DOTALL)

MEM_BUDGET = 32

class Table(SpatialTable):

    def __init__(self, name, columns, index_column=None, index_kind=None, column_types=None):
        self.name = name
        self._init_spatial()
        self._spatial_rows = {}
        self.columns = columns
        self.column_types = column_types or {}
        self.column_definitions = {}
        self.index_column = index_column
        self.index_kind = index_kind
        self.rows = []

    def insert(self, row: dict):
        self.rows.append(row)
        self._spatial_rows[id(row)] = row
        self._spatial_insert(row)

    @staticmethod
    def spatial_id(row):
        return id(row)

    def spatial_row(self, rid):
        return self._spatial_rows.get(rid)

    def scan(self):
        return list(self.rows)

    def search(self, column, value):
        return [r for r in self.rows if r[column] == value]

    def remove(self, rows):
        marcadas = {id(r) for r in rows}
        for row in rows:
            self._spatial_remove(row)
            self._spatial_rows.pop(id(row), None)
        self.rows = [r for r in self.rows if id(r) not in marcadas]
        return len(marcadas)


class Executor(Visitor):
    def __init__(self, catalog=None, transaction_manager=None, data_dir=None, parameters=None):
        self.catalog = catalog if catalog is not None else {}
        self.plan = []
        self.paginas_tocadas = set()
        self.transaction_manager = transaction_manager or TransactionManager()
        self.data_dir = data_dir
        self.parameters = parameters or {}

    def execute(self, sentencias):
        for resultado in self.run(sentencias):
            if "error" in resultado:
                print(f"  Error semántico: {resultado['error']}")
                continue
            for linea in resultado["plan"]:
                print(f"  plan: {linea}")
            if "message" in resultado:
                print("  " + resultado["message"])
            else:
                self._imprimir(resultado["columns"], resultado["rows"])

    def run(self, sentencias):
        activa_al_inicio = self.transaction_manager.current() is not None
        try:
            return self._run(sentencias)
        finally:
            if not activa_al_inicio and self.transaction_manager.current() is not None:
                self.transaction_manager.end()

    def _run(self, sentencias):
        salidas = []
        for sentencia in sentencias:
            self.plan = []
            self.paginas_tocadas = set()
            implicita = self.transaction_manager.current() is None and type(sentencia).__name__ not in ("BeginTransaction", "EndTransaction")
            if implicita:
                self.transaction_manager.begin()
            try:
                resultado = sentencia.accept(self)
            except SemanticError as e:
                salidas.append({"error": str(e), "plan": list(self.plan)})
                continue
            finally:
                if implicita:
                    self.transaction_manager.end()
            salida = {"plan": list(self.plan)}
            if resultado is None:
                salida["message"] = "OK"
            elif "message" in resultado:
                salida["message"] = resultado["message"]
            else:
                salida["columns"] = resultado["columns"]
                salida["rows"] = resultado["rows"]
            if resultado is not None and "spatial" in resultado:
                salida["spatial"] = resultado["spatial"]
            if resultado is not None and "explain" in resultado:
                salida["explain"] = resultado["explain"]
            if self.paginas_tocadas:
                salida["paginas"] = sorted(self.paginas_tocadas)
            salidas.append(salida)
        return salidas

    def _tabla(self, nombre):
        if nombre not in self.catalog:
            raise SemanticError(f"la tabla '{nombre}' no existe")
        return self.catalog[nombre]

    @staticmethod
    def _columna(tabla, nombre):
        if nombre in getattr(tabla, "ambiguous_columns", ()):
            raise SemanticError(f"la columna '{nombre}' es ambigua; usa tabla.columna")
        nombre = getattr(tabla, "column_aliases", {}).get(nombre, nombre)
        if nombre not in tabla.columns:
            raise SemanticError(f"la columna '{nombre}' no existe en '{tabla.name}'")
        return nombre

    def _paso(self, op, method, detail, rows):
        return {"op": op, "method": method, "detail": detail, "rows": rows}

    def _plan_insert(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla, LockMode.PX)
        columnas = list(tabla.columns)
        if node.columns is not None:
            columnas = [self._columna(tabla, c) for c in node.columns]
            if len(columnas) != len(set(columnas)):
                raise SemanticError("hay columnas repetidas en INSERT")
        filas = []
        for valores in node.all_values():
            if len(valores) != len(columnas):
                raise SemanticError(
                    f"se esperaban {len(columnas)} valores "
                    f"({', '.join(columnas)}) y se dieron {len(valores)}"
                )
            fila = {c: None for c in tabla.columns}
            fila.update(zip(columnas, valores))
            filas.append(self._validar_fila(tabla, fila))
        self._validar_claves(tabla, filas)
        hijo = planner.resultado(filas, Perfil(tabla).ancho)

        def aplicar(filas):
            for f in filas:
                tabla.insert(f)
            return len(filas)

        return planner.modificar("Insert", tabla, hijo, aplicar, base_de(tabla), tabla.name)

    def visit_Insert(self, node):
        raiz = self._plan_insert(node)
        self._ejecutar(raiz)
        self._mantener(raiz.tabla)
        if raiz.afectadas == 1:
            return {"message": f"1 fila insertada en '{raiz.tabla.name}'"}
        return {"message": f"{raiz.afectadas} filas insertadas en '{raiz.tabla.name}'"}

    def _plan_delete(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla, LockMode.PU)
        hijo = self._acceso(tabla, node.where)

        def aplicar(filas):
            self._bloquear_tabla(tabla, LockMode.PX)
            return tabla.remove(filas)

        return planner.modificar("Delete", tabla, hijo, aplicar, "lazy", tabla.name)

    def visit_Delete(self, node):
        raiz = self._plan_delete(node)
        self._ejecutar(raiz)
        self._mantener(raiz.tabla)
        return {"message": f"{raiz.afectadas} fila(s) eliminada(s) de '{raiz.tabla.name}'"}

    def _plan_select(self, node):
        raiz, tabla = self._fuente_select(node)
        columnas = list(tabla.columns) if node.columns is None else [self._columna(tabla, c) for c in node.columns]
        grupo = None if node.group_by is None else self._columna(tabla, node.group_by)

        if node.group_by is not None:
            if node.columns is not None and any(c != grupo for c in columnas):
                raise SemanticError("las columnas sin agregación deben aparecer en GROUP BY")
            specs, nombres = self._agg_specs(tabla, node)
            raiz = planner.agregar(raiz, tabla, grupo, specs, nombres, MEM_BUDGET)
            columnas = [grupo]
            for nombre in nombres:
                columnas.append(nombre)
        elif node.aggregates is not None:
            if node.columns:
                raise SemanticError("no se pueden mezclar columnas y agregaciones sin GROUP BY")
            specs, nombres = self._agg_specs(tabla, node)
            raiz = planner.agregar(raiz, tabla, None, specs, nombres, MEM_BUDGET)
            columnas = list(nombres)

        if node.projection is not None:
            agregaciones = {aggregate_name(func, arg) for func, arg in node.aggregates or []}
            columnas = [c if c in agregaciones else self._columna(tabla, c) for c in node.projection]
            if len(columnas) != len(set(columnas)):
                raise SemanticError("hay columnas repetidas en el resultado")

        if node.order_by is not None:
            orden = node.order_by
            disponibles = columnas if node.group_by is not None or node.aggregates is not None else tabla.columns
            if isinstance(orden, Distance):
                key_fn = self._distancia(tabla, orden, disponibles)
                indice = None
                texto = PrintVisitor().visit_Distance(orden)
                if node.join is None and node.limit is not None and not node.order_desc and node.group_by is None and node.aggregates is None:
                    actual = self._tabla(node.table)
                    expresion = self._sin_alias(orden, node.table_alias or node.table)
                    target = self._objetivo_espacial(actual, expresion)
                    if target is not None and node.where is None:
                        columna, centro, metrica = target
                        indice = self._indice_espacial(actual, columna, "knn", lambda tree: _con_nulos(actual, columna, tree.knn(centro, node.limit, metrica), node.limit), texto, node.limit)
                        if tabla is not actual:
                            indice = Calificar(indice, node.table_alias or node.table, actual.columns)
                    elif target is not None and tabla is actual:
                        indice = self._knn_filtrado(actual, target, texto, node.where, node.limit, raiz, key_fn)
                raiz = indice if indice is not None else planner.ordenar(raiz, texto, MEM_BUDGET, node.order_desc, key_fn)
            else:
                if orden not in columnas:
                    orden = self._columna(tabla, orden)
                if orden not in disponibles:
                    raise SemanticError(f"la columna '{node.order_by}' no está disponible para ORDER BY")
                raiz = planner.ordenar(raiz, orden, MEM_BUDGET, node.order_desc)

        if node.limit is not None:
            raiz = planner.limitar(raiz, node.limit)

        return raiz, columnas, tabla

    def _fuente_select(self, node):
        izquierda = self._tabla(node.table)
        derecha = None if node.join is None else self._tabla(node.join.table)
        for tabla in sorted([izquierda] + ([] if derecha is None else [derecha]), key=lambda t: t.name):
            self._bloquear_tabla(tabla, LockMode.PS)
        referencias = list(node.columns or []) + [arg for _, arg in node.aggregates or [] if arg is not None]
        for expresion in (node.group_by, node.order_by):
            referencias.extend(expression_columns(expresion))
        referencias.extend(condition_columns(node.where))
        if derecha is None and node.table_alias is None and not any("." in c for c in referencias):
            return self._acceso(izquierda, node.where), izquierda

        lados = [(izquierda, node.table_alias or node.table)]
        if derecha is not None:
            lados.append((derecha, node.join.alias or node.join.table))
        if len({prefijo for _, prefijo in lados}) != len(lados):
            raise SemanticError("JOIN requiere nombres o alias de tabla distintos")
        columnas = [prefijo + "." + c for tabla, prefijo in lados for c in tabla.columns]
        fuente = Table(" JOIN ".join(prefijo for _, prefijo in lados), columnas)
        fuente.column_types = {prefijo + "." + c: {"int": "INT", "float": "FLOAT", "str": "VARCHAR", "point": "POINT"}[self._tipo_columna(tabla, c)] for tabla, prefijo in lados for c in tabla.columns}
        fuente.spatial_sources = {prefijo + "." + c: (tabla.name, c) for tabla, prefijo in lados for c in tabla.columns if self._tipo_columna(tabla, c) == "point"}
        fuente.column_aliases = {}
        fuente.ambiguous_columns = set()
        for tabla, prefijo in lados:
            for c in tabla.columns:
                if c in fuente.column_aliases:
                    fuente.ambiguous_columns.add(c)
                fuente.column_aliases[c] = prefijo + "." + c
        if derecha is None:
            prefijo = lados[0][1]
            simple = self._mapear_condicion(node.where, lambda c: self._columna(fuente, c).split(".", 1)[1], lambda e: self._sin_alias(e, prefijo))
            raiz = Calificar(self._acceso(izquierda, simple), prefijo, izquierda.columns)
            return raiz, fuente

        condicion = None
        espacial = self._es_espacial(node.where)
        compuesta = node.where is not None and not espacial and not isinstance(node.where, Compare)
        if node.where is not None and not espacial and not compuesta:
            columna = self._columna(fuente, node.where.column)
            condicion = Compare(columna, node.where.op, self._valor_comparable(fuente, columna, node.where.value))

        clave_izq = self._columna(fuente, node.join.left_column)
        clave_der = self._columna(fuente, node.join.right_column)
        if clave_izq.startswith(lados[1][1] + "."):
            clave_izq, clave_der = clave_der, clave_izq
        if not clave_izq.startswith(lados[0][1] + ".") or not clave_der.startswith(lados[1][1] + "."):
            raise SemanticError("ON debe comparar una columna de cada tabla")
        tipo_izq = self._tipo_columna(fuente, clave_izq)
        tipo_der = self._tipo_columna(fuente, clave_der)
        if tipo_izq != tipo_der and {tipo_izq, tipo_der} != {"int", "float"}:
            raise SemanticError("las columnas de JOIN deben tener tipos compatibles")
        raiz = planner.unir(
            Calificar(planner.acceso(izquierda, None), lados[0][1], izquierda.columns),
            Calificar(planner.acceso(derecha, None), lados[1][1], derecha.columns),
            clave_izq, clave_der, MEM_BUDGET,
        )
        if condicion is not None:
            raiz = planner.filtrar(raiz, condicion)
        elif espacial:
            raiz = self._filtro_espacial(raiz, fuente, node.where)
        elif compuesta:
            predicado, seleccion = self._predicado(fuente, node.where)
            raiz = planner.filtrar(raiz, predicado, selectividad=seleccion)
        return raiz, fuente

    def _mapear_condicion(self, condicion, columna, distancia):
        if condicion is None:
            return None
        if isinstance(condicion, (And, Or)):
            return type(condicion)(tuple(self._mapear_condicion(c, columna, distancia) for c in condicion.conditions))
        if isinstance(condicion, Not):
            return Not(self._mapear_condicion(condicion.condition, columna, distancia))
        if isinstance(getattr(condicion, "value", None), ColumnRef):
            condicion = replace(condicion, value=ColumnRef(columna(condicion.value.name)))
        if isinstance(condicion.column, Distance):
            return replace(condicion, column=distancia(condicion.column))
        return replace(condicion, column=columna(condicion.column))

    def visit_Select(self, node):
        raiz, columnas, tabla = self._plan_select(node)
        filas = self._ejecutar(raiz)
        self.plan.append(self._paso("Project", ",".join(columnas), tabla.name, len(filas)))
        spatial = []
        if node.group_by is None and node.aggregates is None:
            for column in tabla.columns:
                if self._tipo_columna(tabla, column) == "point":
                    name, field = getattr(tabla, "spatial_sources", {}).get(column, (tabla.name, column))
                    spatial.append({"table": name, "column": field, "points": [row[column] for row in filas]})
        return {"columns": columnas, "rows": [{c: fila[c] for c in columnas} for fila in filas], "spatial": spatial}

    def _ejecutar(self, raiz):
        filas = list(raiz.iterar())
        self.plan.extend(raiz.traza())
        self.paginas_tocadas = set(raiz.real.io.paginas)
        return filas

    def _mantener(self, tabla):
        autoanalyze = getattr(tabla, "autoanalyze", None)
        if autoanalyze is not None:
            autoanalyze()

    def _planificar(self, sentencia):
        nombre = type(sentencia).__name__
        if nombre == "Select":
            raiz, columnas, tabla = self._plan_select(sentencia)
            return raiz
        if nombre == "Insert":
            return self._plan_insert(sentencia)
        if nombre == "Delete":
            return self._plan_delete(sentencia)
        if nombre == "Update":
            return self._plan_update(sentencia)
        raise SemanticError("EXPLAIN solo admite SELECT, INSERT, UPDATE o DELETE")

    def visit_Explain(self, node):
        inicio = time.perf_counter()
        raiz = self._planificar(node.statement)
        planificacion = time.perf_counter() - inicio
        ejecucion = 0.0
        if node.analyze:
            inicio = time.perf_counter()
            for _ in raiz.iterar():
                pass
            ejecucion = time.perf_counter() - inicio
            self.paginas_tocadas = set(raiz.real.io.paginas)
            self.plan.extend(raiz.traza())
            if hasattr(raiz, "afectadas"):
                self._mantener(raiz.tabla)
        explain = reporte(raiz, node.analyze, planificacion, ejecucion)
        filas = []
        for linea in explain["text"]:
            filas.append({"QUERY PLAN": linea})
        return {"columns": ["QUERY PLAN"], "rows": filas, "explain": explain}

    def visit_Analyze(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla, LockMode.PX)
        if not hasattr(tabla, "analyze"):
            return {"message": f"ANALYZE {tabla.name}: tabla en memoria, sin estadísticas"}
        estadisticas = tabla.analyze()
        self.plan.append(self._paso("Analyze", base_de(tabla), tabla.name, estadisticas["filas"]))
        return {"message": f"ANALYZE {tabla.name}: {estadisticas['filas']} filas, {len(estadisticas['columnas'])} columnas"}

    def _agg_specs(self, tabla, node):
        specs = []
        nombres = []
        if node.aggregates is None:
            specs.append(("count", None))
            nombres.append("conteo")
            return specs, nombres
        for func, arg in node.aggregates:
            columna = None
            if arg is not None:
                columna = self._columna(tabla, arg)
            if func == "count":
                specs.append(("count", None if columna is None else operator.itemgetter(columna)))
                nombres.append(aggregate_name(func, arg))
                continue
            if arg is None:
                raise SemanticError(f"la función {func.upper()} requiere una columna")
            if func in ("sum", "avg") and self._tipo_columna(tabla, columna) not in ("int", "float"):
                raise SemanticError(f"{func.upper()} requiere una columna numérica")
            specs.append((func, operator.itemgetter(columna)))
            nombres.append(aggregate_name(func, arg))
        if len(nombres) != len(set(nombres)):
            raise SemanticError("hay agregaciones repetidas en SELECT")
        return specs, nombres

    def _acceso(self, tabla, where):
        if where is None:
            return planner.acceso(tabla, None)
        if self._es_espacial(where):
            return self._acceso_espacial(tabla, where)
        if self._es_simple(where):
            simple = self._condicion_simple(tabla, where)
            principal = planner.acceso(tabla, simple)
            opciones = [o for o in [principal] + self._opciones_secundarias(tabla, simple) if isinstance(o, IndexScan)]
            return min(opciones, key=lambda o: o.costo_total) if opciones else principal
        partes = list(where.conditions) if isinstance(where, And) else [where]
        mejor, usada = None, None
        for parte in partes:
            for opcion in self._opciones_indice(tabla, parte):
                if mejor is None or opcion.costo_total < mejor.costo_total:
                    mejor, usada = opcion, parte
        if mejor is None:
            predicado, seleccion = self._predicado(tabla, where)
            return planner.escanear(tabla, predicado, seleccion)
        resto = [p for p in partes if p is not usada]
        if not resto:
            return mejor
        predicado, seleccion = self._predicado(tabla, resto[0] if len(resto) == 1 else And(tuple(resto)))
        return planner.filtrar(mejor, predicado, selectividad=seleccion)

    def _opciones_secundarias(self, tabla, condicion):
        opciones = []
        for indice in getattr(tabla, "secundarios", {}).values():
            opcion = planner.acceso_indice(tabla, condicion, indice)
            if opcion is not None:
                opciones.append(opcion)
        return opciones

    def _opciones_indice(self, tabla, condicion):
        if self._es_espacial(condicion):
            opcion = self._acceso_espacial(tabla, condicion)
            usa_indice = isinstance(opcion, SpatialIndexScan) or any(isinstance(h, SpatialIndexScan) for h in opcion.hijos)
            return [opcion] if usa_indice else []
        if self._es_simple(condicion):
            simple = self._condicion_simple(tabla, condicion)
            opciones = self._opciones_secundarias(tabla, simple)
            principal = planner.acceso_indice(tabla, simple)
            return opciones + ([principal] if principal is not None else [])
        if isinstance(condicion, Between) and not condicion.negated and isinstance(condicion.column, str):
            columna = self._columna(tabla, self._sin_tabla(tabla, condicion.column))
            bajo = self._valor_comparable(tabla, columna, condicion.low)
            alto = self._valor_comparable(tabla, columna, condicion.high)
            rango = Rango(columna, bajo, alto)
            opciones = self._opciones_secundarias(tabla, rango)
            principal = planner.acceso_indice(tabla, rango)
            return opciones + ([principal] if principal is not None else [])
        return []

    def _acceso_espacial(self, tabla, where):
        seleccion = self._selectividad_espacial(tabla, where)
        fallback = self._filtro_espacial(planner.acceso(tabla, None), tabla, where, seleccion)
        filas = Perfil(tabla).filas * (costos.DEFAULT_SPATIAL_SEL if seleccion is None else seleccion)
        if isinstance(where, Intersection):
            column = where.column.removeprefix(tabla.name + ".")
            vertices = self._vertices(where)
            extra = costos.CPU_OPERATOR_COST * len(vertices)
            return self._indice_espacial(tabla, column, "polygon", lambda tree: tree.search_polygon(vertices), PrintVisitor().visit_Intersection(where), filas, extra)
        target = self._objetivo_espacial(tabla, where.column)
        if target is not None and where.op in ("<", "<=", "="):
            column, center, metric = target
            radius = float(where.value)
            if radius >= 0:
                root = self._indice_espacial(tabla, column, "radius", lambda tree: tree.search_radius(center, radius, metric, inclusive=where.op != "<"), PrintVisitor().visit_Compare(where), filas)
                return self._filtro_espacial(root, tabla, where, costos.DEFAULT_EQ_SEL) if where.op == "=" else root
        return fallback

    @staticmethod
    def _sin_tabla(tabla, columna):
        if columna.startswith(tabla.name + "."):
            return columna.split(".", 1)[1]
        return columna

    def _valor_comparable(self, tabla, columna, valor):
        if valor is None:
            raise SemanticError("una comparación con NULL nunca es verdadera; usa IS NULL o IS NOT NULL")
        return self._convertir(tabla, columna, valor)

    def _expresion_condicion(self, tabla, expresion):
        if isinstance(expresion, Distance):
            return self._distancia(tabla, expresion), "float", None
        columna = self._columna(tabla, self._sin_tabla(tabla, expresion))
        return operator.itemgetter(columna), self._tipo_columna(tabla, columna), columna

    def _predicado(self, tabla, condicion):
        evaluar, seleccion = self._compilar(tabla, condicion)
        texto = condicion.accept(PrintVisitor())
        return Predicado(evaluar, texto), min(1.0, max(0.0, seleccion))

    def _compilar(self, tabla, condicion):
        if isinstance(condicion, (And, Or)):
            partes = [self._compilar(tabla, c) for c in condicion.conditions]
            funciones = [f for f, _ in partes]
            if isinstance(condicion, And):
                seleccion = math.prod(s for _, s in partes)
                return (lambda fila: _y(funciones, fila)), seleccion
            seleccion = 1.0 - math.prod(1.0 - s for _, s in partes)
            return (lambda fila: _o(funciones, fila)), seleccion
        if isinstance(condicion, Not):
            interna, seleccion = self._compilar(tabla, condicion.condition)
            return (lambda fila: None if (valor := interna(fila)) is None else not valor), 1.0 - seleccion
        perfil = Perfil(tabla)
        if isinstance(condicion, Intersection):
            filtro = self._filtro_espacial(planner.acceso(tabla, None), tabla, condicion)
            columna = filtro.condicion.column
            contiene = filtro.key_fn
            seleccion = self._selectividad_espacial(tabla, condicion) if hasattr(tabla, "filas_totales") else None
            return (lambda fila: None if fila[columna] is None else contiene(fila)), costos.DEFAULT_SPATIAL_SEL if seleccion is None else seleccion
        extraer, tipo, columna = self._expresion_condicion(tabla, condicion.column)
        if isinstance(condicion, IsNull):
            fraccion = perfil.fraccion_nula(columna) if columna else costos.DEFAULT_EQ_SEL
            negado = condicion.negated
            return (lambda fila: (extraer(fila) is None) != negado), (1.0 - fraccion if negado else fraccion)
        if isinstance(condicion, Like):
            if tipo != "str":
                raise SemanticError(f"LIKE requiere una columna de texto y '{columna}' no lo es")
            patron = _patron_like(condicion.pattern)
            negado = condicion.negated
            return (lambda fila: None if (valor := extraer(fila)) is None else bool(patron.fullmatch(valor)) != negado), (1.0 - costos.DEFAULT_MATCH_SEL if negado else costos.DEFAULT_MATCH_SEL)
        if isinstance(condicion, Compare) and isinstance(condicion.value, ColumnRef):
            return self._comparar_columnas(tabla, condicion, extraer, tipo, columna)
        convertir = self._conversor(tabla, columna, condicion)
        if isinstance(condicion, Compare):
            valor = convertir(condicion.value)
            comparar = COMPARADORES[condicion.op]
            if columna is None:
                seleccion = self._selectividad_espacial(tabla, condicion) if hasattr(tabla, "filas_totales") else None
                seleccion = costos.DEFAULT_SPATIAL_SEL if seleccion is None else seleccion
            else:
                seleccion = perfil.selectividad(Compare(columna, condicion.op, valor))
            return (lambda fila: None if (actual := extraer(fila)) is None else comparar(actual, valor)), seleccion
        if isinstance(condicion, Between):
            bajo, alto = convertir(condicion.low), convertir(condicion.high)
            negado = condicion.negated
            seleccion = perfil.selectividad_rango(columna, bajo, alto) if columna else costos.DEFAULT_RANGE_SEL
            return (lambda fila: None if (actual := extraer(fila)) is None else (bajo <= actual <= alto) != negado), (1.0 - seleccion if negado else seleccion)
        valores = [convertir(v) for v in condicion.values if v is not None]
        hay_nulo = any(v is None for v in condicion.values)
        negado = condicion.negated
        seleccion = min(1.0, len(set(valores)) * (perfil.selectividad(Compare(columna, "=", valores[0])) if columna and valores else costos.DEFAULT_EQ_SEL))

        def pertenece(fila):
            actual = extraer(fila)
            if actual is None:
                return None
            if actual in valores:
                return not negado
            return None if hay_nulo else negado
        return pertenece, (1.0 - seleccion if negado else seleccion)

    def _comparar_columnas(self, tabla, condicion, extraer, tipo, columna):
        otra, tipo_otra, columna_otra = self._expresion_condicion(tabla, condicion.value.name)
        numericos = {"int", "float"}
        if tipo != tipo_otra and not (tipo in numericos and tipo_otra in numericos):
            raise SemanticError(f"no se puede comparar '{condicion.column}' con '{condicion.value.name}': tipos distintos")
        if tipo == "point":
            raise SemanticError("las columnas POINT solo se comparan con distancia() o intersecta()")
        comparar = COMPARADORES[condicion.op]
        perfil = Perfil(tabla)
        if condicion.op == "=":
            distintos = max(perfil.n_distinct(columna) if columna else 1, perfil.n_distinct(columna_otra) if columna_otra else 1)
            seleccion = 1.0 / max(distintos, 1)
        elif condicion.op in ("!=", "<>"):
            seleccion = 1.0 - costos.DEFAULT_EQ_SEL
        else:
            seleccion = costos.DEFAULT_INEQ_SEL

        def evaluar(fila):
            a, b = extraer(fila), otra(fila)
            if a is None or b is None:
                return None
            return comparar(a, b)
        return evaluar, seleccion

    def _conversor(self, tabla, columna, condicion):
        if columna is not None:
            return lambda valor: self._valor_comparable(tabla, columna, valor)

        def numero(valor):
            if valor is None:
                raise SemanticError("una comparación con NULL nunca es verdadera; usa IS NULL o IS NOT NULL")
            try:
                valido = isinstance(valor, (int, float)) and math.isfinite(valor)
            except OverflowError:
                valido = False
            if not valido:
                raise SemanticError("la distancia debe compararse con un número finito")
            return valor
        return numero

    def _condicion_simple(self, tabla, where):
        if where is None:
            return None
        columna = where.column
        if columna.startswith(tabla.name + "."):
            columna = columna.split(".", 1)[1]
        columna = self._columna(tabla, columna)
        return Compare(columna, where.op, self._valor_comparable(tabla, columna, where.value))

    def _selectividad_espacial(self, tabla, where):
        perfil = Perfil(tabla)
        if isinstance(where, Intersection):
            column = where.column.removeprefix(tabla.name + ".")
            if column not in tabla.columns:
                return None
            return costos.selectividad_poligono(perfil, column, self._vertices(where))
        target = self._objetivo_espacial(tabla, where.column)
        if target is None:
            return None
        column, center, metric = target
        if isinstance(where.value, bool) or not isinstance(where.value, (int, float)) or not math.isfinite(where.value):
            return None
        radio = float(where.value)
        dentro = costos.selectividad_radio(perfil, column, center, max(radio, 0.0), metric)
        if where.op in ("<", "<="):
            return dentro
        if where.op in (">", ">="):
            return 1.0 - dentro
        if where.op in ("!=", "<>"):
            return 1.0 - costos.DEFAULT_EQ_SEL
        return costos.DEFAULT_EQ_SEL

    def _knn_filtrado(self, tabla, target, texto, where, limite, acceso, key_fn):
        columna, centro, metrica = target
        if self._es_espacial(where):
            seleccion = self._selectividad_espacial(tabla, where)
            if seleccion is None:
                seleccion = costos.DEFAULT_SPATIAL_SEL
        elif self._es_simple(where):
            condicion = self._condicion_simple(tabla, where)
            seleccion = Perfil(tabla).selectividad(condicion)
        else:
            condicion, seleccion = self._predicado(tabla, where)
        total = max(Perfil(tabla).filas, 1)
        necesarias = min(total, math.ceil(limite / max(seleccion, 1.0 / total)))
        escaneo = self._indice_espacial(tabla, columna, "knn-incremental", lambda tree: _con_nulos(tabla, columna, tree.knn_iter(centro, metrica)), texto, necesarias)
        if self._es_espacial(where):
            incremental = self._filtro_espacial(escaneo, tabla, where, seleccion)
        else:
            incremental = planner.filtrar(escaneo, condicion, selectividad=seleccion)
        ordenado = planner.ordenar(acceso, texto, MEM_BUDGET, False, key_fn)
        if planner.limitar(incremental, limite).costo_total < planner.limitar(ordenado, limite).costo_total:
            return incremental
        return ordenado

    def _distancia(self, tabla, expresion, disponibles=None):
        def operando(value):
            if isinstance(value, str) and value.startswith(tabla.name + "."):
                simple = value[len(tabla.name) + 1:]
                if simple in tabla.columns:
                    value = simple
            if isinstance(value, Point):
                constante = (value.latitude, value.longitude)
            elif value in tabla.columns or value in getattr(tabla, "column_aliases", {}):
                columna = self._columna(tabla, value)
                if disponibles is not None and columna not in disponibles:
                    raise SemanticError(f"la columna '{value}' no está disponible después de GROUP BY")
                if self._tipo_columna(tabla, columna) != "point":
                    raise SemanticError(f"la columna '{value}' debe ser de tipo POINT")
                return operator.itemgetter(columna)
            elif value in self.parameters:
                constante = self.parameters[value]
            else:
                raise SemanticError(f"no existe la columna o el parámetro espacial '{value}'")
            try:
                constante = point(constante)
                distance(constante, constante, expresion.metric)
            except ValueError as error:
                raise SemanticError(str(error)) from error
            return lambda fila: constante

        izquierda, derecha = operando(expresion.left), operando(expresion.right)

        def evaluar(fila):
            a, b = izquierda(fila), derecha(fila)
            if a is None or b is None:
                return None
            try:
                return distance(a, b, expresion.metric)
            except ValueError as error:
                raise SemanticError(str(error)) from error

        return evaluar

    @staticmethod
    def _es_espacial(condicion):
        return isinstance(condicion, Intersection) or (Executor._es_simple(condicion) and isinstance(condicion.column, Distance))

    @staticmethod
    def _es_simple(condicion):
        return isinstance(condicion, Compare) and not isinstance(condicion.value, ColumnRef)

    @staticmethod
    def _sin_alias(expresion, prefijo):
        return replace(expresion, left=expresion.left.removeprefix(prefijo + ".") if isinstance(expresion.left, str) else expresion.left,
                       right=expresion.right.removeprefix(prefijo + ".") if isinstance(expresion.right, str) else expresion.right)

    def _objetivo_espacial(self, tabla, expresion):
        self._distancia(tabla, expresion)
        operands = [o.removeprefix(tabla.name + ".") if isinstance(o, str) else o for o in (expresion.left, expresion.right)]
        columns = [o for o in operands if isinstance(o, str) and o in tabla.columns]
        if len(columns) != 1:
            return None
        other = operands[1] if operands[0] == columns[0] else operands[0]
        center = (other.latitude, other.longitude) if isinstance(other, Point) else self.parameters[other]
        return columns[0], point(center), expresion.metric

    def _indice_espacial(self, tabla, columna, operacion, buscar, texto, filas, extra_cpu=0.0):
        def consulta():
            try:
                yield from buscar(tabla.spatial_index(columna))
            except ValueError as error:
                raise SemanticError(str(error)) from error
        return planner.indice_espacial(tabla, columna, operacion, consulta, texto, filas, extra_cpu)

    @staticmethod
    def _vertices(condicion):
        try:
            return validate_polygon([(p.latitude, p.longitude) for p in condicion.polygon.vertices])
        except ValueError as error:
            raise SemanticError(str(error)) from error

    def _filtro_espacial(self, raiz, tabla, condicion, selectividad=None):
        if isinstance(condicion, Intersection):
            column = condicion.column.removeprefix(tabla.name + ".") if condicion.column not in tabla.columns else condicion.column
            column = self._columna(tabla, column)
            if self._tipo_columna(tabla, column) != "point":
                raise SemanticError("INTERSECTA requiere una columna POINT")
            vertices = self._vertices(condicion)
            filtro = planner.filtrar(raiz, Compare(column, "=", True), lambda row: row[column] is not None and contains_point(vertices, row[column]), PrintVisitor().visit_Intersection(condicion), selectividad)
            filtro.method = "sequential-polygon"
            return filtro
        try:
            valida = isinstance(condicion.value, (int, float)) and math.isfinite(condicion.value)
        except OverflowError:
            valida = False
        if not valida:
            raise SemanticError("la distancia debe compararse con un número finito")
        key_fn = self._distancia(tabla, condicion.column)
        texto = PrintVisitor().visit_Compare(condicion)
        # Comparaciones entre columnas, JOIN y complementos conservan el filtro secuencial.
        return planner.filtrar(raiz, condicion, key_fn, texto, selectividad)

    @staticmethod
    def _tipo_columna(tabla, columna):
        schema = getattr(tabla, "schema", None)
        if schema:
            return dict(schema).get(columna, "str")
        tipo = getattr(tabla, "column_types", {}).get(columna)
        if tipo == "INT":
            return "int"
        if tipo == "FLOAT":
            return "float"
        if tipo == "POINT":
            return "point"
        return "str"

    def _convertir(self, tabla, columna, valor):
        tipo = self._tipo_columna(tabla, columna)
        if tipo == "point":
            try:
                return point((valor.latitude, valor.longitude) if isinstance(valor, Point) else valor)
            except ValueError as error:
                raise SemanticError(f"la columna '{columna}': {error}") from error
        if isinstance(valor, Point):
            raise SemanticError(f"la columna '{columna}' no es de tipo POINT")
        if tipo == "int":
            try:
                convertido = int(valor)
                if isinstance(valor, float) and valor != convertido:
                    raise ValueError
                if not -(2**31) <= convertido < 2**31:
                    raise ValueError
                return convertido
            except (TypeError, ValueError, OverflowError):
                raise SemanticError(f"'{valor}' no es un valor válido para la columna INT '{columna}'")
        if tipo == "float":
            try:
                convertido = float(valor)
                if not math.isfinite(convertido):
                    raise ValueError
                return struct.unpack("f", struct.pack("f", convertido))[0]
            except (TypeError, ValueError, OverflowError):
                raise SemanticError(f"'{valor}' no es un valor válido para la columna FLOAT '{columna}'")
        if tipo == "str" and not isinstance(valor, str):
            return str(valor)
        return valor

    def _validar_fila(self, tabla, fila):
        salida = dict(fila)
        for columna in tabla.columns:
            valor = salida[columna]
            definition = tabla.column_definitions.get(columna, {})
            if valor is None and (definition.get("not_null") or definition.get("primary_key")):
                raise SemanticError(f"la columna '{columna}' no admite NULL")
            if valor is None:
                if isinstance(tabla, StorageTable) and columna == tabla.index_field:
                    raise SemanticError(f"la columna '{columna}' tiene el índice principal de '{tabla.name}' y no admite NULL")
                if isinstance(tabla, StorageTable) and not tabla.nulos:
                    raise SemanticError(f"la tabla '{tabla.name}' se creó sin soporte para NULL")
                continue
            valor = self._convertir(tabla, columna, valor)
            tipo = tabla.column_types.get(columna)
            if tipo == "DATE":
                try:
                    if date.fromisoformat(valor).isoformat() != valor:
                        raise ValueError
                except (TypeError, ValueError):
                    raise SemanticError(f"'{valor}' no es una fecha válida (formato YYYY-MM-DD)")
            tam = definition.get("size")
            if isinstance(valor, str):
                if tam is not None and len(valor) > tam:
                    raise SemanticError(f"el valor de '{columna}' excede VARCHAR({tam})")
                if isinstance(tabla, StorageTable) and len(valor.encode()) > tabla._string_size(columna):
                    raise SemanticError(f"el valor de '{columna}' excede el espacio de almacenamiento")
            salida[columna] = valor
        return salida

    def _validar_claves(self, tabla, nuevas, anteriores=()):
        claves = [c for c, definition in tabla.column_definitions.items() if definition.get("primary_key")]
        if not claves:
            return
        clave = claves[0]
        if not anteriores and tabla.index_column == clave:
            vistas = set()
            for fila in nuevas:
                if fila[clave] in vistas or tabla.search(clave, fila[clave]):
                    raise SemanticError(f"PRIMARY KEY duplicada: {clave} = {fila[clave]}")
                vistas.add(fila[clave])
            return
        reemplazadas = {fila[clave] for fila in anteriores}
        existentes = {fila[clave] for fila in tabla.scan() if fila[clave] not in reemplazadas}
        for fila in nuevas:
            if fila[clave] in existentes:
                raise SemanticError(f"PRIMARY KEY duplicada: {clave} = {fila[clave]}")
            existentes.add(fila[clave])

    def visit_Compare(self, node):
        raise SemanticError("las condiciones se evalúan dentro del planificador")

    @staticmethod
    def _imprimir(columnas, filas):
        print("  " + " | ".join(columnas))
        for fila in filas:
            print("  " + " | ".join(str(fila[c]) for c in columnas))
        print(f"  ({len(filas)} fila(s))")

    def visit_BeginTransaction(self, node):
        try:
            self.transaction_manager.begin()
        except TransactionError as error:
            raise SemanticError(str(error)) from error
        self.plan.append(self._paso("Begin", "transaction", "", 0))
        return None

    def visit_EndTransaction(self, node):
        try:
            self.transaction_manager.end()
        except TransactionError as error:
            raise SemanticError(str(error)) from error
        self.plan.append(self._paso("End", "transaction", "", 0))
        return None

    def _bloquear_tabla(self, tabla, mode):
        if self.transaction_manager.current() is None:
            return
        try:
            self.transaction_manager.acquire(Resource("table", tabla.name), mode)
        except (LockError, TransactionError) as error:
            raise SemanticError(str(error)) from error

    def visit_CreateTable(self, node):
        self._bloquear_catalogo(node.table)
        if node.table in self.catalog:
            raise SemanticError(f"la tabla '{node.table}' ya existe")
        nombres = [c.name for c in node.columns]
        if len(nombres) != len(set(nombres)):
            raise SemanticError("hay columnas repetidas")
        tipos = {c.name: c.type for c in node.columns}
        definitions = {c.name: {"type": c.type, "size": c.size, "primary_key": c.primary_key, "not_null": c.not_null} for c in node.columns}
        if any(c.size is not None and c.size <= 0 for c in node.columns):
            raise SemanticError("el tamaño de VARCHAR debe ser positivo")
        if node.index_column is not None and tipos[node.index_column] == "POINT":
            raise SemanticError("POINT no admite PRIMARY KEY con índices HASH o BPLUS")

        if self.data_dir is None:
            self.catalog[node.table] = Table(node.table, nombres,
                                             index_column=node.index_column,
                                             index_kind=node.index_kind,
                                             column_types=tipos)
            self.catalog[node.table].column_definitions = definitions
            self.plan.append(self._paso("Create Table", "memory", node.table, 0))
            return {"message": f"tabla '{node.table}' creada con {len(nombres)} columnas"}

        schema = []
        for c in node.columns:
            if c.type == "INT":
                schema.append((c.name, "int"))
            elif c.type == "FLOAT":
                schema.append((c.name, "float"))
            elif c.type == "POINT":
                schema.append((c.name, "point"))
            else:
                schema.append((c.name, "str"))
        campo = node.index_column
        if campo is None:
            campo = next((c.name for c in node.columns if c.type != "POINT"), None)
        if campo is None:
            raise SemanticError("la tabla necesita una columna escalar para su índice HASH o BPLUS")
        tipo = node.index_kind
        if tipo is None:
            tipo = "HASH"
        formato = "".join("i" if c.type == "INT" else "f" if c.type == "FLOAT" else "dd" if c.type == "POINT" else str(c.size * 4 if c.size is not None else 32) + "s" for c in node.columns)
        if struct.calcsize(formato + "Qii") > 4080:
            raise SemanticError("el registro es demasiado grande para una página de 4096 bytes")
        tabla = StorageTable(node.table, schema, self.data_dir, campo, tipo, definitions)
        self.catalog[node.table] = tabla
        self.plan.append(self._paso("Create Table", base_de(tabla), node.table, 0))
        return {"message": f"tabla '{node.table}' creada con {len(nombres)} columnas"}

    def _bloquear_catalogo(self, nombre):
        try:
            self.transaction_manager.acquire(Resource("catalog", "tables"), LockMode.PX)
            self.transaction_manager.acquire(Resource("table", nombre), LockMode.PX)
        except (LockError, TransactionError) as error:
            raise SemanticError(str(error)) from error

    def visit_CreateIndex(self, node):
        self._bloquear_catalogo(node.table)
        tabla = self._tabla(node.table)
        if not isinstance(tabla, StorageTable):
            raise SemanticError("los índices secundarios solo existen en tablas guardadas en disco")
        columna = self._columna(tabla, node.column)
        if self._tipo_columna(tabla, columna) == "point":
            raise SemanticError(f"la columna POINT '{columna}' ya tiene su R-Tree; CREATE INDEX admite HASH o BPLUS")
        tipo = node.kind or "BPLUS"
        existentes = nombres_de_indices(self.catalog)
        if node.name in existentes:
            raise SemanticError(f"ya existe un índice llamado '{node.name}' (en '{existentes[node.name]}')")
        principal = str(tabla.index_kind)
        if columna == tabla.index_field and (principal == tipo or (tipo == "BPLUS" and principal == "BPLUS_CLUSTERED")):
            raise SemanticError(f"'{columna}' ya tiene el índice principal {tabla.nombre_indice_principal()} ({principal})")
        for indice in tabla.secundarios.values():
            if indice.columna == columna and indice.tipo == tipo:
                raise SemanticError(f"'{columna}' ya tiene el índice {tipo} '{indice.nombre}'")
        try:
            indice = tabla.crear_indice(node.name, columna, tipo)
        except ValueError as error:
            raise SemanticError(str(error)) from error
        filas = sum(1 for fila in tabla.scan() if fila[columna] is not None)
        descripcion = "B+ no agrupado" if tipo == "BPLUS" else "hash extensible"
        self.plan.append(self._paso("Create Index", tipo + "(" + columna + ")", node.name, filas))
        return {"message": f"índice '{indice.nombre}' creado sobre {tabla.name}.{columna} ({descripcion}, {filas} entradas)"}

    def visit_DropTable(self, node):
        self._bloquear_catalogo(node.table)
        if node.table not in self.catalog:
            if node.if_exists:
                return {"message": f"la tabla '{node.table}' no existe; se omite"}
            raise SemanticError(f"la tabla '{node.table}' no existe")
        tabla = self.catalog.pop(node.table)
        if isinstance(tabla, StorageTable):
            tabla.destruir()
        self.plan.append(self._paso("Drop Table", base_de(tabla), node.table, 0))
        return {"message": f"tabla '{node.table}' eliminada"}

    def visit_DropIndex(self, node):
        existentes = nombres_de_indices(self.catalog)
        if node.name not in existentes:
            if node.if_exists:
                return {"message": f"el índice '{node.name}' no existe; se omite"}
            raise SemanticError(f"el índice '{node.name}' no existe")
        self._bloquear_catalogo(existentes[node.name])
        tabla = self._tabla(existentes[node.name])
        if node.name not in tabla.secundarios:
            raise SemanticError(f"'{node.name}' es un índice propio de la tabla '{tabla.name}' y no se puede eliminar; solo se eliminan índices creados con CREATE INDEX")
        tabla.eliminar_indice(node.name)
        self.plan.append(self._paso("Drop Index", tabla.name, node.name, 0))
        return {"message": f"índice '{node.name}' eliminado de '{tabla.name}'"}

    def _plan_update(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla, LockMode.PU)
        for columna, _ in node.assignments:
            self._columna(tabla, columna)
        hijo = self._acceso(tabla, node.where)

        def aplicar(filas):
            self._bloquear_tabla(tabla, LockMode.PX)
            nuevas = [self._validar_fila(tabla, dict(fila, **dict(node.assignments))) for fila in filas]
            self._validar_claves(tabla, nuevas, filas)
            if isinstance(tabla, StorageTable):
                total = 0
                for fila, nueva in zip(filas, nuevas):
                    asignaciones = [(columna, nueva[columna]) for columna, _ in node.assignments]
                    total += tabla.update_rows([fila], asignaciones)
                return total
            for fila, nueva in zip(filas, nuevas):
                tabla._spatial_remove(fila)
                fila.update(nueva)
                tabla._spatial_insert(fila)
            return len(filas)

        columnas = ",".join(c for c, _ in node.assignments)
        return planner.modificar("Update", tabla, hijo, aplicar, base_de(tabla), columnas)

    def visit_Update(self, node):
        raiz = self._plan_update(node)
        self._ejecutar(raiz)
        self._mantener(raiz.tabla)
        return {"message": f"{raiz.afectadas} fila(s) actualizada(s) en '{raiz.tabla.name}'"}

    def visit_ColumnDef(self, node):
        return None
