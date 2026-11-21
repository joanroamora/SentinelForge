"""Backward, bounded assignment slicing. Source is data, never executed."""

import ast
import base64
import hashlib
import json
import sys


def location(node):
    return {"line": node.lineno, "column": node.col_offset + 1,
            "end_line": node.end_lineno, "end_column": node.end_col_offset + 1}


def step(kind, node, symbol=None):
    return dict(kind=kind, symbol=symbol if symbol and len(symbol) <= 120 else None, **location(node))


def investigate(call, signal, parents, capacity):
    sink = step("sink", call, signal["call"])
    keywords = [item.value for item in call.keywords if item.arg == "args"]
    argument = call.args[0] if call.args else keywords[0] if len(keywords) == 1 else None

    def unknown(reason, node=None, scope=None):
        return {"function": scope, "origin_kind": "unknown", "reason": reason,
                "steps": [step("unknown", node or argument or call), sink]}

    if any(item.arg is None for item in call.keywords) or (call.args and keywords) or isinstance(argument, ast.Starred):
        return unknown("dynamic_arguments")
    if argument is None:
        return unknown("argument_missing")
    current = call
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.Lambda, ast.ClassDef, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return unknown("function_out_of_scope")
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            break
    if not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return unknown("function_out_of_scope")
    function = current
    scope = location(function)
    index = next((i for i, statement in enumerate(function.body) if getattr(statement, "value", None) is call
                  and isinstance(statement, (ast.Expr, ast.Return, ast.Assign))), None)
    if index is None:
        return unknown("control_flow_or_opaque_statement", scope=scope)
    if index > 128:
        return unknown("trace_limit", scope=scope)
    parameters = {item.arg: item for item in [*function.args.posonlyargs, *function.args.args,
                  *function.args.kwonlyargs, function.args.vararg, function.args.kwarg] if item is not None}
    external = set()
    pending = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            external.update(node.names)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            pending.extend(ast.iter_child_nodes(node))
    assignments = []
    expression, cutoff = argument, index
    reason, origin = "straight_line_bindings", "unknown"
    while True:
        if isinstance(expression, ast.Constant):
            origin_step, origin = step("literal", expression), "literal"
            break
        if isinstance(expression, ast.Call):
            origin_step, origin, reason = step("call_result", expression), "call_result", "callee_not_followed"
            break
        if not isinstance(expression, ast.Name):
            origin_step, reason = step("unknown", expression), "expression_out_of_scope"
            break
        if expression.id in external:
            origin_step, reason = step("unknown", expression, expression.id), "binding_out_of_scope"
            break
        found, blocked = None, False
        for previous in range(cutoff - 1, -1, -1):
            statement = function.body[previous]
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                if statement.targets[0].id == expression.id:
                    found = previous, statement
                    break
                if not isinstance(statement.value, (ast.Name, ast.Constant)):
                    blocked = True
                    break
            elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                names = {alias.asname or (alias.name.split(".")[0] if isinstance(statement, ast.Import)
                                         else alias.name) for alias in statement.names}
                if expression.id in names or "*" in names:
                    blocked = True
                    break
            elif not (isinstance(statement, (ast.Pass, ast.Global, ast.Nonlocal)) or
                      isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)):
                blocked = True
                break
        if blocked:
            origin_step, reason = step("unknown", expression, expression.id), "control_flow_or_opaque_statement"
            break
        if found is None:
            if expression.id in parameters:
                origin_step, origin = step("parameter", parameters[expression.id], expression.id), "parameter"
            else:
                origin_step, reason = step("unknown", expression, expression.id), "binding_out_of_scope"
            break
        if len(assignments) >= capacity - 2:
            origin_step, reason = step("unknown", expression, expression.id), "trace_limit"
            break
        cutoff, statement = found
        assignments.append(step("assignment", statement.targets[0], expression.id))
        expression = statement.value
    return {"function": scope, "origin_kind": origin, "reason": reason,
            "steps": [origin_step, *reversed(assignments), sink]}


def run(payload):
    raw = base64.b64decode(payload["source"], validate=True)
    signals = payload["signals"]
    if len(raw) > 65536 or not 1 <= len(signals) <= 100:
        return {"error": "lineage_invalid_input"}
    digest = hashlib.sha256(raw).hexdigest()
    if digest != payload["sha256"]:
        return {"error": "source_hash_mismatch"}
    tree = ast.parse(raw.decode("utf-8-sig"), filename="<lineage-source>")
    nodes = list(ast.walk(tree))
    if len(nodes) > 20000:
        return {"error": "lineage_too_complex"}
    parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
    calls = {tuple(location(node).values()): node for node in nodes if isinstance(node, ast.Call)}
    traces, remaining = [], 512
    for index, signal in enumerate(signals):
        capacity = min(32, remaining - 2 * (len(signals) - index - 1))
        call = calls[tuple(signal[key] for key in ("line", "column", "end_line", "end_column"))]
        proposal = investigate(call, signal, parents, capacity)
        traces.append(dict(signal_fingerprint=signal["fingerprint"], **proposal))
        remaining -= len(proposal["steps"])
    return {"source_sha256": digest, "proposals": traces}


if __name__ == "__main__":
    try:
        wire = sys.stdin.buffer.read(163841)
        result = run(json.loads(wire)) if len(wire) <= 163840 else {"error": "lineage_invalid_input"}
    except (SyntaxError, UnicodeError):
        result = {"error": "lineage_invalid_python"}
    except (MemoryError, RecursionError):
        result = {"error": "lineage_too_complex"}
    except (ValueError, TypeError, KeyError, AttributeError):
        result = {"error": "lineage_invalid_input"}
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
