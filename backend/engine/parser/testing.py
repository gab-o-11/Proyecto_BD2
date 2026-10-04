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
SELECT * FROM alumnos WHERE id BETWEEN 1 AND 3;
"""

# Cada una se parsea sola: un error de sintaxis aborta todo el bloque.
INVALIDAS = [
    "SELECT FROM t",
    "DELETE FROM t",
    "SELECT * FROM t ORDER BY x WHERE y = 1",
    "INSERT INTO t VALUES (1, 2,)",
    "UPDATE alumnos SET promedio 5",
    "UPDATE SET x = 1",
    "CREATE TABLE t (a BLOB)",
    "CREATE TABLE t ()",
    "BEGIN;",
    "SELECT * FROM t WHERE n = 'Ana",
    "SELECT # FROM t",
    "SELECT * FROM t WHERE id BETWEEN 1",
    "SELECT * FROM t WHERE id BETWEEN 1 10",
    "SELECT * FROM t WHERE id BETWEEN AND 10",
]

# Cada una debe parsear, imprimirse con PrintVisitor y volver a parsear
# al MISMO AST. Si el visitor olvida imprimir un campo, el AST cambia.
# Solo se parsean, no se ejecutan: no dependen del executor.
IDA_Y_VUELTA = [
    "SELECT COUNT(*) FROM t",
    "SELECT ciudad, AVG(sueldo), MAX(edad) FROM t GROUP BY ciudad ORDER BY ciudad",
    "CREATE TABLE t (id INT PRIMARY KEY NOT NULL, n VARCHAR(10), f DATE) USING BPLUS",
    "CREATE TABLE t (a DATE)",
    "EXPLAIN ANALYZE SELECT * FROM t WHERE id >= 3",
    "UPDATE t SET a = 1, b = 'x'",
    "INSERT INTO t VALUES (1, 2.5, 'hola')",
    "SELECT * FROM t WHERE id BETWEEN 10 AND 20",
    "SELECT * FROM t WHERE id BETWEEN -5 AND 5 ORDER BY id DESC LIMIT 3",
    "DELETE FROM t WHERE fecha BETWEEN '2026-01-01' AND '2026-12-31'",
]


def probar_ida_y_vuelta():
    print("=" * 60)
    print("IDA Y VUELTA  AST -> SQL -> AST")
    print("=" * 60)
    correctas = 0
    for consulta in IDA_Y_VUELTA:
        # parse_program devuelve una lista; aquí cada consulta es UNA sentencia
        [original] = Parser(Scanner(consulta)).parse_program()
        texto = PrintVisitor().render([original])
        try:
            [reparseado] = Parser(Scanner(texto)).parse_program()
        except (ParseError, LexicalError) as e:
            print(f"  FALLA {consulta!r}")
            print(f"     el texto impreso no parsea: {texto!r}")
            print(f"     {e}")
            continue
        if original == reparseado:   # @dataclass compara campo por campo
            correctas += 1
        else:
            print(f"  FALLA {consulta!r}")
            print(f"     impreso:    {texto!r}")
            print(f"     original:   {original}")
            print(f"     reparseado: {reparseado}")
    print(f"\n{correctas} de {len(IDA_Y_VUELTA)} pasaron la ida y vuelta\n")


def main():
    probar_ida_y_vuelta()

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