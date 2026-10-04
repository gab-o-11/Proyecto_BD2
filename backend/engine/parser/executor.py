import operator
import math
import struct
import time
from .visitor import PrintVisitor, Visitor
from .nodes import Compare, Distance, Point, Intersection, aggregate_name, expression_columns
from ..catalog import StorageTable
from ..transactions import LockError, LockMode, Resource, TransactionError, TransactionManager
from ..plan import base_de, planner, reporte
from ..plan.costos import Perfil
from ..plan.nodos import Calificar, SpatialIndexScan
from ..spatial import distance, point
from ..spatial_table import SpatialTable
from ..rtree import contains_point, validate_polygon
from dataclasses import replace
from datetime import date


class SemanticError(Exception):
    pass

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
        if len(node.values) != len(tabla.columns):
            raise SemanticError(
                f"'{tabla.name}' tiene {len(tabla.columns)} columnas "
                f"y se dieron {len(node.values)} valores"
            )
        fila = dict(zip(tabla.columns, node.values))
        fila = self._validar_fila(tabla, fila)
        self._validar_claves(tabla, [fila])
        hijo = planner.resultado(fila, Perfil(tabla).ancho)

        def aplicar(filas):
            for f in filas:
                tabla.insert(f)
            return len(filas)

        return planner.modificar("Insert", tabla, hijo, aplicar, base_de(tabla), tabla.name)

    def visit_Insert(self, node):
        raiz = self._plan_insert(node)
        self._ejecutar(raiz)
        self._mantener(raiz.tabla)
        return {"message": f"1 fila insertada en '{raiz.tabla.name}'"}

    def _plan_delete(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla, LockMode.PX)
        hijo = self._acceso(tabla, node.where)
        return planner.modificar("Delete", tabla, hijo, tabla.remove, "lazy", tabla.name)

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
                if node.join is None and node.where is None and node.limit is not None and not node.order_desc and node.group_by is None and node.aggregates is None:
                    actual = self._tabla(node.table)
                    expresion = self._sin_alias(orden, node.table_alias or node.table)
                    target = self._objetivo_espacial(actual, expresion)
                    if target is not None:
                        columna, centro, metrica = target
                        indice = self._indice_espacial(actual, columna, "knn", lambda tree: tree.knn(centro, node.limit, metrica), PrintVisitor().visit_Distance(orden), node.limit)
                        if tabla is not actual:
                            indice = Calificar(indice, node.table_alias or node.table, actual.columns)
                raiz = indice if indice is not None else planner.ordenar(raiz, PrintVisitor().visit_Distance(orden), MEM_BUDGET, node.order_desc, key_fn)
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
        for expresion in (node.group_by, node.order_by, None if node.where is None else node.where.column):
            referencias.extend(expression_columns(expresion))
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
        condicion = None
        espacial = self._es_espacial(node.where)
        if node.where is not None and not espacial:
            columna = self._columna(fuente, node.where.column)
            condicion = Compare(columna, node.where.op, self._convertir(fuente, columna, node.where.value))
        if derecha is None:
            simple = None if condicion is None else Compare(condicion.column.split(".", 1)[1], condicion.op, condicion.value)
            if espacial:
                self._filtro_espacial(planner.acceso(izquierda, None), fuente, node.where)
                if isinstance(node.where, Intersection):
                    simple = replace(node.where, column=self._columna(fuente, node.where.column).split(".", 1)[1])
                else:
                    simple = replace(node.where, column=self._sin_alias(node.where.column, lados[0][1]))
            raiz = Calificar(self._acceso(izquierda, simple), lados[0][1], izquierda.columns)
            return raiz, fuente

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
        return raiz, fuente

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
                specs.append(("count", None))
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
        if self._es_espacial(where):
            fallback = self._filtro_espacial(planner.acceso(tabla, None), tabla, where)
            if isinstance(where, Intersection):
                column = where.column.removeprefix(tabla.name + ".")
                vertices = self._vertices(where)
                return self._indice_espacial(tabla, column, "polygon", lambda tree: tree.search_polygon(vertices), PrintVisitor().visit_Intersection(where))
            target = self._objetivo_espacial(tabla, where.column)
            if target is not None and where.op in ("<", "<=", "="):
                column, center, metric = target
                radius = float(where.value)
                if radius >= 0:
                    root = self._indice_espacial(tabla, column, "radius", lambda tree: tree.search_radius(center, radius, metric, inclusive=where.op != "<"), PrintVisitor().visit_Compare(where))
                    return self._filtro_espacial(root, tabla, where) if where.op == "=" else root
            return fallback
        if where is not None:
            columna = where.column
            if columna.startswith(tabla.name + "."):
                columna = columna.split(".", 1)[1]
            columna = self._columna(tabla, columna)
            where = Compare(columna, where.op, self._convertir(tabla, columna, where.value))
        return planner.acceso(tabla, where)

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
            try:
                return distance(izquierda(fila), derecha(fila), expresion.metric)
            except ValueError as error:
                raise SemanticError(str(error)) from error

        return evaluar

    @staticmethod
    def _es_espacial(condicion):
        return isinstance(condicion, Intersection) or (condicion is not None and isinstance(condicion.column, Distance))

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

    def _indice_espacial(self, tabla, columna, operacion, buscar, texto, limite=None):
        def consulta():
            try:
                return buscar(tabla.spatial_index(columna))
            except ValueError as error:
                raise SemanticError(str(error)) from error
        return SpatialIndexScan(tabla, columna, operacion, consulta, texto, limite)

    @staticmethod
    def _vertices(condicion):
        try:
            return validate_polygon([(p.latitude, p.longitude) for p in condicion.polygon.vertices])
        except ValueError as error:
            raise SemanticError(str(error)) from error

    def _filtro_espacial(self, raiz, tabla, condicion):
        if isinstance(condicion, Intersection):
            column = condicion.column.removeprefix(tabla.name + ".") if condicion.column not in tabla.columns else condicion.column
            column = self._columna(tabla, column)
            if self._tipo_columna(tabla, column) != "point":
                raise SemanticError("INTERSECTA requiere una columna POINT")
            vertices = self._vertices(condicion)
            filtro = planner.filtrar(raiz, Compare(column, "=", True), lambda row: contains_point(vertices, row[column]), PrintVisitor().visit_Intersection(condicion))
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
        return planner.filtrar(raiz, condicion, key_fn, texto)

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
        try:
            self.transaction_manager.acquire(Resource("catalog", "tables"), LockMode.PX)
            self.transaction_manager.acquire(Resource("table", node.table), LockMode.PX)
        except (LockError, TransactionError) as error:
            raise SemanticError(str(error)) from error
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
        if struct.calcsize(formato + "ii") > 4080:
            raise SemanticError("el registro es demasiado grande para una página de 4096 bytes")
        tabla = StorageTable(node.table, schema, self.data_dir, campo, tipo, definitions)
        self.catalog[node.table] = tabla
        self.plan.append(self._paso("Create Table", base_de(tabla), node.table, 0))
        return {"message": f"tabla '{node.table}' creada con {len(nombres)} columnas"}

    def _plan_update(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla, LockMode.PX)
        for columna, _ in node.assignments:
            self._columna(tabla, columna)
        hijo = self._acceso(tabla, node.where)

        def aplicar(filas):
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
