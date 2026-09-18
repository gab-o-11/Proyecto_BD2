from .scanner import Scanner, LexicalError
from .sql_parser import Parser, ParseError
from .visitor import PrintVisitor
from .executor import Executor
from .tokens import TokenType
import tempfile

CONSULTAS = """
CREATE TABLE alumnos (id INT, nombre VARCHAR(20), promedio FLOAT);
INSERT INTO alumnos VALUES (1, 'Ana', 17.5);
INSERT INTO alumnos VALUES (2, 'Luis', 12.0);
INSERT INTO alumnos VALUES (3, 'Rosa', 15.5);
UPDATE alumnos SET promedio = 13.0 WHERE id = 2;
UPDATE alumnos SET nombre = 'Anita', promedio = 18.0 WHERE nombre = 'Ana';
SELECT * FROM alumnos WHERE id = 3;
SELECT nombre, promedio FROM alumnos WHERE promedio >= 13.0 ORDER BY promedio;
SELECT * FROM alumnos GROUP BY promedio;
BEGIN TRANSACTION;
DELETE FROM alumnos WHERE id = 2;
END TRANSACTION;
SELECT * FROM alumnos;
SELECT * FROM cursos;
SELECT xx FROM alumnos;
UPDATE alumnos SET xx = 1;
CREATE TABLE alumnos (id INT);
END TRANSACTION;
"""

# Cada una se parsea sola: un error de sintaxis aborta todo el bloque.
INVALIDAS = [
    "SELECT FROM t",
    "DELETE FROM t",
    "SELECT * FROM t ORDER BY x WHERE y = 1",
    "INSERT INTO t VALUES (1, 2,)",
    "UPDATE alumnos SET promedio 5",
    "UPDATE SET x = 1",
    "CREATE TABLE t (a DATE)",
    "CREATE TABLE t ()",
    "BEGIN;",
    "SELECT * FROM t WHERE n = 'Ana",
    "SELECT # FROM t",
]


def main():
    try:
        ast = Parser(Scanner(CONSULTAS)).parse_program()
    except (ParseError, LexicalError) as e:
        print("El bloque válido no parseó:", e)
        return

    print("=" * 60)
    print("SQL RECONSTRUIDO DESDE EL AST")
    print("=" * 60)
    print(PrintVisitor().render(ast))

    print("\n" + "=" * 60)
    print("EJECUCIÓN")
    print("=" * 60)
    Executor(data_dir=tempfile.mkdtemp()).execute(ast)

    print("\n" + "=" * 60)
    print("DEBEN DAR ERROR (sintáctico o léxico)")
    print("=" * 60)
    correctas = 0
    for consulta in INVALIDAS:
        try:
            Parser(Scanner(consulta)).parse_program()
            print(f"  {consulta!r}\n     NO dio error (mal)")
        except (ParseError, LexicalError) as e:
            print(f"  {consulta!r}\n     {e}")
            correctas += 1
    print(f"\n{correctas} de {len(INVALIDAS)} fueron rechazadas correctamente")


if __name__ == "__main__":
    main()