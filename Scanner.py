from tokens import KEYWORDS, Token, TokenType


class LexicalError(Exception):
    pass


class Scanner:
    def __init__(self, source: str):
        self.source = source
        self.start = 0
        self.current = 0
        self.line = 1

    def next_token(self) -> Token:
        # TODO
        pass