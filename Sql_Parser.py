from scanner import Scanner
from tokens import TokenType


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, scanner: Scanner):
        self.scanner = scanner
        self.previous = None
        self.current = None

    # ---------------- utilidades ----------------
    def _check(self, *types):
        pass

    def _advance(self):
        pass

    def _match(self, *types):
        pass

    def _expect(self, ttype, what):
        pass

    # ---------------- reglas ----------------
    def parse_program(self):
        pass

    def _statement(self):
        pass

    def _select(self):
        pass

    def _insert(self):
        pass

    def _delete(self):
        pass

    def _condition(self):
        pass

    def _value(self):
        pass