"""A bounded integer algorithm language with Python syntax, interpreted without exec/eval.

This is not a sandbox for arbitrary Python. Unknown syntax is rejected before interpretation.
"""

import ast
import re

from morph.sandbox import SandboxFailure, SandboxResult

_BUILTINS = {"sum", "len", "abs", "min", "max"}
_BINARY = (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod)
_COMPARE = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_MAX_INTEGER = 10**12


def _name(node: ast.AST, *, target: bool = False) -> None:
    if not isinstance(node, ast.Name) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", node.id):
        raise SandboxFailure("only plain variable names are allowed")
    if target and node.id in _BUILTINS | {"solve"}:
        raise SandboxFailure("reserved variable name")


def _expression(node: ast.AST) -> None:
    if isinstance(node, ast.Constant):
        if type(node.value) not in (int, bool) or abs(node.value) > _MAX_INTEGER:
            raise SandboxFailure("only bounded integer or boolean constants are allowed")
    elif isinstance(node, ast.Name):
        _name(node)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, _BINARY):
        _expression(node.left)
        _expression(node.right)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
        _expression(node.operand)
    elif isinstance(node, ast.Compare) and all(isinstance(op, _COMPARE) for op in node.ops):
        _expression(node.left)
        for value in node.comparators:
            _expression(value)
    elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        for value in node.values:
            _expression(value)
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _BUILTINS
        and len(node.args) == 1
        and not node.keywords
    ):
        _expression(node.args[0])
    else:
        raise SandboxFailure(f"unsupported expression: {type(node).__name__}")


def _statements(body: list[ast.stmt]) -> None:
    for node in body:
        if isinstance(node, ast.Return) and node.value is not None:
            _expression(node.value)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            _name(node.targets[0], target=True)
            _expression(node.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, _BINARY):
            _name(node.target, target=True)
            _expression(node.value)
        elif isinstance(node, ast.If):
            _expression(node.test)
            _statements(node.body)
            _statements(node.orelse)
        elif isinstance(node, ast.For) and not node.orelse:
            _name(node.target, target=True)
            _expression(node.iter)
            _statements(node.body)
        else:
            raise SandboxFailure(f"unsupported statement: {type(node).__name__}")


def _parse(code: str) -> ast.FunctionDef:
    if type(code) is not str or len(code.encode("utf-8")) > 100_000:
        raise SandboxFailure("invalid code size")
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise SandboxFailure("invalid algorithm syntax") from exc
    pending = [(tree, 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > 2048 or depth > 32:
            raise SandboxFailure("algorithm syntax budget exceeded")
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    body = tree.body
    if len(body) != 1 or not isinstance(body[0], ast.FunctionDef) or body[0].name != "solve":
        raise SandboxFailure("exactly one solve function is required")
    function = body[0]
    args = function.args
    if (
        function.decorator_list
        or getattr(function, "type_params", [])
        or args.posonlyargs
        or args.kwonlyargs
        or args.defaults
        or args.kw_defaults
        or args.vararg
        or args.kwarg
        or len(args.args) != 1
        or args.args[0].arg != "values"
    ):
        raise SandboxFailure("solve must take exactly one values argument")
    # Annotations are syntax only; they are never evaluated.
    if function.returns is not None and not (
        isinstance(function.returns, ast.Name) and function.returns.id == "int"
    ):
        raise SandboxFailure("unsupported return annotation")
    annotation = args.args[0].annotation
    if annotation is not None and not (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "list"
        and isinstance(annotation.slice, ast.Name)
        and annotation.slice.id == "int"
    ):
        raise SandboxFailure("unsupported input annotation")
    if (
        function.body
        and isinstance(function.body[0], ast.Expr)
        and isinstance(function.body[0].value, ast.Constant)
        and type(function.body[0].value.value) is str
    ):
        function.body = function.body[1:]
    _statements(function.body)
    return function


class _Returned(Exception):
    def __init__(self, value):
        self.value = value


class _Machine:
    def __init__(self, values: list[int], max_steps: int):
        self.env = {"values": tuple(values)}
        self.remaining = max_steps

    def step(self):
        self.remaining -= 1
        if self.remaining < 0:
            raise SandboxFailure("algorithm step budget exceeded")

    def integer(self, value):
        if type(value) is not int or abs(value) > _MAX_INTEGER:
            raise SandboxFailure("integer type or magnitude limit exceeded")
        return value

    def sequence(self, value):
        if type(value) is not tuple or len(value) > 1000:
            raise SandboxFailure("only the bounded input sequence may be iterated")
        return value

    def binary(self, op, left, right):
        a, b = self.integer(left), self.integer(right)
        if isinstance(op, ast.Add):
            value = a + b
        elif isinstance(op, ast.Sub):
            value = a - b
        elif isinstance(op, ast.Mult):
            value = a * b
        elif isinstance(op, ast.FloorDiv):
            value = a // b
        else:
            value = a % b
        return self.integer(value)

    def expression(self, node):
        self.step()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.env:
                raise SandboxFailure("undefined algorithm variable")
            return self.env[node.id]
        if isinstance(node, ast.BinOp):
            return self.binary(node.op, self.expression(node.left), self.expression(node.right))
        if isinstance(node, ast.UnaryOp):
            value = self.expression(node.operand)
            if isinstance(node.op, ast.Not):
                return not self.condition(value)
            return (
                self.integer(value)
                if isinstance(node.op, ast.UAdd)
                else self.integer(-self.integer(value))
            )
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self.condition(self.expression(x)) for x in node.values)
            return any(self.condition(self.expression(x)) for x in node.values)
        if isinstance(node, ast.Compare):
            left = self.integer(self.expression(node.left))
            for op, other in zip(node.ops, node.comparators, strict=True):
                right = self.integer(self.expression(other))
                matched = (
                    left == right
                    if isinstance(op, ast.Eq)
                    else left != right
                    if isinstance(op, ast.NotEq)
                    else left < right
                    if isinstance(op, ast.Lt)
                    else left <= right
                    if isinstance(op, ast.LtE)
                    else left > right
                    if isinstance(op, ast.Gt)
                    else left >= right
                )
                if not matched:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            value = self.expression(node.args[0])
            name = node.func.id
            if name == "abs":
                return self.integer(abs(self.integer(value)))
            values = self.sequence(value)
            if name == "len":
                return len(values)
            if name in {"min", "max"} and not values:
                raise SandboxFailure("empty sequence for min/max")
            result = 0 if name == "sum" else values[0]
            for element in values:
                self.step()
                result = (
                    self.integer(result + element)
                    if name == "sum"
                    else min(result, element)
                    if name == "min"
                    else max(result, element)
                )
            return result
        raise SandboxFailure("unvalidated expression")

    def condition(self, value):
        if type(value) not in (bool, int):
            raise SandboxFailure("condition must be boolean or integer")
        return bool(value)

    def assign(self, name, value):
        if name not in self.env and len(self.env) >= 64:
            raise SandboxFailure("variable budget exceeded")
        self.env[name] = value

    def statements(self, body):
        for node in body:
            self.step()
            if isinstance(node, ast.Return):
                raise _Returned(self.expression(node.value))
            if isinstance(node, ast.Assign):
                self.assign(node.targets[0].id, self.expression(node.value))
            elif isinstance(node, ast.AugAssign):
                self.assign(
                    node.target.id,
                    self.binary(node.op, self.expression(node.target), self.expression(node.value)),
                )
            elif isinstance(node, ast.If):
                self.statements(
                    node.body if self.condition(self.expression(node.test)) else node.orelse
                )
            elif isinstance(node, ast.For):
                for value in self.sequence(self.expression(node.iter)):
                    self.step()
                    self.assign(node.target.id, value)
                    self.statements(node.body)


class BoundedRunner:
    runtime = "bounded-integer-v1"
    synthesis_instructions = (
        "The runtime is a bounded integer algorithm language with Python syntax. "
        "Define only solve(values), optionally with list[int] and int annotations. "
        "Use plain assignments, integer arithmetic (+,-,*,//,%), if, for over values, and return. "
        "The only calls are sum, len, abs, min, max with one argument. "
        "No imports, attributes, indexing, comprehensions, while, recursion, I/O or other calls. "
        "Input length <=1000; integer magnitude <=10^12; evaluation has a finite step budget."
    )

    def __init__(self, max_steps: int = 20_000):
        if type(max_steps) is not int or not 1 <= max_steps <= 100_000:
            raise ValueError("invalid step budget")
        self.max_steps = max_steps

    def preflight(self) -> None:
        """No external runtime is required for this restricted language."""

    def validate(self, code: str) -> None:
        _parse(code)

    def run(self, code: str, values: list[int]) -> SandboxResult:
        if (
            type(values) is not list
            or len(values) > 1000
            or any(type(x) is not int or abs(x) > 10**9 for x in values)
        ):
            raise SandboxFailure("invalid bounded input")
        function = _parse(code)
        machine = _Machine(values, self.max_steps)
        try:
            machine.statements(function.body)
        except _Returned as result:
            return SandboxResult(machine.integer(result.value))
        except (ZeroDivisionError, RecursionError) as exc:
            raise SandboxFailure("invalid algorithm arithmetic") from exc
        raise SandboxFailure("algorithm did not return an integer")
