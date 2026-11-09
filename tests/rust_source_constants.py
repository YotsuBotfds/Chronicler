"""Read constants from the Rust sources without the native extension.

A test helper (not collected): the parity rows in ``tests/test_ffi_constants.py``
compare Python mirrors with the values the Rust crate declares, parsing the
source text the way ``tests/test_hunger_mortality.py`` does. Paths are relative
to ``chronicler-agents/src``. Every reader raises ``AssertionError`` naming the
item and the file when it finds no match, so a renamed Rust item fails loudly.

Values are evaluated by a small whitelisted evaluator: numeric literals (with
Rust type suffixes and ``_`` separators), ``u8::MAX``-style bounds, unary minus
and ``* / + -``. Anything else is rejected.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

RUST_SRC = Path(__file__).resolve().parents[1] / "chronicler-agents" / "src"

_INT_BOUNDS = {
    "u8::MAX": 0xFF,
    "u16::MAX": 0xFFFF,
    "u32::MAX": 0xFFFF_FFFF,
    "u64::MAX": 0xFFFF_FFFF_FFFF_FFFF,
    "i8::MAX": 0x7F,
    "i16::MAX": 0x7FFF,
    "i32::MAX": 0x7FFF_FFFF,
}
_SUFFIX = re.compile(r"(?<=[0-9.])_?(?:f32|f64|u8|u16|u32|u64|usize|i8|i16|i32|i64|isize)\b")
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def read_source(path: str | Path) -> str:
    """The text of a Rust source file (a seam tests may monkeypatch)."""
    return (RUST_SRC / path).read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _normalize(expr: str) -> str:
    expr = expr.strip()
    for bound, value in _INT_BOUNDS.items():
        expr = re.sub(rf"\b{re.escape(bound)}", str(value), expr)
    expr = _SUFFIX.sub("", expr)
    # Rust allows `1.` and `_` separators; Python accepts `1.` and `1_000`.
    return expr


def evaluate(expr: str) -> float | int:
    """Evaluate a numeric Rust constant expression with a whitelisted AST."""
    tree = ast.parse(_normalize(expr), mode="eval")

    def ev(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = ev(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div, ast.Add, ast.Sub)):
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Add):
                return left + right
            return left - right
        raise ValueError(f"unsupported expression in Rust constant: {expr!r}")

    return ev(tree)


def _literal(expr: str, name: str, path: str | Path):
    """A Rust array literal (nested lists of numbers or strings) as Python lists."""
    text = _normalize(_strip_comments(expr))
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - a Rust form the reader does not know
        raise AssertionError(f"{name} in {path} is not a plain array literal: {exc}") from exc

    def ev(node: ast.AST):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, (ast.List, ast.Tuple)):
            return [ev(item) for item in node.elts]
        if isinstance(node, ast.Constant) and type(node.value) is str:
            return node.value
        return evaluate(ast.unparse(node))

    return ev(tree)


def _is_float_type(rust_type: str) -> bool:
    return rust_type.strip().startswith("f")


def const(path: str | Path, name: str) -> float | int:
    """The value of a scalar ``const``/``pub const`` item; float for ``f32``/``f64``."""
    text = _strip_comments(read_source(path))
    matches = re.findall(
        rf"^\s*(?:pub(?:\([^)]*\))?\s+)?const\s+{re.escape(name)}\s*:\s*([^=]+?)\s*=\s*([^;]+);",
        text,
        re.M,
    )
    if not matches:
        raise AssertionError(f"{name} not found in {path}")
    if len(matches) > 1:
        raise AssertionError(f"{name} declared {len(matches)} times in {path}")
    rust_type, expr = matches[0]
    value = evaluate(expr)
    return float(value) if _is_float_type(rust_type) else int(value)


def enum(path: str | Path, enum_name: str) -> dict[str, int]:
    """Variant -> discriminant of a field-less enum (explicit ``= n`` or declaration order)."""
    text = _strip_comments(read_source(path))
    match = re.search(rf"\benum\s+{re.escape(enum_name)}\s*\{{([^}}]*)\}}", text)
    if not match:
        raise AssertionError(f"{enum_name} not found in {path}")
    variants: dict[str, int] = {}
    nxt = 0
    for raw in match.group(1).split(","):
        item = raw.strip()
        if not item:
            continue
        m = re.fullmatch(r"(?:#\[[^\]]*\]\s*)*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*(.+))?", item, re.S)
        if not m:
            raise AssertionError(f"{enum_name} in {path}: unparseable variant {item!r}")
        nxt = int(evaluate(m.group(2))) if m.group(2) is not None else nxt
        variants[m.group(1)] = nxt
        nxt += 1
    return variants


def array(path: str | Path, name: str) -> list:
    """A ``const``/``static`` array literal (nested lists; numbers or strings)."""
    text = _strip_comments(read_source(path))
    match = re.search(
        rf"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const|static)\s+{re.escape(name)}\s*:\s*[^=]+=\s*(\[.*?\])\s*;",
        text,
        re.M | re.S,
    )
    if not match:
        raise AssertionError(f"{name} not found in {path}")
    return _literal(match.group(1), name, path)


def default_fields(path: str | Path, impl_header: str) -> dict[str, float | int]:
    """``field: value`` pairs of the ``Self { .. }`` in an ``impl Default`` block."""
    text = _strip_comments(read_source(path))
    start = text.find(impl_header)
    if start < 0:
        raise AssertionError(f"{impl_header} not found in {path}")
    match = re.search(r"fn\s+default\s*\(\s*\)\s*->\s*Self\s*\{\s*Self\s*\{(.*?)\}", text[start:], re.S)
    if not match:
        raise AssertionError(f"{impl_header} not found in {path} (no `Self {{ .. }}`)")
    fields: dict[str, float | int] = {}
    for raw in match.group(1).split(","):
        item = raw.strip()
        if not item:
            continue
        m = re.fullmatch(r"([a-z_][a-z0-9_]*)\s*:\s*(.+)", item, re.S)
        if not m:
            raise AssertionError(f"{impl_header} in {path}: unparseable field {item!r}")
        fields[m.group(1)] = evaluate(m.group(2))
    return fields
