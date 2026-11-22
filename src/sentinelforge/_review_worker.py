"""Independent static recheck. Only stdlib imports; never execute supplied source."""

import ast
import base64
import hashlib
import io
import json
import symtable
import sys
import tokenize

FUNCTIONS = {"run", "Popen", "call", "check_call", "check_output"}


def imported_target(root, call, tree, nodes, symbols, parents):
    """Use compiler symbol tables plus original imports, not the detector's alias resolver."""
    bindings = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    return None
                name = alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import)
                                        else alias.name)
                if name != root:
                    continue
                if isinstance(node, ast.Import):
                    target = "subprocess" if alias.name == "subprocess" else None
                else:
                    target = ("subprocess." + alias.name if node.module == "subprocess" and
                              node.level == 0 and alias.name in FUNCTIONS else None)
                bindings.append((target, (node.lineno, node.col_offset)))
    if not bindings or any(target != bindings[0][0] for target, _ in bindings):
        return None
    if bindings[0][0] is None or not any(position < (call.lineno, call.col_offset) for _, position in bindings):
        return None
    symbol = symbols.lookup(root)
    if not symbol.is_imported() or symbol.is_assigned() or symbol.is_namespace():
        return None
    if not module_binding_visible(root, call, nodes, symbols, parents):
        return None
    for node in nodes:
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            value = node.value
            while isinstance(value, (ast.Attribute, ast.Subscript)):
                value = value.value
            if isinstance(value, ast.Name) and value.id == root:
                return None
    return bindings[0][0]


def module_binding_visible(root, call, nodes, symbols, parents):
    """A compiler-local symbol must not replace the module name at this call."""
    named_functions = {(node.name, node.lineno) for node in nodes
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    visible = set()
    current = call
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visible.add((current.name, current.lineno))
    pending = list(symbols.get_children())
    while pending:
        table = pending.pop()
        pending.extend(table.get_children())
        if root in table.get_identifiers():
            entry = table.lookup(root)
            key = (table.get_name(), table.get_lineno())
            if (table.get_type() == "function" and key in named_functions and key not in visible and
                    entry.is_parameter() and not entry.is_assigned() and not entry.is_imported() and
                    not entry.is_namespace()):
                continue
            if entry.is_local() or entry.is_parameter() or entry.is_imported() or entry.is_assigned():
                return False
    return True


def assigned_target(root, call, tree, nodes, symbols, parents):
    """Reconstruct one module assignment using original imports and compiler symbols."""
    declarations = [node for node in tree.body if isinstance(node, ast.Assign) and
                    len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == root]
    if len(declarations) != 1 or root not in symbols.get_identifiers():
        return None
    declaration = declarations[0]
    if (declaration.lineno, declaration.col_offset) >= (call.lineno, call.col_offset):
        return None
    symbol = symbols.lookup(root)
    if not symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace():
        return None
    if not module_binding_visible(root, call, nodes, symbols, parents):
        return None
    for node in nodes:
        if (isinstance(node, ast.Name) and node.id == root and
                isinstance(node.ctx, (ast.Store, ast.Del)) and node is not declaration.targets[0]):
            return None
        if isinstance(node, (ast.Global, ast.Nonlocal)) and root in node.names:
            return None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name == root:
            return None
        if isinstance(node, ast.MatchMapping) and node.rest == root:
            return None
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            base = node.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name) and base.id == root:
                return None
    value = declaration.value
    if isinstance(value, ast.Name):
        original = imported_target(value.id, declaration, tree, nodes, symbols, parents)
        return original if original in {"subprocess." + name for name in FUNCTIONS} else None
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.attr in FUNCTIONS:
        original = imported_target(value.value.id, declaration, tree, nodes, symbols, parents)
        return "subprocess." + value.attr if original == "subprocess" else None
    return None


def function_import_target(root, call, parents, nodes, symbols):
    """Check the compiler's local symbol, original imports and mutations independently."""
    child, owner = call, parents.get(call)
    while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if isinstance(owner, (ast.ClassDef, ast.Lambda, ast.ListComp, ast.SetComp,
                              ast.DictComp, ast.GeneratorExp)):
            return None
        child, owner = owner, parents.get(owner)
    if owner is None or child not in owner.body:
        return None
    pending, matches = list(symbols.get_children()), []
    while pending:
        table = pending.pop()
        pending.extend(table.get_children())
        if table.get_type() == "function" and table.get_name() == owner.name and table.get_lineno() == owner.lineno:
            matches.append(table)
    if len(matches) != 1 or root not in matches[0].get_identifiers():
        return None
    table = matches[0]
    entry = table.lookup(root)
    if (not entry.is_imported() or entry.is_assigned() or entry.is_parameter() or
            entry.is_global() or entry.is_nonlocal() or entry.is_namespace() or
            any(getattr(item, "name", None) == root for item in getattr(owner, "type_params", []))):
        return None
    nested = list(table.get_children())
    while nested:
        descendant = nested.pop()
        nested.extend(descendant.get_children())
        if root in descendant.get_identifiers():
            symbol = descendant.lookup(root)
            if symbol.is_imported() or symbol.is_assigned() or symbol.is_parameter() or symbol.is_local():
                return None
    bindings = []
    for statement in owner.body:
        if not isinstance(statement, (ast.Import, ast.ImportFrom)):
            continue
        for alias in statement.names:
            name = alias.asname or (alias.name.split(".")[0] if isinstance(statement, ast.Import) else alias.name)
            if name != root:
                continue
            target = ("subprocess" if alias.name == "subprocess" else None) if isinstance(statement, ast.Import) else (
                "subprocess." + alias.name if statement.module == "subprocess" and statement.level == 0
                and alias.name in FUNCTIONS else None)
            bindings.append((target, (statement.lineno, statement.col_offset)))
    if (not bindings or bindings[0][0] is None or
            any(target != bindings[0][0] for target, _ in bindings) or
            not any(position < (call.lineno, call.col_offset) for _, position in bindings)):
        return None
    for node in ast.walk(owner):
        if isinstance(node, (ast.Global, ast.Nonlocal)) and root in node.names:
            return None
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in owner.body:
            for alias in node.names:
                name = alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)
                if name in {root, "*"}:
                    return None
    for node in nodes:
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            base = node.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name) and base.id == root:
                return None
    return bindings[0][0]


def function_assigned_target(root, call, tree, nodes, symbols, parents):
    """Establish a compiler-local single store and independently reread its import."""
    child, owner = call, parents.get(call)
    while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if isinstance(owner, (ast.ClassDef, ast.Lambda, ast.ListComp, ast.SetComp,
                              ast.DictComp, ast.GeneratorExp)):
            return None
        child, owner = owner, parents.get(owner)
    if owner is None or child not in owner.body:
        return None
    pending, tables = list(symbols.get_children()), []
    while pending:
        table = pending.pop()
        pending.extend(table.get_children())
        if table.get_type() == "function" and table.get_name() == owner.name and table.get_lineno() == owner.lineno:
            tables.append(table)
    if len(tables) != 1 or root not in tables[0].get_identifiers():
        return None
    symbol = tables[0].lookup(root)
    if (not symbol.is_local() or not symbol.is_assigned() or symbol.is_parameter() or
            symbol.is_imported() or symbol.is_global() or symbol.is_nonlocal() or symbol.is_namespace() or
            any(getattr(item, "name", None) == root for item in getattr(owner, "type_params", []))):
        return None
    nested = list(tables[0].get_children())
    while nested:
        table = nested.pop()
        nested.extend(table.get_children())
        if root in table.get_identifiers():
            entry = table.lookup(root)
            if entry.is_local() or entry.is_parameter() or entry.is_imported() or entry.is_assigned():
                return None
    captures = [statement for statement in owner.body if isinstance(statement, ast.Assign)
                and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id == root]
    if len(captures) != 1:
        return None
    capture = captures[0]
    if (capture.lineno, capture.col_offset) >= (call.lineno, call.col_offset):
        return None
    for node in ast.walk(owner):
        if (isinstance(node, ast.Name) and node.id == root and
                isinstance(node.ctx, (ast.Store, ast.Del)) and node is not capture.targets[0]):
            return None
        if isinstance(node, (ast.Global, ast.Nonlocal)) and root in node.names:
            return None
        if (node is not owner and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                ast.ClassDef, ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name == root):
            return None
        if isinstance(node, ast.MatchMapping) and node.rest == root:
            return None
    for node in nodes:
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            base = node.value
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name) and base.id == root:
                return None
    value = capture.value
    original_name = value.id if isinstance(value, ast.Name) else (
        value.value.id if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) else None)
    if original_name is None:
        return None
    original = (function_import_target(original_name, capture, parents, nodes, symbols) or
                imported_target(original_name, capture, tree, nodes, symbols, parents))
    if isinstance(value, ast.Name):
        return original if original in {"subprocess." + name for name in FUNCTIONS} else None
    return "subprocess." + value.attr if original == "subprocess" and value.attr in FUNCTIONS else None


def verify(payload):
    raw = base64.b64decode(payload["source"], validate=True)
    signals = payload["signals"]
    if len(raw) > 65536 or not isinstance(signals, list) or not 1 <= len(signals) <= 100:
        return {"error": "invalid_verification_input"}
    digest = hashlib.sha256(raw).hexdigest()
    if digest != payload["sha256"]:
        return {"error": "source_hash_mismatch"}
    source = raw.decode("utf-8-sig")
    tree = ast.parse(source, filename="<verification-source>")
    nodes = []
    for node in ast.walk(tree):
        nodes.append(node)
        if len(nodes) > 20000:
            return {"error": "source_verifier_too_complex"}
    symbols = symtable.symtable(source, "<verification-source>", "exec")
    parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    calls = {(node.lineno, node.col_offset + 1, node.end_lineno, node.end_col_offset + 1): node
             for node in nodes if isinstance(node, ast.Call)}
    decisions = []
    for signal in signals:
        position = tuple(signal[key] for key in ("line", "column", "end_line", "end_column"))
        node = calls.get(position)
        result, reason = "not_reproduced", "location_does_not_match"
        if node is not None:
            func = node.func
            root = (func.id if isinstance(func, ast.Name) else func.value.id
                    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None)
            target = (function_import_target(root, node, parents, nodes, symbols) or
                      imported_target(root, node, tree, nodes, symbols, parents) or
                      assigned_target(root, node, tree, nodes, symbols, parents) or
                      function_assigned_target(root, node, tree, nodes, symbols, parents)) if root else None
            if target is None:
                result, reason = "inconclusive", "binding_not_established"
            else:
                canonical = (target + "." + func.attr if isinstance(func, ast.Attribute) else target)
                if canonical != signal["call"]:
                    result, reason = "not_reproduced", "call_does_not_match"
                else:
                    result, reason = "not_reproduced", "shell_true_not_observed"
                    for keyword in node.keywords:
                        if keyword.arg != "shell":
                            continue
                        segment = ast.get_source_segment(source, keyword.value)
                        tokens = [token for token in tokenize.generate_tokens(io.StringIO(segment).readline)
                                  if token.type not in {tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER,
                                                        tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT}]
                        if len(tokens) == 1 and tokens[0].type == tokenize.NAME and tokens[0].string == "True":
                            result, reason = "pattern_reproduced", "literal_shell_true_observed"
        decisions.append({"signal_fingerprint": signal["fingerprint"], "result": result, "reason": reason})
    return {"source_sha256": digest, "decisions": decisions}


if __name__ == "__main__":
    try:
        wire = sys.stdin.buffer.read(163841)
        result = verify(json.loads(wire)) if len(wire) <= 163840 else {"error": "invalid_verification_input"}
    except (SyntaxError, UnicodeError, tokenize.TokenError):
        result = {"error": "source_verifier_invalid_python"}
    except (MemoryError, RecursionError):
        result = {"error": "source_verifier_too_complex"}
    except (ValueError, TypeError, KeyError, AttributeError):
        result = {"error": "invalid_verification_input"}
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
