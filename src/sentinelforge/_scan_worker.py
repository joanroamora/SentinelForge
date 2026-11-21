"""Bounded, standalone AST worker; input is data and is never imported or executed.

Run with ``python -I -S path/to/_scan_worker.py``. Only stdlib imports belong here.
Import aliases are recognized only at module level, before the call in source
order. Any visible rebinding of an alias anywhere in the file suppresses it,
conservatively accepting false negatives.
This is a process boundary for parser failures, not an operating-system sandbox.
"""

import ast
import json
import sys

MAX_SOURCE_BYTES = 65_536
MAX_AST_NODES = 20_000
MAX_SIGNALS = 100
SUBPROCESS_FUNCTIONS = frozenset({"run", "Popen", "call", "check_call", "check_output"})
TYPE_PARAMETERS = tuple(
    getattr(ast, name) for name in ("TypeVar", "ParamSpec", "TypeVarTuple") if hasattr(ast, name)
)


def _import_bindings(node: ast.Import | ast.ImportFrom) -> dict[str, str | None]:
    if isinstance(node, ast.Import):
        return {
            alias.asname or alias.name.split(".")[0]: (
                "module" if alias.name == "subprocess" else None
            )
            for alias in node.names
        }
    return {
        alias.asname or alias.name: (
            alias.name
            if node.module == "subprocess" and node.level == 0
            and alias.name in SUBPROCESS_FUNCTIONS
            else None
        )
        for alias in node.names
    }


def _attribute_root(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _aliases(tree: ast.Module, nodes: list[ast.AST]) -> dict[str, tuple[str, int, int]]:
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    allowed_ids = {id(node) for node in imports}
    aliases: dict[str, tuple[str, int, int]] = {}
    blocked: set[str] = set()
    for node in imports:
        for name, target in _import_bindings(node).items():
            if target is None or (name in aliases and aliases[name][0] != target):
                blocked.add(name)
            else:
                aliases.setdefault(name, (target, node.lineno, node.col_offset))

    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # A star import could overwrite every recognized binding.
            if any(alias.name == "*" for alias in node.names):
                return {}
            if id(node) not in allowed_ids:
                blocked.update(_import_bindings(node))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            blocked.add(node.id)
        elif isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            root = _attribute_root(node)
            if root is not None:
                blocked.add(root)
        elif isinstance(node, ast.arg):
            blocked.add(node.arg)
        elif isinstance(node, (
            ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
            ast.ExceptHandler, ast.MatchAs, ast.MatchStar,
        )) and node.name is not None:
            blocked.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            blocked.add(node.rest)
        elif isinstance(node, TYPE_PARAMETERS):
            blocked.add(node.name)
    return {name: target for name, target in aliases.items() if name not in blocked}


def scan_source(raw: bytes) -> dict:
    """Return only bounded locations and canonical call names, never source text."""
    if len(raw) > MAX_SOURCE_BYTES:
        return {"signals": [], "error": "source_too_large"}
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {"signals": [], "error": "invalid_encoding"}
    try:
        tree = ast.parse(source, filename="<local-source>")
        nodes = []
        for node in ast.walk(tree):
            nodes.append(node)
            if len(nodes) > MAX_AST_NODES:
                return {"signals": [], "error": "source_too_complex"}
        aliases = _aliases(tree, nodes)
        signals = []
        for node in nodes:
            if not isinstance(node, ast.Call) or not any(
                keyword.arg == "shell" and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True for keyword in node.keywords
            ):
                continue
            target = None
            if isinstance(node.func, ast.Name):
                candidate = aliases.get(node.func.id)
                if candidate is not None and candidate[0] in SUBPROCESS_FUNCTIONS and (
                    candidate[1:] <= (node.lineno, node.col_offset)
                ):
                    target = candidate[0]
            elif (
                isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.attr in SUBPROCESS_FUNCTIONS
            ):
                candidate = aliases.get(node.func.value.id)
                if candidate is not None and candidate[0] == "module" and (
                    candidate[1:] <= (node.lineno, node.col_offset)
                ):
                    target = node.func.attr
            if target is None:
                continue
            signals.append({
                "line": node.lineno,
                "column": node.col_offset + 1,
                "end_line": node.end_lineno,
                "end_column": node.end_col_offset + 1,
                "call": "subprocess." + target,
            })
            if len(signals) > MAX_SIGNALS:
                return {"signals": [], "error": "too_many_findings"}
        signals.sort(key=lambda item: (item["line"], item["column"]))
        return {"signals": signals, "error": None}
    except (SyntaxError, ValueError):
        return {"signals": [], "error": "invalid_python"}
    except (MemoryError, RecursionError):
        return {"signals": [], "error": "source_too_complex"}


if __name__ == "__main__":
    result = scan_source(sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1))
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
