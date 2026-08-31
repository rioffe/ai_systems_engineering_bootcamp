# pyright: reportMissingImports=false
from __future__ import annotations

import ast
import operator
from decimal import Decimal
from typing import Any, Callable

from .errors import ConstraintError

_BINOPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv
}
_CMPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.In: operator.contains,
}


def _value(node: ast.AST, fields: dict[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        if node.id not in fields:
            raise ConstraintError(f"missing constraint field: {node.id}")
        return fields[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool, type(None))):
        return Decimal(str(node.value)) if isinstance(node.value, (int, float)) else node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_value(x, fields) for x in node.elts]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        try:
            return _BINOPS[type(node.op)](_value(node.left, fields), _value(node.right, fields))
        except ZeroDivisionError as exc:
            raise ConstraintError("constraint division by zero") from exc
    raise ConstraintError("unsafe constraint expression")


def _evaluate(node: ast.AST, fields: dict[str, Any]) -> bool:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        values = [_evaluate(x, fields) for x in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        operation = _CMPS.get(type(node.ops[0]))
        if operation is None:
            raise ConstraintError("unsupported constraint comparison")
        left, right = _value(node.left, fields), _value(node.comparators[0], fields)
        return operation(right, left) if isinstance(node.ops[0], ast.In) else operation(left, right)
    raise ConstraintError("constraint must be a comparison or boolean expression")


def compile_constraint(expression: str):
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ConstraintError(f"invalid constraint syntax: {exc.msg}") from exc
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Name, ast.Load,
               ast.Constant, ast.List, ast.Tuple, ast.Set, ast.BinOp, ast.Add, ast.Sub,
               ast.Mult, ast.Div, ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq, ast.In)
    if any(not isinstance(node, allowed) for node in ast.walk(tree)):
        raise ConstraintError("unsafe constraint expression")
    def check(fields: dict[str, Any]) -> tuple[bool, str]:
        try:
            return _evaluate(tree.body, fields), expression
        except ConstraintError:
            raise
        except Exception as exc:
            raise ConstraintError(f"constraint evaluation failed: {exc}") from exc
    return check


def check_constraints(fields: dict[str, Any], expressions: list[str] | tuple[str, ...]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    for expression in expressions:
        try:
            ok, _ = compile_constraint(expression)(fields)
        except ConstraintError as exc:
            reasons.append(str(exc))
            continue
        if not ok:
            reasons.append(f"constraint failed: {expression}")
    return not reasons, tuple(reasons)
