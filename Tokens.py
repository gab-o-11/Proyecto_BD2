from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    ## Palabras Reservadas
    SELECT = auto()
    FROM = auto()
    WHERE = auto()
    ORDER = auto()
    GROUP = auto()
    BY = auto()
    INSERT = auto()
    INTO = auto()
    DELETE = auto()
    VALUES = auto()

    ## ID y tipos de datos

    IDENTIFIER = auto()
    FLOAT = auto()
    INT = auto()
    STRING = auto()

    ## Condicionales

    ## operadores y simbolos
    STAR = auto()
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    SEMICOLON = auto()   ## semicolon es ";"
    EQUAL = auto()
    NOT_EQUAL = auto()   ## !=
    LESS = auto()   ## <
    LESS_EQUAL = auto()
    GREATER = auto()   ## >
    GREATER_EQUAL = auto()

    ## Fin
    EOF  = auto() ## se coloca para enlazarlo con el punto 2.1.4

KEYWORDS = {
    "SELECT": TokenType.SELECT,
    "FROM": TokenType.FROM,
    "WHERE": TokenType.WHERE,
    "ORDER": TokenType.ORDER,
    "GROUP": TokenType.GROUP,
    "BY": TokenType.BY,
    "INSERT": TokenType.INSERT,
    "INTO": TokenType.INTO,
    "DELETE": TokenType.DELETE,
    "VALUES": TokenType.VALUES,

}


@dataclass
class Token:
    type: TokenType
    lexeme: str
    line: int