from abc import ABC, abstractmethod
from .nodes import Distance, Point, aggregate_name


class Visitor(ABC):

    @abstractmethod
    def visit_Select(self, node): ...
    @abstractmethod
    def visit_Insert(self, node): ...
    @abstractmethod
    def visit_Delete(self, node): ...
    @abstractmethod
    def visit_Compare(self, node): ...
    @abstractmethod
    def visit_BeginTransaction(self, node): ...
    @abstractmethod
    def visit_EndTransaction(self, node): ...
    @abstractmethod
    def visit_CreateTable(self, node): ...
    @abstractmethod
    def visit_ColumnDef(self, node): ...
    @abstractmethod
    def visit_Update(self, node): ...
    @abstractmethod
    def visit_Explain(self, node): ...
    @abstractmethod
    def visit_Analyze(self, node): ...

class PrintVisitor(Visitor):
    def render(self, sentencias) -> str:
        return "\n".join(s.accept(self) + ";" for s in sentencias)

    def visit_Select(self, node):

        if node.columns is None:
            items = ["*"]
        else:
            expresiones = {columna: columna for columna in node.columns}
            for func, arg in node.aggregates or []:
                argumento = "*" if arg is None else arg
                expresiones[aggregate_name(func, arg)] = f"{func.upper()}({argumento})"
            orden = node.projection or list(expresiones)
            items = [expresiones[nombre] for nombre in orden]

        sql = f"SELECT {', '.join(items)} FROM {node.table}"
        if node.table_alias is not None:
            sql += f" AS {node.table_alias}"
        if node.join is not None:
            sql += f" JOIN {node.join.table}"
            if node.join.alias is not None:
                sql += f" AS {node.join.alias}"
            sql += f" ON {node.join.left_column} = {node.join.right_column}"

        if node.where is not None:
            sql += " WHERE " + node.where.accept(self)
        if node.group_by is not None:
            sql += f" GROUP BY {node.group_by}"
        if node.order_by is not None:
            orden = node.order_by.accept(self) if isinstance(node.order_by, Distance) else node.order_by
            sql += f" ORDER BY {orden}"
            if node.order_desc:
                sql += " DESC"
        if node.limit is not None:
            sql += f" LIMIT {node.limit}"
        return sql

    def visit_Insert(self, node):
        valores = ", ".join(self._literal(v) for v in node.values)
        return f"INSERT INTO {node.table} VALUES ({valores})"

    def visit_Delete(self, node):
        return f"DELETE FROM {node.table} WHERE {node.where.accept(self)}"

    def visit_Compare(self, node):
        columna = node.column.accept(self) if isinstance(node.column, Distance) else node.column
        return f"{columna} {node.op} {self._literal(node.value)}"

    def visit_Between(self, node):
        columna = node.column.accept(self) if isinstance(node.column, Distance) else node.column
        return f"{columna} BETWEEN {self._literal(node.low)} AND {self._literal(node.high)}"

    def visit_Point(self, node):
        return f"POINT({node.latitude}, {node.longitude})"

    def visit_Polygon(self, node):
        return "POLYGON(" + ", ".join(self.visit_Point(p) for p in node.vertices) + ")"

    def visit_Intersection(self, node):
        return f"intersecta({node.column}, {self.visit_Polygon(node.polygon)})"

    def visit_Distance(self, node):
        izquierda = node.left.accept(self) if isinstance(node.left, Point) else node.left
        derecha = node.right.accept(self) if isinstance(node.right, Point) else node.right
        return f"distancia({izquierda}, {derecha}, '{node.metric}')"

    @staticmethod
    def _literal(valor):
        if isinstance(valor, Point):
            return PrintVisitor().visit_Point(valor)
        return "'" + valor.replace("'", "''") + "'" if isinstance(valor, str) else str(valor)

    def visit_BeginTransaction(self, node):
        return "BEGIN TRANSACTION"

    def visit_EndTransaction(self, node):
        return "END TRANSACTION"

    def visit_CreateTable(self, node):
        columnas = ", ".join(c.accept(self) for c in node.columns)
        sql = f"CREATE TABLE {node.table} ({columnas})"
        if node.index_kind is not None:
            sql += f" USING {node.index_kind}"
        return sql

    def visit_ColumnDef(self, node):
        tam = f"({node.size})" if node.size is not None else ""
        sql = f"{node.name} {node.type}{tam}"
        if node.primary_key:
            sql += " PRIMARY KEY"
        if node.not_null:
            sql += " NOT NULL"
        return sql

    def visit_Update(self, node):
        asignaciones = ", ".join(f"{c} = {self._literal(v)}" for c, v in node.assignments)
        sql = f"UPDATE {node.table} SET {asignaciones}"
        if node.where is not None:
            sql += " WHERE " + node.where.accept(self)
        return sql

    def visit_Explain(self, node):
        prefijo = "EXPLAIN ANALYZE " if node.analyze else "EXPLAIN "
        return prefijo + node.statement.accept(self)

    def visit_Analyze(self, node):
        return f"ANALYZE {node.table}"
