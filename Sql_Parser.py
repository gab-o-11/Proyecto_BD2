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


    def parse_program(self):
        pass

    def _statement(self):
        pass

    def _select(self):
        pass

    def _insert(self):
        pass

    ## delete -> DELETE FROM IDENTIFIER WHERE condition
    def _delete(self):
        self._expect(TokenType.DELETE, "FROM")
        tabla = self._expect(TokenType.IDENTIFIER, "nombre de la tabla").lexeme
        self._expect(TokenType.WHERE, "WHERE")
        condicion = self._condition()
        return ("delete", tabla, condicion)


    ## condition -> IDENTIFIER comp_op value
    def _condition(self):
        columna = self._expect(TokenType.IDENTIFIER, "nombre de la tabla").lexeme

        if self._match(COMPARISON_OPS):
            operador = self.previous.lexeme
            valor = self._value()
            return ("condition",columna,operador, valor)


        raise ParseError(
            f"Línea {self.current.line}: se esperaba un símbolo de comparacion"
            f"se encontró '{self.current.lexeme}'"
        )

    ## value -> INT | FLOAT | STRING
    def _value(self):
        if self._match(VALUE_TYPES):
            return self.previous.lexeme
        raise ParseError(
            f"Línea {self.current.line}: se esperaba un INT, FLOAT, STRING, "
            f"se encontró '{self.current.lexeme}'"
        )