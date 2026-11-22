"""Independent forward binding replay; does not import the slicing investigator."""

import ast
import base64
import hashlib
import json
import sys


def span(node):
    return {"line": node.lineno, "column": node.col_offset + 1,
                "end_line": node.end_lineno, "end_column": node.end_col_offset + 1}


def item(kind, node, name=None):
    return dict(kind=kind, symbol=name if name and len(name) <= 120 else None, **span(node))


def replay(call, signal, ancestors, allowance):
    sink = item("sink", call, signal["call"])
    named = [keyword.value for keyword in call.keywords if keyword.arg == "args"]
    value = call.args[0] if call.args else named[0] if len(named) == 1 else None

    def stopped(reason, scope=None):
        return {"function": scope, "origin_kind": "unknown", "reason": reason,
                    "steps": [item("unknown", value or call), sink]}

    if (any(keyword.arg is None for keyword in call.keywords) or
            call.args and named or isinstance(value, ast.Starred)):
        return stopped("dynamic_arguments")
    if value is None:
        return stopped("argument_missing")
    owner = ancestors.get(call)
    while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if isinstance(owner, (ast.ClassDef, ast.Lambda, ast.ListComp, ast.SetComp,
                              ast.DictComp, ast.GeneratorExp)):
            return stopped("function_out_of_scope")
        owner = ancestors.get(owner)
    if owner is None:
        return stopped("function_out_of_scope")
    scope = span(owner)
    before = []
    for statement in owner.body:
        if isinstance(statement, (ast.Return, ast.Expr, ast.Assign)) and statement.value is call:
            break
        before.append(statement)
    else:
        return stopped("control_flow_or_opaque_statement", scope)
    if len(before) > 128:
        return stopped("trace_limit", scope)
    external = set()

    def declarations(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            external.update(node.names)
        for child in ast.iter_child_nodes(node):
            declarations(child)

    for statement in owner.body:
        declarations(statement)
    bindings = {}
    for parameter in (*owner.args.posonlyargs, *owner.args.args, *owner.args.kwonlyargs,
                      owner.args.vararg, owner.args.kwarg):
        if parameter is not None:
            bindings[parameter.arg] = ("parameter", "straight_line_bindings",
                                       [item("parameter", parameter, parameter.arg)])
    barrier = False
    import_bindings = set()
    module = owner
    while module in ancestors:
        module = ancestors[module]
    module_references = {
        alias.asname or alias.name: (statement.lineno, statement.col_offset)
        for statement in getattr(module, "body", []) if isinstance(statement, ast.Import)
        for alias in statement.names if alias.name == "subprocess"
    }
    for name in bindings:
        module_references.pop(name, None)

    def expression(node):
        if isinstance(node, ast.Constant):
            return "literal", "straight_line_bindings", [item("literal", node)]
        if isinstance(node, ast.Call):
            return "call_result", "callee_not_followed", [item("call_result", node)]
        if isinstance(node, ast.Name):
            if node.id not in external and node.id in bindings:
                kind, reason, steps = bindings[node.id]
                return kind, reason, list(steps)
            reason = ("control_flow_or_opaque_statement" if (barrier or node.id in import_bindings) and node.id not in external
                      else "binding_out_of_scope")
            return "unknown", reason, [item("unknown", node, node.id)]
        return "unknown", "expression_out_of_scope", [item("unknown", node)]

    assignment_sources = {}
    for statement in before:
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1 and
                isinstance(statement.targets[0], ast.Name)):
            target = statement.targets[0]
            capture = (isinstance(call.func, ast.Name) and call.func.id == target.id and
                       isinstance(statement.value, ast.Attribute) and isinstance(statement.value.value, ast.Name) and
                       signal["call"] == "subprocess." + statement.value.attr and
                       statement.value.value.id in module_references and
                       module_references[statement.value.value.id] < (statement.lineno, statement.col_offset))
            kind, reason, path = expression(statement.value)
            if not isinstance(statement.value, (ast.Name, ast.Constant)) and not capture:
                bindings.clear()
                barrier = True
            module_references.pop(target.id, None)
            path.append(item("assignment", target, target.id))
            bindings[target.id] = kind, reason, path
            assignment_sources[tuple(span(target).values())] = statement.value
            import_bindings.discard(target.id)
        elif isinstance(statement, (ast.Import, ast.ImportFrom)):
            for alias in statement.names:
                if alias.name == "*":
                    bindings.clear()
                    barrier = True
                else:
                    name = alias.asname or alias.name.split(".")[0] if isinstance(statement, ast.Import) else alias.asname or alias.name
                    bindings.pop(name, None)
                    import_bindings.add(name)
                    module_references.pop(name, None)
                    if isinstance(statement, ast.Import) and alias.name == "subprocess":
                        module_references[name] = statement.lineno, statement.col_offset
        elif not (isinstance(statement, (ast.Pass, ast.Global, ast.Nonlocal)) or
                  isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)):
            bindings.clear()
            barrier = True
    kind, reason, path = expression(value)
    if len(path) + 1 > allowance:
        kept = path[-(allowance - 2):] if allowance > 2 else []
        boundary = assignment_sources[tuple(kept[0][key] for key in
                    ("line", "column", "end_line", "end_column"))] if kept else value
        path = [item("unknown", boundary, boundary.id if isinstance(boundary, ast.Name) else None), *kept]
        kind, reason = "unknown", "trace_limit"
    return {"function": scope, "origin_kind": kind, "reason": reason, "steps": [*path, sink]}


def run(payload):
    raw = base64.b64decode(payload["source"], validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    signals, proposals = payload["signals"], payload["proposals"]
    if len(raw) > 65536 or not 1 <= len(signals) <= 100 or len(proposals) != len(signals):
        return {"error": "lineage_invalid_input"}
    if digest != payload["sha256"]:
        return {"error": "source_hash_mismatch"}
    tree = ast.parse(raw.decode("utf-8-sig"), filename="<lineage-check>")
    nodes = list(ast.walk(tree))
    if len(nodes) > 20000:
        return {"error": "lineage_too_complex"}
    ancestors = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    calls = {tuple(span(node).values()): node for node in nodes if isinstance(node, ast.Call)}
    checks, remaining = [], 512
    for index, (signal, proposed) in enumerate(zip(signals, proposals, strict=True)):
        allowance = min(32, remaining - 2 * (len(signals) - index - 1))
        call = calls[tuple(signal[key] for key in ("line", "column", "end_line", "end_column"))]
        expected = dict(signal_fingerprint=signal["fingerprint"],
                        **replay(call, signal, ancestors, allowance))
        remaining -= len(expected["steps"])
        if expected != proposed:
            result, results = "not_reproduced", ["not_reproduced"] * len(proposed["steps"])
        elif expected["origin_kind"] in {"unknown", "call_result"}:
            result, results = "inconclusive", ["inconclusive", *["reproduced"] * (len(proposed["steps"]) - 1)]
        else:
            result, results = "steps_reproduced", ["reproduced"] * len(proposed["steps"])
        checks.append({"signal_fingerprint": signal["fingerprint"], "result": result, "step_results": results})
    return {"source_sha256": digest, "checks": checks}


if __name__ == "__main__":
    try:
        wire = sys.stdin.buffer.read(1048577)
        output = run(json.loads(wire)) if len(wire) <= 1048576 else {"error": "lineage_invalid_input"}
    except (SyntaxError, UnicodeError):
        output = {"error": "lineage_invalid_python"}
    except (MemoryError, RecursionError):
        output = {"error": "lineage_too_complex"}
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        output = {"error": "lineage_invalid_input"}
    sys.stdout.write(json.dumps(output, ensure_ascii=True, separators=(",", ":")))
