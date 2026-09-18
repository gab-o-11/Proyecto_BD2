import operator
from .visitor import Visitor
from ..catalog import StorageTable
from ..transactions import Resource, TransactionError, TransactionManager

class SemanticError(Exception):
    pass

COMPARADORES = {
    "=": operator.eq, "!=": operator.ne,
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
}

class Table:

    def __init__(self, name, columns, index_column=None, index_kind=None):
        self.name = name
        self.columns = columns
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

    def _base(self, tabla):
        clustered = getattr(tabla, "is_clustered", False)
        if clustered:
            return "sequential"
        return "heap"

    def _paso(self, op, method, detail, rows):
        return {"op": op, "method": method, "detail": detail, "rows": rows}

    def visit_Insert(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        if len(node.values) != len(tabla.columns):
            raise SemanticError(
                f"'{tabla.name}' tiene {len(tabla.columns)} columnas "
                f"y se dieron {len(node.values)} valores"
            )
        tabla.insert(dict(zip(tabla.columns, node.values)))
        self.plan.append(self._paso("Insert", self._base(tabla), tabla.name, 1))
        return {"message": f"1 fila insertada en '{tabla.name}'"}

    def visit_Delete(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        filas = self._filtrar(tabla, node.where)
        eliminadas = tabla.remove(filas)
        self.plan.append(self._paso("Delete", "lazy", tabla.name, eliminadas))
        return {"message": f"{eliminadas} fila(s) eliminada(s) de '{tabla.name}'"}

    def visit_Select(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        columnas = tabla.columns if node.columns is None else node.columns
        for c in columnas:
            self._columna(tabla, c)

        filas = self._filtrar(tabla, node.where)

        if node.group_by is not None:
            self._columna(tabla, node.group_by)
            grupos = {}
            for fila in filas:
                clave = fila[node.group_by]
                if clave not in grupos:
                    grupos[clave] = []
                grupos[clave].append(fila)
            nuevas = []
            for clave in grupos:
                nuevas.append({node.group_by: clave, "conteo": len(grupos[clave])})
            filas = nuevas
            columnas = [node.group_by, "conteo"]
            self.plan.append(self._paso("Group By", "hash", node.group_by, len(filas)))

        if node.order_by is not None:
            ordenadas = sorted(filas, key=lambda f: f[node.order_by])
            filas = ordenadas
            self.plan.append(self._paso("Order By", "sort", node.order_by, len(filas)))

        self.plan.append(self._paso("Project", ",".join(columnas), tabla.name, len(filas)))
        return {"columns": columnas, "rows": filas}

    def _filtrar(self, tabla, where):
        if where is None:
            filas = tabla.scan()
            self.plan.append(self._paso("Sequential Scan", self._base(tabla), tabla.name, len(filas)))
            return filas

        self._columna(tabla, where.column)

        if where.op == "=" and where.column == tabla.index_column:
            filas = tabla.search(where.column, where.value)
            metodo = str(tabla.index_kind) + "(" + str(tabla.index_column) + ")"
            detalle = str(where.column) + " = " + str(where.value)
            self.plan.append(self._paso("Index Search", metodo, detalle, len(filas)))
            return filas

        detalle = str(where.column) + " " + str(where.op) + " " + str(where.value)
        comparar = COMPARADORES[where.op]
        todas = tabla.scan()
        filas = []
        for f in todas:
            if comparar(f[where.column], where.value):
                filas.append(f)
        self.plan.append(self._paso("Sequential Scan + Filter", self._base(tabla), detalle, len(filas)))
        return filas

    def visit_Compare(self, node):
        raise SemanticError("las condiciones se evalúan dentro de _filtrar")

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
        if self.data_dir is None:
            self.catalog[node.table] = Table(node.table, nombres,
                                             index_column=node.index_column,
                                             index_kind=node.index_kind)
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
        self.catalog[node.table] = StorageTable(node.table, schema, self.data_dir, campo, tipo)
        self.plan.append(self._paso("Create Table", "heap", node.table, 0))
        return {"message": f"tabla '{node.table}' creada con {len(nombres)} columnas"}

    def visit_Update(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        for columna, _ in node.assignments:
            self._columna(tabla, columna)
        filas = self._filtrar(tabla, node.where)
        if isinstance(tabla, StorageTable):
            total = tabla.update_rows(filas, node.assignments)
        else:
            for fila in filas:
                for columna, valor in node.assignments:
                    fila[columna] = valor
            total = len(filas)
        columnas = ",".join(c for c, _ in node.assignments)
        self.plan.append(self._paso("Update", self._base(tabla), columnas, total))
        return {"message": f"{total} fila(s) actualizada(s) en '{tabla.name}'"}

    def visit_ColumnDef(self, node):
        return None
