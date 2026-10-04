import operator
from .visitor import Visitor
from ..catalog import StorageTable
from ..transactions import Resource, TransactionError, TransactionManager
from ..plan import base_de, planner
from ..plan.costos import Perfil
from datetime import date


class SemanticError(Exception):
    pass

MEM_BUDGET = 32

class Table:

    def __init__(self, name, columns, index_column=None, index_kind=None, column_types=None):
        self.name = name
        self.columns = columns
        self.column_types = column_types or {}
        self.index_column = index_column
        self.index_kind = index_kind
        self.rows = []

    def insert(self, row: dict):
        self.rows.append(row)

    def scan(self):
        return list(self.rows)

    def search(self, column, value):
        return [r for r in self.rows if r[column] == value]

    def remove(self, rows):
        marcadas = {id(r) for r in rows}
        self.rows = [r for r in self.rows if id(r) not in marcadas]
        return len(marcadas)


class Executor(Visitor):
    def __init__(self, catalog=None, transaction_manager=None, data_dir=None):
        self.catalog = catalog if catalog is not None else {}
        self.plan = []
        self.transaction_manager = transaction_manager or TransactionManager()
        self.data_dir = data_dir

    def execute(self, sentencias):
        for sentencia in sentencias:
            self.plan = []
            try:
                resultado = sentencia.accept(self)
            except SemanticError as e:
                print(f"  Error semántico: {e}")
                continue
            for linea in self.plan:
                print(f"  plan: {linea}")
            if resultado is None:
                continue
            if "message" in resultado:
                print("  " + resultado["message"])
            else:
                self._imprimir(resultado["columns"], resultado["rows"])

    def run(self, sentencias):
        salidas = []
        for sentencia in sentencias:
            self.plan = []
            try:
                resultado = sentencia.accept(self)
            except SemanticError as e:
                salidas.append({"error": str(e), "plan": list(self.plan)})
                continue
            salida = {"plan": list(self.plan)}
            if resultado is None:
                salida["message"] = "OK"
            elif "message" in resultado:
                salida["message"] = resultado["message"]
            else:
                salida["columns"] = resultado["columns"]
                salida["rows"] = resultado["rows"]
            salidas.append(salida)
        return salidas

    def _tabla(self, nombre):
        if nombre not in self.catalog:
            raise SemanticError(f"la tabla '{nombre}' no existe")
        return self.catalog[nombre]

    @staticmethod
    def _columna(tabla, nombre):
        if nombre not in tabla.columns:
            raise SemanticError(f"la columna '{nombre}' no existe en '{tabla.name}'")
        return nombre

    def _paso(self, op, method, detail, rows):
        return {"op": op, "method": method, "detail": detail, "rows": rows}

    def _plan_insert(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        if len(node.values) != len(tabla.columns):
            raise SemanticError(
                f"'{tabla.name}' tiene {len(tabla.columns)} columnas "
                f"y se dieron {len(node.values)} valores"
            )
        for col, valor in zip(tabla.columns, node.values):
            if getattr(tabla, "column_types", {}).get(col) == "DATE":
                try:
                    date.fromisoformat(valor)
                except (TypeError, ValueError):
                    raise SemanticError(f"'{valor}' no es una fecha válida (formato YYYY-MM-DD)")
        fila = dict(zip(tabla.columns, node.values))
        hijo = planner.resultado(fila, Perfil(tabla).ancho)

        def aplicar(filas):
            for f in filas:
                tabla.insert(f)
            return len(filas)

        return planner.modificar("Insert", tabla, hijo, aplicar, base_de(tabla), tabla.name)

    def visit_Insert(self, node):
        raiz = self._plan_insert(node)
        self._ejecutar(raiz)
        return {"message": f"1 fila insertada en '{raiz.tabla.name}'"}

    def _plan_delete(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        hijo = self._acceso(tabla, node.where)
        return planner.modificar("Delete", tabla, hijo, tabla.remove, "lazy", tabla.name)

    def visit_Delete(self, node):
        raiz = self._plan_delete(node)
        self._ejecutar(raiz)
        return {"message": f"{raiz.afectadas} fila(s) eliminada(s) de '{raiz.tabla.name}'"}

    def _plan_select(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        columnas = tabla.columns if node.columns is None else node.columns
        for c in columnas:
            self._columna(tabla, c)

        raiz = self._acceso(tabla, node.where)

        if node.group_by is not None:
            self._columna(tabla, node.group_by)
            specs, nombres = self._agg_specs(tabla, node)
            raiz = planner.agregar(raiz, tabla, node.group_by, specs, nombres, MEM_BUDGET)
            columnas = [node.group_by]
            for nombre in nombres:
                columnas.append(nombre)
        elif node.aggregates is not None:
            specs, nombres = self._agg_specs(tabla, node)
            raiz = planner.agregar(raiz, tabla, None, specs, nombres, MEM_BUDGET)
            columnas = list(nombres)

        if node.order_by is not None:
            raiz = planner.ordenar(raiz, node.order_by, MEM_BUDGET)

        return raiz, columnas, tabla

    def visit_Select(self, node):
        raiz, columnas, tabla = self._plan_select(node)
        filas = self._ejecutar(raiz)
        self.plan.append(self._paso("Project", ",".join(columnas), tabla.name, len(filas)))
        return {"columns": columnas, "rows": filas}

    def _ejecutar(self, raiz):
        filas = list(raiz.iterar())
        self.plan.extend(raiz.traza())
        return filas

    def _agg_specs(self, tabla, node):
        specs = []
        nombres = []
        if node.aggregates is None:
            specs.append(("count", None))
            nombres.append("conteo")
            return specs, nombres
        for func, arg in node.aggregates:
            if func == "count":
                specs.append(("count", None))
                nombres.append("conteo")
                continue
            if arg is None:
                raise SemanticError(f"la función {func.upper()} requiere una columna")
            self._columna(tabla, arg)
            specs.append((func, operator.itemgetter(arg)))
            nombres.append(func + "_" + arg)
        return specs, nombres

    def _acceso(self, tabla, where):
        if where is not None:
            self._columna(tabla, where.column)
        return planner.acceso(tabla, where)

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

    def _bloquear_tabla(self, tabla):
        if self.transaction_manager.current() is None:
            return
        self.transaction_manager.acquire(Resource("table", tabla.name))

    def visit_CreateTable(self, node):
        if node.table in self.catalog:
            raise SemanticError(f"la tabla '{node.table}' ya existe")
        nombres = [c.name for c in node.columns]
        if len(nombres) != len(set(nombres)):
            raise SemanticError("hay columnas repetidas")
        tipos = {c.name: c.type for c in node.columns}

        if self.data_dir is None:
            self.catalog[node.table] = Table(node.table, nombres,
                                             index_column=node.index_column,
                                             index_kind=node.index_kind,
                                             column_types=tipos)
            self.plan.append(self._paso("Create Table", "memory", node.table, 0))
            return {"message": f"tabla '{node.table}' creada con {len(nombres)} columnas"}

        schema = []
        for c in node.columns:
            if c.type == "INT":
                schema.append((c.name, "int"))
            elif c.type == "FLOAT":
                schema.append((c.name, "float"))
            else:
                schema.append((c.name, "str"))
        campo = node.index_column
        if campo is None:
            campo = nombres[0]
        tipo = node.index_kind
        if tipo is None:
            tipo = "HASH"
        tabla = StorageTable(node.table, schema, self.data_dir, campo, tipo)
        tabla.column_types = tipos
        self.catalog[node.table] = tabla
        self.plan.append(self._paso("Create Table", "heap", node.table, 0))
        return {"message": f"tabla '{node.table}' creada con {len(nombres)} columnas"}

    def _plan_update(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        for columna, _ in node.assignments:
            self._columna(tabla, columna)
        hijo = self._acceso(tabla, node.where)

        def aplicar(filas):
            if isinstance(tabla, StorageTable):
                return tabla.update_rows(filas, node.assignments)
            for fila in filas:
                for columna, valor in node.assignments:
                    fila[columna] = valor
            return len(filas)

        columnas = ",".join(c for c, _ in node.assignments)
        return planner.modificar("Update", tabla, hijo, aplicar, base_de(tabla), columnas)

    def visit_Update(self, node):
        raiz = self._plan_update(node)
        self._ejecutar(raiz)
        return {"message": f"{raiz.afectadas} fila(s) actualizada(s) en '{raiz.tabla.name}'"}

    def visit_ColumnDef(self, node):
        return None
