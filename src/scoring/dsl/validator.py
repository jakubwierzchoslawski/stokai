"""DSL semantic validator.

Walks the AST and verifies every IdentifierNode refers to a known parameter or
built-in function name.  Returns a ValidationResult rather than raising so that
callers can accumulate multiple errors.

Accepts IParameterCatalog (injected) for parameter lookup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

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
# Built-in functions — always valid regardless of catalog
# ---------------------------------------------------------------------------

BUILTIN_FUNCTIONS: frozenset[str] = frozenset(
    {"IF", "RANK", "ZSCORE", "PERCENTILE", "MIN", "MAX", "ABS", "LOG"}
)


# ---------------------------------------------------------------------------
# Catalog protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class IParameterCatalog(Protocol):
    async def get_enabled_parameters(self, tenant_id: UUID) -> list[str]: ...
    async def get_parameter_definition(self, name: str, tenant_id: UUID) -> dict | None: ...


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class DslValidator:
    """Semantic validator for DSL AST trees.

    Usage (async)::

        catalog = MyParameterCatalog()
        validator = DslValidator(catalog)
        result = await validator.validate(ast, tenant_id=UUID("..."))
    """

    def __init__(self, catalog: IParameterCatalog) -> None:
        self._catalog = catalog

    async def validate(self, ast: AstNode, tenant_id: UUID) -> ValidationResult:
        """Walk *ast* and check every identifier against the parameter catalog.

        Built-in function names are always accepted.  Identifiers used in
        function-call position are validated as function names; identifiers in
        value position are validated against the enabled parameter list.
        """
        enabled = set(await self._catalog.get_enabled_parameters(tenant_id))
        result = ValidationResult(valid=True)
        self._walk(ast, enabled, result, in_function_position=False)
        return result

    # ------------------------------------------------------------------
    # AST walker
    # ------------------------------------------------------------------

    def _walk(
        self,
        node: AstNode,
        enabled_params: set[str],
        result: ValidationResult,
        in_function_position: bool,
    ) -> None:
        if isinstance(node, NumberLiteral):
            return
        if isinstance(node, StringLiteral):
            return
        if isinstance(node, IdentifierNode):
            name = node.name
            if in_function_position:
                if name.upper() not in BUILTIN_FUNCTIONS:
                    result.add_error(
                        f"Unknown function: {name!r}. "
                        f"Built-in functions are: {sorted(BUILTIN_FUNCTIONS)}"
                    )
            else:
                if name not in enabled_params:
                    result.add_error(
                        f"Unknown parameter: {name!r}. "
                        f"Enable it via the parameter catalog first."
                    )
            return
        if isinstance(node, BinaryOp):
            self._walk(node.left, enabled_params, result, False)
            self._walk(node.right, enabled_params, result, False)
            return
        if isinstance(node, UnaryOp):
            self._walk(node.operand, enabled_params, result, False)
            return
        if isinstance(node, FunctionCall):
            # Validate the function name
            if node.name.upper() not in BUILTIN_FUNCTIONS:
                result.add_error(
                    f"Unknown function: {node.name!r}. "
                    f"Built-in functions are: {sorted(BUILTIN_FUNCTIONS)}"
                )
            for arg in node.positional_args:
                self._walk(arg, enabled_params, result, False)
            for _kw_name, kw_val in node.keyword_args:
                self._walk(kw_val, enabled_params, result, False)
            return
        if isinstance(node, TimeSeriesIndex):
            if node.parameter not in enabled_params:
                result.add_error(
                    f"Unknown parameter in time-series index: {node.parameter!r}."
                )
            return
        if isinstance(node, ConditionalExpr):
            self._walk(node.condition, enabled_params, result, False)
            self._walk(node.then_expr, enabled_params, result, False)
            self._walk(node.else_expr, enabled_params, result, False)
            return
        # Unhandled node type — treat as non-fatal warning via error
        result.add_error(f"Unrecognized AST node type: {type(node).__name__}")
