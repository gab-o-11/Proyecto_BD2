from abc import ABC, abstractmethod


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

class PrintVisitor(Visitor):
    def render(self, sentencias) -> str:
        return "\n".join(s.accept(self) + ";" for s in sentencias)

    def visit_Select(self, node):
        columnas = "*" if node.columns is None else ", ".join(node.columns)
        sql = f"SELECT {columnas} FROM {node.table}"
        if node.where is not None:
            sql += " WHERE " + node.where.accept(self)
        if node.group_by is not None:
            sql += f" GROUP BY {node.group_by}"
        if node.order_by is not None:
            sql += f" ORDER BY {node.order_by}"
        return sql

    def visit_Insert(self, node):
        valores = ", ".join(self._literal(v) for v in node.values)
        return f"INSERT INTO {node.table} VALUES ({valores})"

    def visit_Delete(self, node):
        return f"DELETE FROM {node.table} WHERE {node.where.accept(self)}"

    def visit_Compare(self, node):
        return f"{node.column} {node.op} {self._literal(node.value)}"

    @staticmethod
    def _literal(valor):
        return f"'{valor}'" if isinstance(valor, str) else str(valor)

    def visit_BeginTransaction(self, node):
        return "BEGIN TRANSACTION"

    def visit_EndTransaction(self, node):
        return "END TRANSACTION"

    def visit_CreateTable(self, node):
        columnas = ", ".join(c.accept(self) for c in node.columns)
        return f"CREATE TABLE {node.table} ({columnas})"

    def visit_ColumnDef(self, node):
        tam = f"({node.size})" if node.size is not None else ""
        return f"{node.name} {node.type}{tam}"

    def visit_Update(self, node):
        asignaciones = ", ".join(f"{c} = {self._literal(v)}" for c, v in node.assignments)
        sql = f"UPDATE {node.table} SET {asignaciones}"
        if node.where is not None:
            sql += " WHERE " + node.where.accept(self)
        return sql