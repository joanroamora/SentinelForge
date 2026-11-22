"""Bounded, standalone AST worker; input is data and is never imported or executed.

Run with ``python -I -S path/to/_scan_worker.py``. Only stdlib imports belong here.
Module aliases ignore unassigned parameters of unrelated named functions;
other binding and mutation checks remain conservative. Function-local
imports must be direct body statements before the call in the same function;
rebindings in that function suppress them. Closures and conditional imports
remain outside this bounded resolver.
Assigned callables allow one direct module/function assignment from a stable import;
chains, conditional captures and competing bindings remain outside that extension.
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


def _aliases(tree: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef,
             nodes: list[ast.AST], parameter_owners: dict | None = None,
             visible_functions: frozenset | None = None) -> dict[str, tuple[str, int, int]]:
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
            owner = None if parameter_owners is None else parameter_owners.get(node)
            if owner is not None and visible_functions is not None and owner not in visible_functions:
                continue
            blocked.add(node.arg)
        elif isinstance(node, (
            ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
            ast.ExceptHandler, ast.MatchAs, ast.MatchStar,
        )) and node.name is not None and node is not tree:
            blocked.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            blocked.add(node.rest)
        elif isinstance(node, TYPE_PARAMETERS):
            blocked.add(node.name)
        elif not isinstance(tree, ast.Module) and isinstance(node, (ast.Global, ast.Nonlocal)):
            blocked.update(node.names)
    return {name: target for name, target in aliases.items() if name not in blocked}


def _assigned_aliases(tree: ast.Module | ast.FunctionDef | ast.AsyncFunctionDef, nodes: list[ast.AST],
                     imports: dict[str, tuple[str, int, int]], parameter_owners: dict | None,
                     visible_functions: frozenset) -> dict[str, tuple[str, int, int]]:
    """Capture one imported callable; its only store must be this direct assignment."""
    candidates: dict[str, tuple[str, int, int, ast.Name]] = {}
    blocked: set[str] = set()
    for statement in tree.body:
        if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)):
            continue
        value = statement.value
        root = value.id if isinstance(value, ast.Name) else (
            value.value.id if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name)
            else None)
        imported = imports.get(root)
        if imported is None or imported[1:] >= (statement.lineno, statement.col_offset):
            continue
        target = imported[0] if isinstance(value, ast.Name) else (
            value.attr if imported[0] == "module" else None)
        if target not in SUBPROCESS_FUNCTIONS:
            continue
        name = statement.targets[0].id
        if name in candidates:
            blocked.add(name)
        candidates[name] = target, statement.lineno, statement.col_offset, statement.targets[0]
    if not candidates:
        return {}
    for node in nodes:
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            candidate = candidates.get(node.id)
            if candidate is not None and node is not candidate[3]:
                blocked.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if any(alias.name == "*" for alias in node.names):
                return {}
            blocked.update(_import_bindings(node))
        elif isinstance(node, ast.arg):
            owner = None if parameter_owners is None else parameter_owners.get(node)
            if owner is None or owner in visible_functions:
                blocked.add(node.arg)
        elif isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            root = _attribute_root(node)
            if root is not None:
                blocked.add(root)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                               ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name is not None and node is not tree:
            blocked.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            blocked.add(node.rest)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            blocked.update(node.names)
        elif isinstance(node, TYPE_PARAMETERS):
            blocked.add(node.name)
    return {name: candidate[:3] for name, candidate in candidates.items() if name not in blocked}


def _function_body_scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    while node in parents:
        parent = parents[node]
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent if node in parent.body else None
        if isinstance(parent, (ast.ClassDef, ast.Lambda, ast.ListComp, ast.SetComp,
                               ast.DictComp, ast.GeneratorExp)):
            return None
        node = parent
    return None


def _parameter_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
        if isinstance(node, ast.Lambda):
            return None
    return None


def _enclosing_functions(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> frozenset:
    owners = set()
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owners.add(node)
    return frozenset(owners)


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
        parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
        parameter_owners = {node: _parameter_function(node, parents) for node in nodes if isinstance(node, ast.arg)}
        captured_imports = _aliases(tree, nodes, parameter_owners, frozenset())
        module_imports = {}
        module_aliases = {}
        local_aliases = {}
        mutated = {_attribute_root(node) for node in nodes if isinstance(node, (ast.Attribute, ast.Subscript))
                   and isinstance(node.ctx, (ast.Store, ast.Del))}
        signals = []
        for node in nodes:
            if not isinstance(node, ast.Call) or not any(
                keyword.arg == "shell" and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True for keyword in node.keywords
            ):
                continue
            target = None
            visible_functions = _enclosing_functions(node, parents)
            if visible_functions not in module_aliases:
                module_imports[visible_functions] = _aliases(tree, nodes, parameter_owners, visible_functions)
                module_aliases[visible_functions] = (
                    module_imports[visible_functions] |
                    _assigned_aliases(tree, nodes, captured_imports, parameter_owners, visible_functions)
                )
            scope = _function_body_scope(node, parents)
            if scope is not None and scope not in local_aliases:
                scope_nodes = list(ast.walk(scope))
                direct = _aliases(scope, scope_nodes)
                captured = _assigned_aliases(scope, scope_nodes,
                    module_imports[visible_functions] | direct, None, frozenset())
                local_aliases[scope] = {name: value for name, value in (direct | captured).items()
                                       if name not in mutated}
            candidates = module_aliases[visible_functions] | local_aliases.get(scope, {})
            if isinstance(node.func, ast.Name):
                candidate = candidates.get(node.func.id)
                if candidate is not None and candidate[0] in SUBPROCESS_FUNCTIONS and (
                    candidate[1:] <= (node.lineno, node.col_offset)
                ):
                    target = candidate[0]
            elif (
                isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.attr in SUBPROCESS_FUNCTIONS
            ):
                candidate = candidates.get(node.func.value.id)
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
