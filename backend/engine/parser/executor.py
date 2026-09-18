import operator
from .visitor import Visitor
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
    def __init__(self, catalog=None, transaction_manager=None):
        self.catalog = catalog if catalog is not None else {}
        self.plan = []
        self.transaction_manager = transaction_manager or TransactionManager()

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
            if resultado is not None:
                self._imprimir(resultado)

    def _tabla(self, nombre):
        if nombre not in self.catalog:
            raise SemanticError(f"la tabla '{nombre}' no existe")
        return self.catalog[nombre]

    @staticmethod
    def _columna(tabla, nombre):
        if nombre not in tabla.columns:
            raise SemanticError(f"la columna '{nombre}' no existe en '{tabla.name}'")
        return nombre

    def visit_Insert(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        if len(node.values) != len(tabla.columns):
            raise SemanticError(
                f"'{tabla.name}' tiene {len(tabla.columns)} columnas "
                f"y se dieron {len(node.values)} valores"
            )
        tabla.insert(dict(zip(tabla.columns, node.values)))
        self.plan.append(f"inserción en '{tabla.name}'")
        print(f"  1 fila insertada en '{tabla.name}'")
        return None

    def visit_Delete(self, node):
        tabla = self._tabla(node.table)
        self._bloquear_tabla(tabla)
        filas = self._filtrar(tabla, node.where)
        print(f"  {tabla.remove(filas)} fila(s) eliminada(s) de '{tabla.name}'")
        return None

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
                grupos.setdefault(fila[node.group_by], []).append(fila)
            self.plan.append(f"agrupación por '{node.group_by}' ({len(grupos)} grupos)")
            filas = [{node.group_by: clave, "conteo": len(g)} for clave, g in grupos.items()]
            columnas = [node.group_by, "conteo"]

        if node.order_by is not None:
            filas.sort(key=lambda f: f[node.order_by])
            self.plan.append(f"ordenamiento por '{node.order_by}'")

        return columnas, filas

    def _filtrar(self, tabla, where):
        if where is None:
            self.plan.append("recorrido completo (sin WHERE)")
            return tabla.scan()

        self._columna(tabla, where.column)

        if where.op == "=" and where.column == tabla.index_column:
            self.plan.append(f"búsqueda por índice {tabla.index_kind}({tabla.index_column})")
            return tabla.search(where.column, where.value)

        self.plan.append("recorrido completo + filtro")
        comparar = COMPARADORES[where.op]
        return [f for f in tabla.scan() if comparar(f[where.column], where.value)]

    def visit_Compare(self, node):
        raise SemanticError("las condiciones se evalúan dentro de _filtrar")

    @staticmethod
    def _imprimir(resultado):
        columnas, filas = resultado
        print("  " + " | ".join(columnas))
        for fila in filas:
            print("  " + " | ".join(str(fila[c]) for c in columnas))
        print(f"  ({len(filas)} fila(s))")

    def visit_BeginTransaction(self, node):
        try:
            self.transaction_manager.begin()
        except TransactionError as error:
            raise SemanticError(str(error)) from error
        self.plan.append("inicio de transacción")
        return None

    def visit_EndTransaction(self, node):
        try:
            self.transaction_manager.end()
        except TransactionError as error:
            raise SemanticError(str(error)) from error
        self.plan.append("fin de transacción")
        return None

    def _bloquear_tabla(self, tabla):
        if self.transaction_manager.current() is None:
            return
        self.transaction_manager.acquire(Resource("table", tabla.name))
