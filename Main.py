from Scanner import LexicalError, Scanner
from Sql_Parser import ParseError, Parser

consultas = [
    "SELECT * FROM alumnos WHERE edad >= 18;",
    "SELECT nombre, edad FROM alumnos ORDER BY edad",
    "SELECT * FROM t WHERE x = 1 GROUP BY ciudad ORDER BY x;",
    "INSERT INTO alumnos VALUES (1, 'Ana', 17.5);",
    "DELETE FROM alumnos WHERE id = 3",
    "INSERT INTO t VALUES (1);\nSELECT * FROM t;",
    "SELECT FROM t",
    "DELETE FROM t",
    "SELECT * FROM t ORDER BY x WHERE y = 1",
    "INSERT INTO t VALUES (1, 2,)",
    "SELECT * FROM t WHERE x = ;",
]

for consulta in consultas:
    print(f"\n--- {consulta!r}")
    try:
        for sentencia in Parser(Scanner(consulta)).parse_program():
            print("   ", sentencia)
    except (ParseError, LexicalError) as e:
        print("    ERROR:", e)