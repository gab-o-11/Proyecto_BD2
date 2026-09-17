from Scanner import LexicalError, Scanner
from Sql_Parser import ParseError, Parser

CONSULTAS_VALIDAS = [
    "SELECT * FROM alumnos WHERE edad >= 18;",
    "SELECT nombre, edad FROM alumnos ORDER BY edad",
    "SELECT * FROM t WHERE x = 1 GROUP BY ciudad ORDER BY x;",
    "INSERT INTO alumnos VALUES (1, 'Ana', 17.5);",
    "DELETE FROM alumnos WHERE id = 3",
    "INSERT INTO t VALUES (1);\nSELECT * FROM t;",
    "select * from ALUMNOS where NOMBRE = 'Ana';",
]

CONSULTAS_INVALIDAS = [
    "SELECT FROM t",
    "DELETE FROM t",
    "SELECT * FROM t ORDER BY x WHERE y = 1",
    "INSERT INTO t VALUES (1, 2,)",
    "SELECT * FROM t WHERE x = ;",
    "SELECT * FROM t WHERE x 5",
    "SELECT * FROM t GROUP ciudad",
    "SELECT * FROM t WHERE n = 'Ana",
    "SELECT # FROM t",
]


def analizar(consulta: str, se_espera_error: bool) -> bool:
    print(f"\n--- {consulta!r}")
    try:
        sentencias = Parser(Scanner(consulta)).parse_program()
    except (ParseError, LexicalError) as e:
        print(f"    ERROR: {e}")
        return se_espera_error

    for sentencia in sentencias:
        print(f"    {sentencia}")
    return not se_espera_error


def main() -> None:
    print("=" * 60)
    print("CONSULTAS VÁLIDAS (deben parsear)")
    print("=" * 60)
    ok = [analizar(c, se_espera_error=False) for c in CONSULTAS_VALIDAS]

    print("\n" + "=" * 60)
    print("CONSULTAS INVÁLIDAS (deben dar error)")
    print("=" * 60)
    ok += [analizar(c, se_espera_error=True) for c in CONSULTAS_INVALIDAS]

    print(f"\n{sum(ok)} de {len(ok)} pruebas dieron el resultado esperado")


if __name__ == "__main__":
    main()