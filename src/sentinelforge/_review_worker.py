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


def imported_target(root, call_position, tree, nodes, symbols):
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
    if bindings[0][0] is None or not any(position < call_position for _, position in bindings):
        return None
    symbol = symbols.lookup(root)
    if not symbol.is_imported() or symbol.is_assigned() or symbol.is_namespace():
        return None
    pending = list(symbols.get_children())
    while pending:
        table = pending.pop()
        pending.extend(table.get_children())
        if root in table.get_identifiers():
            entry = table.lookup(root)
            if entry.is_local() or entry.is_parameter() or entry.is_imported() or entry.is_assigned():
                return None
    for node in nodes:
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            value = node.value
            while isinstance(value, (ast.Attribute, ast.Subscript)):
                value = value.value
            if isinstance(value, ast.Name) and value.id == root:
                return None
    return bindings[0][0]


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
            target = imported_target(root, (node.lineno, node.col_offset), tree, nodes, symbols) if root else None
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
