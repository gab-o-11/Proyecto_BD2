from Tokens import TokenType
from Scanner import LexicalError, Scanner


def probar(consulta: str) -> None:
    print(f"\n--- {consulta!r}")
    scanner = Scanner(consulta)
    try:
        while True:
            token = scanner.next_token()
            print(f"  {token.type.name:15} {token.lexeme!r}  (línea {token.line})")
            if token.type == TokenType.EOF:
                break
    except LexicalError as e:
        print(f"  {e}")


probar("SELECT nombre, edad FROM alumnos WHERE edad >= 18;")
probar("INSERT INTO alumnos VALUES (1, 'Ana', 17.5);")
probar("select * from t where x != 3")
probar("DELETE FROM t\nWHERE id < 5")
probar("SELECT * FROM t WHERE n = 'Ana")
probar("SELECT # FROM t")
probar("   \n\n  ")