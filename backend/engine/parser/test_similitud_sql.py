from .scanner import Scanner
from .sql_parser import ParseError, Parser
from .nodes import And, SimilarTo
from .visitor import PrintVisitor


def _parse(sql):
    return Parser(Scanner(sql)).parse_program()


def _ida_y_vuelta(sql):
    ast = _parse(sql)
    assert ast == _parse(PrintVisitor().render(ast)), sql
    return ast[0]


def _rechaza(sql):
    try:
        _parse(sql)
    except ParseError:
        return
    raise AssertionError(f"debía rechazarse: {sql}")


def _similar_to():
    nodo = _ida_y_vuelta("SELECT * FROM imagenes WHERE SIMILAR_TO('foto_consulta.jpg', k=10);")
    assert nodo.where == SimilarTo("foto_consulta.jpg", 10)
    nodo = _ida_y_vuelta("SELECT * FROM imagenes WHERE tipo = 'a' AND similar_to('it''s.jpg', K=5);")
    assert isinstance(nodo.where, And) and nodo.where.conditions[1] == SimilarTo("it's.jpg", 5)
    for sql in [
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg')",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', 10)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', x=10)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', k=0)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', k=-1)",
        "SELECT * FROM t WHERE SIMILAR_TO('a.jpg', k=1.5)",
        "SELECT * FROM t WHERE SIMILAR_TO(columna, k=5)",
        "SELECT * FROM t ORDER BY SIMILAR_TO('a.jpg', k=5)",
    ]:
        _rechaza(sql)


def main():
    _similar_to()
    print("OK: SQL de similitud")


if __name__ == "__main__":
    main()
