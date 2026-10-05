"""Safe arithmetic expression parsing and evaluation.

The parser intentionally supports only the calculator language needed by the
assignment. It never evaluates user input as Python code.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


class CalculationError(ValueError):
    """An expression cannot be parsed or evaluated."""


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    position: int


_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")
_OPERATORS = "+-*/()"
_MAX_EXPRESSION_LENGTH = 1000
_MAX_NUMBER_LENGTH = 64
_MAX_TOKEN_COUNT = 256
_MAX_NESTING = 100


def _tokenize(expression: str) -> list[Token]:
    if not isinstance(expression, str):
        raise CalculationError("expression must be a string")
    if not expression.strip():
        raise CalculationError("expression cannot be empty")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise CalculationError("expression is too long")

    tokens: list[Token] = []
    index = 0
    while index < len(expression):
        char = expression[index]
        if char.isspace():
            index += 1
            continue
        if char in _OPERATORS:
            tokens.append(Token(char, char, index))
            index += 1
        elif char.isdigit() or char == ".":
            match = _NUMBER.match(expression, index)
            if match is None:
                raise CalculationError(f"invalid number at position {index}")
            value = match.group(0)
            if len(value) > _MAX_NUMBER_LENGTH:
                raise CalculationError("number is too long")
            tokens.append(Token("NUMBER", value, index))
            index = match.end()
        else:
            raise CalculationError(f"invalid character at position {index}")
        if len(tokens) > _MAX_TOKEN_COUNT:
            raise CalculationError("expression has too many tokens")
    tokens.append(Token("EOF", "", len(expression)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0
        self.depth = 0

    def current(self) -> Token:
        return self.tokens[self.index]

    def take(self, kind: str) -> Token:
        token = self.current()
        if token.kind != kind:
            expected = "number or (" if kind == "PRIMARY" else kind
            raise CalculationError(
                f"expected {expected} at position {token.position}"
            )
        self.index += 1
        return token

    def parse(self) -> float:
        value = self.parse_expression()
        if self.current().kind != "EOF":
            token = self.current()
            raise CalculationError(f"unexpected token at position {token.position}")
        return value

    def parse_expression(self) -> float:
        value = self.parse_term()
        while self.current().kind in ("+", "-"):
            operator = self.current().kind
            self.index += 1
            right = self.parse_term()
            value = value + right if operator == "+" else value - right
            self._check_finite(value)
        return value

    def parse_term(self) -> float:
        value = self.parse_unary()
        while self.current().kind in ("*", "/"):
            operator = self.current().kind
            self.index += 1
            right = self.parse_unary()
            if operator == "*":
                value *= right
            else:
                if right == 0:
                    raise CalculationError("division by zero")
                value /= right
            self._check_finite(value)
        return value

    def parse_unary(self) -> float:
        if self.current().kind == "+":
            self.index += 1
            return self.parse_unary()
        if self.current().kind == "-":
            self.index += 1
            return -self.parse_unary()
        return self.parse_primary()

    def parse_primary(self) -> float:
        token = self.current()
        if token.kind == "NUMBER":
            self.index += 1
            try:
                value = float(token.value)
            except ValueError as error:
                raise CalculationError("invalid number") from error
            self._check_finite(value)
            return value
        if token.kind == "(":
            self.index += 1
            self.depth += 1
            if self.depth > _MAX_NESTING:
                raise CalculationError("parentheses are nested too deeply")
            value = self.parse_expression()
            self.take(")")
            self.depth -= 1
            return value
        raise CalculationError(f"expected number or ( at position {token.position}")

    @staticmethod
    def _check_finite(value: float) -> None:
        if not math.isfinite(value):
            raise CalculationError("result is outside the supported numeric range")


def evaluate(expression: str) -> float:
    """Parse and evaluate an expression using standard arithmetic precedence."""

    return _Parser(_tokenize(expression)).parse()

