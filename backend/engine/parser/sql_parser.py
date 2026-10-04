import math
import sys
from .scanner import Scanner, LexicalError
from .tokens import TokenType
from .nodes import Analyze, BeginTransaction, ColumnDef, Compare, CreateTable, Delete, Distance, EndTransaction, Explain, Insert, Join, Point, Polygon, Intersection, Select, Update, aggregate_name, Between


class ParseError(Exception):
    pass

COMPARISON_OPS = (
    TokenType.EQUAL,
    TokenType.NOT_EQUAL,
    TokenType.LESS,
    TokenType.LESS_EQUAL,
    TokenType.GREATER,
    TokenType.GREATER_EQUAL,
)

VALUE_TYPES = (TokenType.INT, TokenType.FLOAT, TokenType.STRING)

AGGREGATE_FUNCS = ("COUNT", "SUM", "AVG", "MIN", "MAX")

INDEX_KINDS = ("HASH", "BPLUS", "BPLUS_CLUSTERED")

class Parser:
    def __init__(self, scanner: Scanner):
        self.scanner = scanner
        self.previous = None
        self.current = scanner.next_token()

    ## Funciones para recorrer

    def _check(self, *types) -> bool:
        return self.current.type in types

    def _advance(self):
        self.previous = self.current
        if self.current.type != TokenType.EOF:
            self.current = self.scanner.next_token()
        return self.previous

    def _match(self, *types):
        if self._check(*types):
            self._advance()
            return True
        return False

    def _expect(self, ttype, what):
        if self._check(ttype):
            return self._advance()
        raise ParseError(
            f"Línea {self.current.line}: se esperaba {what}, "
            f"se encontró '{self.current.lexeme}'"
        )

    # program -> statement { ';' statement } [ ';' ] EOF
    def parse_program(self):
        sentencias = [self._statement()]
        while self._match(TokenType.SEMICOLON):
            if self._check(TokenType.EOF):
                break
            sentencias.append(self._statement())
        self._expect(TokenType.EOF, "';' o fin de la consulta")
        return sentencias

    # statement -> EXPLAIN [ ANALYZE ] statement | ANALYZE IDENTIFIER | select | insert | delete | update | create | begin_tx | end_tx
    def _statement(self):
        if self._match(TokenType.EXPLAIN):
            analyze = self._match(TokenType.ANALYZE)
            if self._check(TokenType.EXPLAIN):
                raise ParseError(f"Línea {self.current.line}: EXPLAIN no se puede anidar")
            return Explain(self._statement(), analyze)
        if self._match(TokenType.ANALYZE):
            tabla = self._expect(TokenType.IDENTIFIER, "nombre de tabla").lexeme
            return Analyze(tabla)
        if self._match(TokenType.SELECT):
            return self._select()
        if self._match(TokenType.INSERT):
            return self._insert()
        if self._match(TokenType.DELETE):
            return self._delete()
        if self._match(TokenType.CREATE):
            return self._create_table()
        if self._match(TokenType.UPDATE):
            return self._update()
        if self._match(TokenType.BEGIN):
            self._expect(TokenType.TRANSACTION, "TRANSACTION")
            return BeginTransaction()
        if self._match(TokenType.END):
            self._expect(TokenType.TRANSACTION, "TRANSACTION")
            return EndTransaction()
        raise ParseError(
            f"Línea {self.current.line}: se esperaba SELECT, INSERT o DELETE, "
            f"se encontró '{self.current.lexeme}'"
        )

    # select -> SELECT select_list FROM table [alias] [JOIN table [alias] ON col = col] [where] [group] [order]
    def _select(self):
        projection = None
        if self._match(TokenType.STAR):
            columnas = None
            agregados = None
        else:
            columnas = []
            agregados = []
            projection = [self._select_item(columnas, agregados)]
            while self._match(TokenType.COMMA):
                projection.append(self._select_item(columnas, agregados))
            if not agregados:
                agregados = None

        self._expect(TokenType.FROM, "FROM")
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de tabla").lexeme
        alias = self._table_alias()
        join = None
        inner = self._match(TokenType.INNER)
        if inner:
            self._expect(TokenType.JOIN, "JOIN")
        if inner or self._match(TokenType.JOIN):
            otra = self._expect(TokenType.IDENTIFIER, "nombre de tabla").lexeme
            otro_alias = self._table_alias()
            self._expect(TokenType.ON, "ON")
            izquierda = self._column_name()
            self._expect(TokenType.EQUAL, "'=' en JOIN")
            derecha = self._column_name()
            join = Join(otra, izquierda, derecha, otro_alias)

        condicion = None
        if self._match(TokenType.WHERE):
            condicion = self._condition()

        group_by = None
        if self._match(TokenType.GROUP):
            self._expect(TokenType.BY, "BY")
            group_by = self._column_name()

        order_by = None
        order_desc = False
        if self._match(TokenType.ORDER):
            self._expect(TokenType.BY, "BY")
            order_by = self._expression()
            if isinstance(order_by, Intersection):
                raise ParseError("INTERSECTA solo se admite en WHERE")
            order_desc = self._match(TokenType.DESC)
            if not order_desc:
                self._match(TokenType.ASC)

        limit = None
        if self._match(TokenType.LIMIT):
            token = self._expect(TokenType.INT, "entero no negativo para LIMIT")
            limit = int(token.lexeme)
            if not 0 <= limit <= sys.maxsize:
                raise ParseError(f"Línea {token.line}: LIMIT debe ser un entero entre 0 y {sys.maxsize}")

        return Select(tabla, columnas, where=condicion, group_by=group_by, order_by=order_by,
                      aggregates=agregados, order_desc=order_desc, table_alias=alias, join=join, projection=projection, limit=limit)

    def _expression(self):
        nombre = self._column_name()
        if not self._match(TokenType.LPAREN):
            return nombre
        if nombre.upper() == "INTERSECTA":
            columna = self._column_name()
            self._expect(TokenType.COMMA, "','")
            nombre_poligono = self._column_name()
            if nombre_poligono.upper() != "POLYGON":
                raise ParseError("INTERSECTA requiere POLYGON(POINT(...), ...)")
            self._expect(TokenType.LPAREN, "'('")
            vertices = [self._point()]
            while self._match(TokenType.COMMA):
                vertices.append(self._point())
            self._expect(TokenType.RPAREN, "')'")
            self._expect(TokenType.RPAREN, "')'")
            return Intersection(columna, Polygon(tuple(vertices)))
        if nombre.upper() != "DISTANCIA":
            raise ParseError(f"Línea {self.previous.line}: función espacial desconocida '{nombre}'")
        izquierda = self._point_operand()
        self._expect(TokenType.COMMA, "','")
        derecha = self._point_operand()
        metrica = "haversine"
        if self._match(TokenType.COMMA):
            token = self._expect(TokenType.STRING, "métrica ('haversine' o 'euclidean')")
            metrica = token.lexeme[1:-1].lower()
            if metrica not in ("haversine", "euclidean"):
                raise ParseError(f"Línea {token.line}: métrica desconocida '{metrica}'")
        self._expect(TokenType.RPAREN, "')'")
        return Distance(izquierda, derecha, metrica)

    def _point_operand(self):
        if self._check(TokenType.POINT):
            return self._point()
        return self._column_name()

    def _point(self):
        self._expect(TokenType.POINT, "POINT")
        self._expect(TokenType.LPAREN, "'('")
        latitude = self._coordinate()
        self._expect(TokenType.COMMA, "','")
        longitude = self._coordinate()
        self._expect(TokenType.RPAREN, "')'")
        return Point(latitude, longitude)

    def _coordinate(self):
        if not self._match(TokenType.INT, TokenType.FLOAT):
            raise ParseError(f"Línea {self.current.line}: se esperaba una coordenada numérica")
        value = float(self.previous.lexeme)
        if not math.isfinite(value):
            raise ParseError(f"Línea {self.previous.line}: la coordenada debe ser finita")
        return value

    def _column_name(self):
        nombre = self._expect(TokenType.IDENTIFIER, "nombre de columna").lexeme
        if self._match(TokenType.DOT):
            nombre += "." + self._expect(TokenType.IDENTIFIER, "nombre de columna después de '.'").lexeme
        return nombre

    def _table_alias(self):
        if self._match(TokenType.AS):
            return self._expect(TokenType.IDENTIFIER, "alias de tabla").lexeme
        if self._check(TokenType.IDENTIFIER):
            return self._advance().lexeme
        return None

    # select_item -> IDENTIFIER '(' ( '*' | IDENTIFIER ) ')' | IDENTIFIER
    def _select_item(self, columnas, agregados):
        nombre = self._column_name()
        if not self._match(TokenType.LPAREN):
            columnas.append(nombre)
            return nombre
        func = nombre.upper()
        if func not in AGGREGATE_FUNCS:
            raise ParseError(
                f"Línea {self.current.line}: función de agregación desconocida '{nombre}'"
            )
        if self._match(TokenType.STAR):
            arg = None
        else:
            arg = self._column_name()
        self._expect(TokenType.RPAREN, "')'")
        agregados.append((func.lower(), arg))
        return aggregate_name(func.lower(), arg)


    # insert -> INSERT INTO IDENTIFIER VALUES '(' value { ',' value } ')'
    def _insert(self):
        self._expect(TokenType.INTO, "INTO")
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de tabla").lexeme
        self._expect(TokenType.VALUES, "VALUES")
        self._expect(TokenType.LPAREN, "'('")
        valores = [self._value()]
        while self._match(TokenType.COMMA):
            valores.append(self._value())
        self._expect(TokenType.RPAREN, "')'")
        return Insert(tabla, valores)

    # delete -> DELETE FROM IDENTIFIER WHERE condition
    def _delete(self):
        self._expect(TokenType.FROM, "FROM")
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de la tabla").lexeme
        self._expect(TokenType.WHERE, "WHERE")
        condicion = self._condition()
        return Delete(tabla, condicion)

    # update -> UPDATE IDENTIFIER SET assignment { ',' assignment } [ WHERE condition ]
    def _update(self):
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de tabla").lexeme
        self._expect(TokenType.SET, "SET")
        asignaciones = [self._assignment()]
        while self._match(TokenType.COMMA):
            asignaciones.append(self._assignment())
        condicion = self._condition() if self._match(TokenType.WHERE) else None
        return Update(tabla, asignaciones, condicion)

    # assignment -> IDENTIFIER '=' value
    def _assignment(self):
        columna = self._expect(TokenType.IDENTIFIER, "nombre de columna").lexeme
        self._expect(TokenType.EQUAL, "'='")
        return (columna, self._value())

    # create -> CREATE TABLE IDENTIFIER '(' column_def { ',' column_def } ')' [ USING IDENTIFIER ]
    def _create_table(self):
        self._expect(TokenType.TABLE, "TABLE")
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de tabla").lexeme
        self._expect(TokenType.LPAREN, "'('")
        columnas = [self._column_def()]
        while self._match(TokenType.COMMA):
            columnas.append(self._column_def())
        self._expect(TokenType.RPAREN, "')'")
        index_column = self._resolver_primary_key(columnas)
        index_kind = None
        if self._match(TokenType.USING):
            token = self._expect(TokenType.IDENTIFIER, "tipo de índice (HASH, BPLUS o BPLUS_CLUSTERED)")
            index_kind = token.lexeme.upper()
            if index_kind not in INDEX_KINDS:
                raise ParseError(
                    f"Línea {token.line}: tipo de índice desconocido '{token.lexeme}'"
                )
        return CreateTable(tabla, columnas, index_column=index_column, index_kind=index_kind)

    # type       -> INT_TYPE | FLOAT_TYPE | VARCHAR_TYPE '(' INT ')'
    def _column_def(self):
        nombre = self._expect(TokenType.IDENTIFIER, "nombre de columna").lexeme
        if self._match(TokenType.INT_TYPE):
            tipo, tam = "INT", None
        elif self._match(TokenType.FLOAT_TYPE):
            tipo, tam = "FLOAT", None
        elif self._match(TokenType.VARCHAR_TYPE):
            self._expect(TokenType.LPAREN, "'('")
            tam = int(self._expect(TokenType.INT, "tamaño del VARCHAR").lexeme)
            self._expect(TokenType.RPAREN, "')'")
            tipo = "VARCHAR"
        elif self._match(TokenType.DATE_TYPE):
            tipo, tam = "DATE", None
        elif self._match(TokenType.POINT):
            tipo, tam = "POINT", None
        else:
            raise ParseError(
                f"Línea {self.current.line}: se esperaba un tipo (INT, FLOAT, VARCHAR, DATE o POINT), "
                f"se encontró '{self.current.lexeme}'"
            )
        primary_key, not_null = self._column_constraints()
        return ColumnDef(nombre, tipo, tam, primary_key=primary_key, not_null=not_null)

    # column_constraint -> PRIMARY KEY | NOT NULL   (cero o más, en cualquier orden)
    def _column_constraints(self):
        primary_key = False
        not_null = False
        while True:
            if self._match(TokenType.PRIMARY):
                self._expect(TokenType.KEY, "KEY")
                primary_key = True
            elif self._match(TokenType.NOT):
                self._expect(TokenType.NULL, "NULL")
                not_null = True
            else:
                break
        return primary_key, not_null

    # Toma la única columna PRIMARY KEY como índice de la tabla; error si hay más de una.
    def _resolver_primary_key(self, columnas):
        claves = [c.name for c in columnas if c.primary_key]
        if len(claves) > 1:
            raise ParseError(
                f"Línea {self.current.line}: solo se permite una PRIMARY KEY, "
                f"se declararon {len(claves)} ({', '.join(claves)})"
            )
        return claves[0] if claves else None

    # condition -> IDENTIFIER comp_op value
    def _condition(self):
        columna = self._expression()
        if isinstance(columna, Intersection):
            return columna

        if self._match(*COMPARISON_OPS):
            operador = self.previous.lexeme
            valor = self._value()
            return Compare(columna, operador, valor)

        if self._match(TokenType.BETWEEN):
            bajo = self._value()
            self._expect(TokenType.AND, "AND")
            alto = self._value()
            return Between(columna, bajo, alto)

        raise ParseError(
            f"Línea {self.current.line}: se esperaba un símbolo de comparación, "
            f"se encontró '{self.current.lexeme}'"
        )

    # value -> INT | FLOAT | STRING
    def _value(self):
        if self._check(TokenType.POINT):
            return self._point()
        if self._match(TokenType.INT):
            return int(self.previous.lexeme)
        if self._match(TokenType.FLOAT):
            return float(self.previous.lexeme)
        if self._match(TokenType.STRING):
            return self.previous.lexeme[1:-1].replace("''", "'")
        raise ParseError(
            f"Línea {self.current.line}: se esperaba un valor (número o cadena), "
            f"se encontró '{self.current.lexeme}'"
        )
