"""DSL recursive-descent parser.

parse(tokens: list[Token]) -> AstNode

Operator precedence (lowest to highest):
  OR → AND → NOT → comparison → additive (+,-) → multiplicative (*,/) →
  exponentiation (^) → unary minus → postfix (function calls, time-series indexing)

Pure function, no I/O. Raises DslParseError on syntax error.
"""
from __future__ import annotations

from typing import Sequence

from src.scoring.dsl.tokenizer import Token, TokenType, DslError
from src.scoring.dsl.ast_nodes import (
    AstNode,
    BinaryOp,
    ConditionalExpr,
    FunctionCall,
    IdentifierNode,
    NumberLiteral,
    StringLiteral,
    TimeSeriesIndex,
    UnaryOp,
)


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class DslParseError(DslError):
    """Raised on a syntactic error in the DSL formula."""


# ---------------------------------------------------------------------------
# Parser state
# ---------------------------------------------------------------------------

class _Parser:
    """Stateful parser — not meant to be reused across calls."""

    def __init__(self, tokens: Sequence[Token]) -> None:
        self._tokens = list(tokens)
        self._pos = 0

    # ------------------------------------------------------------------
    # Token navigation helpers
    # ------------------------------------------------------------------

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, *types: TokenType) -> Token:
        tok = self._peek()
        if tok.type not in types:
            expected = ", ".join(t.name for t in types)
            raise DslParseError(
                f"Expected {expected} but got {tok.type.name} ({tok.value!r})"
            )
        return self._advance()

    def _match(self, *types: TokenType) -> bool:
        return self._peek().type in types

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def parse(self) -> AstNode:
        if self._match(TokenType.EOF):
            raise DslParseError("Formula is empty — cannot parse an empty expression")
        node = self._parse_or()
        if not self._match(TokenType.EOF):
            tok = self._peek()
            raise DslParseError(
                f"Unexpected token {tok.type.name} ({tok.value!r}) after expression"
            )
        return node

    # ------------------------------------------------------------------
    # Grammar rules (lowest → highest precedence)
    # ------------------------------------------------------------------

    def _parse_or(self) -> AstNode:
        left = self._parse_and()
        while self._match(TokenType.OR):
            self._advance()
            right = self._parse_and()
            left = BinaryOp("OR", left, right)
        return left

    def _parse_and(self) -> AstNode:
        left = self._parse_not()
        while self._match(TokenType.AND):
            self._advance()
            right = self._parse_not()
            left = BinaryOp("AND", left, right)
        return left

    def _parse_not(self) -> AstNode:
        if self._match(TokenType.NOT):
            self._advance()
            operand = self._parse_not()
            return UnaryOp("NOT", operand)
        return self._parse_comparison()

    _COMPARISON_OPS = {
        TokenType.GT, TokenType.LT, TokenType.GTE,
        TokenType.LTE, TokenType.EQ, TokenType.NEQ,
    }

    def _parse_comparison(self) -> AstNode:
        left = self._parse_additive()
        if self._match(*self._COMPARISON_OPS):
            op_tok = self._advance()
            right = self._parse_additive()
            return BinaryOp(op_tok.value, left, right)
        return left

    def _parse_additive(self) -> AstNode:
        left = self._parse_multiplicative()
        while self._match(TokenType.PLUS, TokenType.MINUS):
            op_tok = self._advance()
            right = self._parse_multiplicative()
            left = BinaryOp(op_tok.value, left, right)
        return left

    def _parse_multiplicative(self) -> AstNode:
        left = self._parse_exponentiation()
        while self._match(TokenType.STAR, TokenType.SLASH):
            op_tok = self._advance()
            right = self._parse_exponentiation()
            left = BinaryOp(op_tok.value, left, right)
        return left

    def _parse_exponentiation(self) -> AstNode:
        # Right-associative: a ^ b ^ c → a ^ (b ^ c)
        base = self._parse_unary()
        if self._match(TokenType.CARET):
            self._advance()
            exp = self._parse_exponentiation()
            return BinaryOp("^", base, exp)
        return base

    def _parse_unary(self) -> AstNode:
        if self._match(TokenType.MINUS):
            self._advance()
            operand = self._parse_unary()
            return UnaryOp("-", operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> AstNode:
        """Handle function calls and time-series indexing."""
        node = self._parse_primary()

        # Time-series indexing: identifier[offset]
        if isinstance(node, IdentifierNode) and self._match(TokenType.LBRACKET):
            self._advance()  # consume [
            # Expect an optional minus then a number
            negative = False
            if self._match(TokenType.MINUS):
                self._advance()
                negative = True
            num_tok = self._expect(TokenType.NUMBER)
            offset_val = int(float(num_tok.value))
            if negative:
                offset_val = -offset_val
            self._expect(TokenType.RBRACKET)
            return TimeSeriesIndex(parameter=node.name, offset=offset_val)

        return node

    def _parse_primary(self) -> AstNode:
        tok = self._peek()

        # Number literal
        if tok.type == TokenType.NUMBER:
            self._advance()
            return NumberLiteral(float(tok.value))

        # String literal
        if tok.type == TokenType.STRING:
            self._advance()
            return StringLiteral(tok.value)

        # Parenthesised expression
        if tok.type == TokenType.LPAREN:
            self._advance()
            node = self._parse_or()
            self._expect(TokenType.RPAREN)
            return node

        # Identifier: either bare identifier, function call (IF special-cased), or start of time-series
        if tok.type == TokenType.IDENTIFIER:
            self._advance()
            name = tok.value

            # Function call: identifier followed by (
            if self._match(TokenType.LPAREN):
                return self._parse_function_call(name)

            return IdentifierNode(name)

        # IF keyword is lexed as IDENTIFIER already (not a reserved keyword in lexer)
        # but handle the case where the parser receives it as-is.

        # Unexpected token
        raise DslParseError(
            f"Unexpected token {tok.type.name} ({tok.value!r}) — expected an expression"
        )

    def _parse_function_call(self, name: str) -> AstNode:
        """Parse argument list for a function call.

        IF(condition, then, else) is treated as a ConditionalExpr.
        All others become FunctionCall nodes.
        """
        self._expect(TokenType.LPAREN)

        positional: list[AstNode] = []
        keyword: list[tuple[str, AstNode]] = []

        if not self._match(TokenType.RPAREN):
            self._parse_arg_list(positional, keyword)

        self._expect(TokenType.RPAREN)

        if name.upper() == "IF":
            if len(positional) != 3 or keyword:
                raise DslParseError(
                    "IF() requires exactly 3 positional arguments: IF(condition, then, else)"
                )
            return ConditionalExpr(
                condition=positional[0],
                then_expr=positional[1],
                else_expr=positional[2],
            )

        return FunctionCall(
            name=name,
            positional_args=tuple(positional),
            keyword_args=tuple(keyword),
        )

    def _parse_arg_list(
        self,
        positional: list[AstNode],
        keyword: list[tuple[str, AstNode]],
    ) -> None:
        """Parse comma-separated argument list (positional then keyword)."""
        while True:
            # Check for keyword argument: IDENTIFIER = expression
            # Look-ahead: if next is IDENTIFIER and one-after is EQUALS, it's keyword arg
            if (
                self._peek().type == TokenType.IDENTIFIER
                and self._pos + 1 < len(self._tokens)
                and self._tokens[self._pos + 1].type == TokenType.EQUALS
            ):
                kw_name = self._advance().value
                self._advance()  # consume =
                kw_val = self._parse_or()
                keyword.append((kw_name, kw_val))
            else:
                if keyword:
                    raise DslParseError(
                        "Positional arguments must come before keyword arguments"
                    )
                positional.append(self._parse_or())

            if self._match(TokenType.COMMA):
                self._advance()
            else:
                break


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(tokens: Sequence[Token]) -> AstNode:
    """Parse *tokens* into an AST.

    Args:
        tokens: output of :func:`tokenize`.

    Returns:
        Root :class:`AstNode` of the parsed expression.

    Raises:
        DslParseError: on any syntactic error.
    """
    return _Parser(tokens).parse()
