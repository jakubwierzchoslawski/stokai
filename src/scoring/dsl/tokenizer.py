"""DSL Lexer: converts a raw formula string into an ordered token stream.

Pure function: tokenize(formula: str) -> list[Token]
Raises DslTokenizeError on any unrecognized character.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DslError(Exception):
    """Base class for all DSL errors."""


class DslTokenizeError(DslError):
    """Raised when the lexer encounters an unrecognized character or sequence."""


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

class TokenType(Enum):
    # Literals
    NUMBER = auto()
    STRING = auto()

    # Identifier (parameter name or function name)
    IDENTIFIER = auto()

    # Arithmetic operators
    PLUS = auto()       # +
    MINUS = auto()      # -
    STAR = auto()       # *
    SLASH = auto()      # /
    CARET = auto()      # ^

    # Comparison operators
    GT = auto()         # >
    LT = auto()         # <
    GTE = auto()        # >=
    LTE = auto()        # <=
    EQ = auto()         # ==
    NEQ = auto()        # !=

    # Logical operators (keywords)
    AND = auto()
    OR = auto()
    NOT = auto()

    # Delimiters
    LPAREN = auto()     # (
    RPAREN = auto()     # )
    LBRACKET = auto()   # [
    RBRACKET = auto()   # ]
    COMMA = auto()      # ,
    EQUALS = auto()     # = (used in keyword args)

    # Sentinel
    EOF = auto()


# ---------------------------------------------------------------------------
# Token dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str  # raw lexeme from source


# ---------------------------------------------------------------------------
# Lexer implementation
# ---------------------------------------------------------------------------

# Keyword → TokenType map (case-sensitive, upper-case keywords)
_KEYWORDS: dict[str, TokenType] = {
    "AND": TokenType.AND,
    "OR": TokenType.OR,
    "NOT": TokenType.NOT,
}

# Multi-character operator patterns ordered longest-first
_MULTI_CHAR_OPS: list[tuple[str, TokenType]] = [
    (">=", TokenType.GTE),
    ("<=", TokenType.LTE),
    ("==", TokenType.EQ),
    ("!=", TokenType.NEQ),
]

# Single-character operator/delimiter map
_SINGLE_CHAR: dict[str, TokenType] = {
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "^": TokenType.CARET,
    ">": TokenType.GT,
    "<": TokenType.LT,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    ",": TokenType.COMMA,
    "=": TokenType.EQUALS,
}

_NUMBER_RE = re.compile(r"\d+(\.\d*)?([eE][+-]?\d+)?")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')  # double-quoted strings


def tokenize(formula: str) -> list[Token]:
    """Convert *formula* into an ordered list of Token objects.

    Raises:
        DslTokenizeError: if an unrecognized character is encountered.
    """
    tokens: list[Token] = []
    pos = 0
    length = len(formula)

    while pos < length:
        # Skip whitespace
        if formula[pos].isspace():
            pos += 1
            continue

        # Number literal (must come before single-char '-' to avoid conflict)
        m = _NUMBER_RE.match(formula, pos)
        if m:
            tokens.append(Token(TokenType.NUMBER, m.group(0)))
            pos = m.end()
            continue

        # String literal (double-quoted)
        m = _STRING_RE.match(formula, pos)
        if m:
            # value is the raw lexeme including quotes
            tokens.append(Token(TokenType.STRING, m.group(0)))
            pos = m.end()
            continue

        # Identifier or keyword
        m = _IDENT_RE.match(formula, pos)
        if m:
            lexeme = m.group(0)
            tok_type = _KEYWORDS.get(lexeme, TokenType.IDENTIFIER)
            tokens.append(Token(tok_type, lexeme))
            pos = m.end()
            continue

        # Multi-character operators (check longest match first)
        matched_multi = False
        for op_str, op_type in _MULTI_CHAR_OPS:
            if formula[pos:pos + len(op_str)] == op_str:
                tokens.append(Token(op_type, op_str))
                pos += len(op_str)
                matched_multi = True
                break
        if matched_multi:
            continue

        # Single-character operators and delimiters
        ch = formula[pos]
        if ch in _SINGLE_CHAR:
            tokens.append(Token(_SINGLE_CHAR[ch], ch))
            pos += 1
            continue

        # Unrecognized character
        raise DslTokenizeError(
            f"Unrecognized character {ch!r} at position {pos} in formula: {formula!r}"
        )

    tokens.append(Token(TokenType.EOF, ""))
    return tokens
