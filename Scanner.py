from Tokens import KEYWORDS, Token, TokenType


class LexicalError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(f"Error léxico (línea {line}): {message}")


SYMBOLS = {
    "*": TokenType.STAR,
    ",": TokenType.COMMA,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ";": TokenType.SEMICOLON,
    "=": TokenType.EQUAL,
}

class Scanner:
    def __init__(self, source: str):
        self.source = source
        self.start = 0
        self.current = 0
        self.line = 1


    ## Funciones para avanzar
    def _peek(self, offset: int = 0) -> str:
        pos = self.current + offset
        return self.source[pos] if pos < len(self.source) else ""

    def _advance(self) -> str:
        c = self.source[self.current]
        self.current += 1
        return c

    def _match(self, expected: str) -> bool:
        if self._peek() == expected:
            self.current += 1
            return True
        return False

    def _make(self, ttype: TokenType) -> Token:
        return Token(ttype, self.source[self.start:self.current], self.line)

    ##

    def next_token(self) -> Token:
        while self._peek() in (" ", "\t", "\r", "\n"):
            if self._advance() == "\n":
                self.line += 1

        self.start = self.current

        if self.current >= len(self.source):
            return Token(TokenType.EOF, "", self.line)

        c = self._advance()

        ## Operadores
        if c in SYMBOLS:
            return self._make(SYMBOLS[c])

        if c == "<":
            return self._make(TokenType.LESS_EQUAL if self._match("=") else TokenType.LESS)
        if c == ">":
            return self._make(TokenType.GREATER_EQUAL if self._match("=") else TokenType.GREATER)
        if c == "!":
            if self._match("="):
                return self._make(TokenType.NOT_EQUAL)
            raise LexicalError("se esperaba '=' después de '!'", self.line)

        if c.isdigit():
            return self._number()

        if c.isalpha() or c == "_":
            return self._word()

        if c == "'":
            return self._string()

        raise LexicalError(f"carácter inválido {c!r}", self.line)

    # ---------- reconocedores ----------
    def _number(self) -> Token:
        while self._peek().isdigit():
            self._advance()
        if self._peek() == "." and self._peek(1).isdigit():
            self._advance()
            while self._peek().isdigit():
                self._advance()
            return self._make(TokenType.FLOAT)
        return self._make(TokenType.INT)

    def _word(self) -> Token:
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        palabra = self.source[self.start:self.current].upper()
        return self._make(KEYWORDS.get(palabra, TokenType.IDENTIFIER))

    def _string(self) -> Token:
        while self._peek() != "'":
            if self._peek() == "" or self._peek() == "\n":
                raise LexicalError("cadena sin cerrar", self.line)
            self._advance()
        self._advance()
        return self._make(TokenType.STRING)
