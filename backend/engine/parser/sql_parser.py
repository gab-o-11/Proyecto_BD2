from .scanner import Scanner, LexicalError
from .tokens import TokenType
from .nodes import BeginTransaction, ColumnDef, Compare, CreateTable, Delete,EndTransaction, Insert, Select, Update


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

    # statement -> select | insert | delete | update | create | begin_tx | end_tx
    def _statement(self):
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

    # select -> SELECT select_list FROM IDENTIFIER [ where ] [ group ] [ order ]
    def _select(self):
        if self._match(TokenType.STAR):
            columnas = None
            agregados = None
        else:
            columnas = []
            agregados = []
            self._select_item(columnas, agregados)
            while self._match(TokenType.COMMA):
                self._select_item(columnas, agregados)
            if not agregados:
                agregados = None

        self._expect(TokenType.FROM, "FROM")
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de tabla").lexeme

        condicion = None
        if self._match(TokenType.WHERE):
            condicion = self._condition()

        group_by = None
        if self._match(TokenType.GROUP):
            self._expect(TokenType.BY, "BY")
            group_by = self._expect(TokenType.IDENTIFIER, "nombre de columna").lexeme

        order_by = None
        if self._match(TokenType.ORDER):
            self._expect(TokenType.BY, "BY")
            order_by = self._expect(TokenType.IDENTIFIER, "nombre de columna").lexeme

        return Select(tabla, columnas, where=condicion, group_by=group_by, order_by=order_by, aggregates=agregados)

    # select_item -> IDENTIFIER '(' ( '*' | IDENTIFIER ) ')' | IDENTIFIER
    def _select_item(self, columnas, agregados):
        nombre = self._expect(TokenType.IDENTIFIER, "'*' o nombre de columna").lexeme
        if not self._match(TokenType.LPAREN):
            columnas.append(nombre)
            return
        func = nombre.upper()
        if func not in AGGREGATE_FUNCS:
            raise ParseError(
                f"Línea {self.current.line}: función de agregación desconocida '{nombre}'"
            )
        if self._match(TokenType.STAR):
            arg = None
        else:
            arg = self._expect(TokenType.IDENTIFIER, "nombre de columna").lexeme
        self._expect(TokenType.RPAREN, "')'")
        agregados.append((func.lower(), arg))


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
        else:
            raise ParseError(
                f"Línea {self.current.line}: se esperaba un tipo (INT, FLOAT, VARCHAR o DATE), "
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
        columna = self._expect(TokenType.IDENTIFIER, "nombre de la tabla").lexeme

        if self._match(*COMPARISON_OPS):
            operador = self.previous.lexeme
            valor = self._value()
            return Compare(columna, operador, valor)

        raise ParseError(
            f"Línea {self.current.line}: se esperaba un símbolo de comparacion"
            f"se encontró '{self.current.lexeme}'"
        )

    # value -> INT | FLOAT | STRING
    def _value(self):
        if self._match(TokenType.INT):
            return int(self.previous.lexeme)
        if self._match(TokenType.FLOAT):
            return float(self.previous.lexeme)
        if self._match(TokenType.STRING):
            return self.previous.lexeme[1:-1]
        raise ParseError(
            f"Línea {self.current.line}: se esperaba un valor (número o cadena), "
            f"se encontró '{self.current.lexeme}'"
        )
