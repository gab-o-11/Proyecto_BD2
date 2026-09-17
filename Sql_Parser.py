from Scanner import Scanner, LexicalError
from Tokens import TokenType


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

    # statement -> select | insert | delete
    def _statement(self):
        if self._match(TokenType.SELECT):
            return self._select()
        if self._match(TokenType.INSERT):
            return self._insert()
        if self._match(TokenType.DELETE):
            return self._delete()
        raise ParseError(
            f"Línea {self.current.line}: se esperaba SELECT, INSERT o DELETE, "
            f"se encontró '{self.current.lexeme}'"
        )

    # select -> SELECT columns FROM IDENTIFIER [ where ] [ group ] [ order ]
    def _select(self):
        if self._match(TokenType.STAR):
            columnas = None
        else:
            columnas = [self._expect(TokenType.IDENTIFIER, "'*' o nombre de columna").lexeme]
            while self._match(TokenType.COMMA):
                columnas.append(self._expect(TokenType.IDENTIFIER, "nombre de columna").lexeme)

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

        return ("select", tabla, columnas, condicion, group_by, order_by)


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
        return ("insert", tabla, valores)

    ## delete -> DELETE FROM IDENTIFIER WHERE condition
    def _delete(self):
        self._expect(TokenType.FROM, "FROM")
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de la tabla").lexeme
        self._expect(TokenType.WHERE, "WHERE")
        condicion = self._condition()
        return ("delete", tabla, condicion)


    ## condition -> IDENTIFIER comp_op value
    def _condition(self):
        columna = self._expect(TokenType.IDENTIFIER, "nombre de la tabla").lexeme

        if self._match(*COMPARISON_OPS):
            operador = self.previous.lexeme
            valor = self._value()
            return ("condition",columna,operador, valor)


        raise ParseError(
            f"Línea {self.current.line}: se esperaba un símbolo de comparacion"
            f"se encontró '{self.current.lexeme}'"
        )

    ## value -> INT | FLOAT | STRING
    def _value(self):
        if self._match(*VALUE_TYPES):
            return self.previous.lexeme
        raise ParseError(
            f"Línea {self.current.line}: se esperaba un INT, FLOAT, STRING, "
            f"se encontró '{self.current.lexeme}'"
        )