from .scanner import Scanner
from .sql_parser import Parser
from .visitor import PrintVisitor
from .executor import Executor, Table

catalogo = {
    "alumnos": Table("alumnos", ["id", "nombre", "edad"],
                     index_column="id", index_kind="HASH")
}

consultas = """
BEGIN TRANSACTION;
INSERT INTO alumnos VALUES (1, 'Ana', 20);
INSERT INTO alumnos VALUES (2, 'Luis', 17);
DELETE FROM alumnos WHERE id = 2;
END TRANSACTION;
SELECT * FROM alumnos;
END TRANSACTION;
BEGIN TRANSACTION;
BEGIN TRANSACTION;
"""

ast = Parser(Scanner(consultas)).parse_program()
print("== SQL reconstruido ==")
print(PrintVisitor().render(ast))
print("\n== Ejecución ==")
Executor(catalogo).execute(ast)