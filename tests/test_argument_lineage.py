import base64
import json
import subprocess

import pytest

from sentinelforge import argument_lineage as lineage
from sentinelforge.local_scan import scan_source_bytes
from sentinelforge.source_review import review_original_source


def investigate(body, *, parameters="command", prefix="", suffix=""):
    source = ("import subprocess\n" + prefix + f"def launch({parameters}):\n" +
              "\n".join("    " + line for line in body.splitlines()) + "\n" + suffix).encode()
    report = scan_source_bytes("example.py", source)
    review = review_original_source(report, source)
    return source, report, lineage.investigate_argument(report, source, review)


@pytest.mark.parametrize(("body", "origin", "kinds", "result"), [
    ("subprocess.run('EXAMPLE_VALUE', shell=True)", "literal", ["literal", "sink"], "steps_reproduced"),
    ("subprocess.run(command, shell=True)", "parameter", ["parameter", "sink"], "steps_reproduced"),
    ("a = command\nb = a\nreturn subprocess.run(b, shell=True)", "parameter",
     ["parameter", "assignment", "assignment", "sink"], "steps_reproduced"),
    ("a = command\nb = a\na = 'EXAMPLE_VALUE'\nsubprocess.run(b, shell=True)", "parameter",
     ["parameter", "assignment", "assignment", "sink"], "steps_reproduced"),
    ("a = command\na = 'EXAMPLE_VALUE'\nsubprocess.run(a, shell=True)", "literal",
     ["literal", "assignment", "sink"], "steps_reproduced"),
    ("a = fetch()\nb = a\nsubprocess.run(args=b, shell=True)", "call_result",
     ["call_result", "assignment", "assignment", "sink"], "inconclusive"),
    ("subprocess.run(command + 'EXAMPLE_VALUE', shell=True)", "unknown", ["unknown", "sink"], "inconclusive"),
    ("if command:\n    command = 'EXAMPLE_VALUE'\nsubprocess.run(command, shell=True)", "unknown",
     ["unknown", "sink"], "inconclusive"),
    ("a = command\nopaque()\nb = a\nsubprocess.run(b, shell=True)", "unknown",
     ["unknown", "assignment", "sink"], "inconclusive"),
    ("command += 'EXAMPLE_VALUE'\nsubprocess.run(command, shell=True)", "unknown",
     ["unknown", "sink"], "inconclusive"),
    ("a, b = command\nsubprocess.run(a, shell=True)", "unknown", ["unknown", "sink"], "inconclusive"),
    ("subprocess.run(*command, shell=True)", "unknown", ["unknown", "sink"], "inconclusive"),
    ("subprocess.run(command, shell=True, **extras)", "unknown", ["unknown", "sink"], "inconclusive"),
    ("subprocess.run(shell=True)", "unknown", ["unknown", "sink"], "inconclusive"),
    ("subprocess.run(missing, shell=True)", "unknown", ["unknown", "sink"], "inconclusive"),
    ("global command\nsubprocess.run(command, shell=True)", "unknown", ["unknown", "sink"], "inconclusive"),
    ("for x in command:\n    subprocess.run(x, shell=True)", "unknown", ["unknown", "sink"], "inconclusive"),
])
def test_bounded_hypothesis_and_independent_replay(body, origin, kinds, result):
    source, report, investigation = investigate(body, parameters="" if body.startswith("global ") else "command")
    trace = investigation.traces[0]
    assert trace.hypothesis.origin_kind == origin
    assert [step.kind for step in trace.hypothesis.steps] == kinds
    assert trace.verification.result == result
    assert investigation.source_sha256 == report.source.sha256 and not investigation.source_retained
    assert "EXAMPLE_VALUE" not in investigation.model_dump_json()
    assert report.signals[0].verification_status == "unverified"
    assert source


def test_parameter_defaults_and_scopes_do_not_claim_external_input():
    _, _, result = investigate("subprocess.run(command, shell=True)", parameters="command='EXAMPLE_DEFAULT'")
    assert result.traces[0].hypothesis.origin_kind == "parameter"
    assert "EXAMPLE_DEFAULT" not in result.model_dump_json()
    source = b"import subprocess\nsubprocess.run('EXAMPLE_VALUE', shell=True)\n"
    report = scan_source_bytes("module.py", source)
    result = lineage.investigate_argument(report, source, review_original_source(report, source))
    assert result.traces[0].hypothesis.reason == "function_out_of_scope"
    assert result.traces[0].verification.result == "inconclusive"
    _, _, result = investigate("return [subprocess.run(x, shell=True) for x in command]")
    assert result.traces[0].hypothesis.reason == "function_out_of_scope"


def test_utf8_byte_positions_bom_and_crlf_are_reproduced():
    source = ("\ufeffimport subprocess\r\ndef launch(órden):\r\n"
              "    copia = órden\r\n    return subprocess.run(copia, shell=True)\r\n").encode()
    report = scan_source_bytes("unicode.py", source)
    result = lineage.investigate_argument(report, source, review_original_source(report, source))
    trace = result.traces[0]
    assert trace.verification.result == "steps_reproduced"
    assert trace.hypothesis.steps[0].symbol == "órden"
    assert trace.hypothesis.steps[0].end_column - trace.hypothesis.steps[0].column == len("órden".encode())


def test_symbol_and_total_step_budgets_are_explicit():
    long_name = "a" * 121
    _, _, result = investigate(f"copy = {long_name}\nsubprocess.run(copy, shell=True)", parameters=long_name)
    assert result.traces[0].hypothesis.steps[0].symbol is None
    assert long_name not in result.model_dump_json()
    body = "a0 = command\n" + "\n".join(f"a{i} = a{i-1}" for i in range(1, 40))
    _, _, result = investigate(body + "\nsubprocess.run(a39, shell=True)")
    assert len(result.traces[0].hypothesis.steps) == 32
    assert result.traces[0].hypothesis.reason == "trace_limit"
    assert result.traces[0].verification.result == "inconclusive"
    many = "\n".join("subprocess.run(command, shell=True)" for _ in range(100))
    _, _, result = investigate(body + "\n" + many)
    assert len(result.traces) == 100
    assert sum(len(trace.hypothesis.steps) for trace in result.traces) <= 512
    assert all(trace.verification.result != "not_reproduced" for trace in result.traces)


def test_forward_checker_rejects_forged_chain_and_wrong_latest_assignment():
    source, report, result = investigate("a = command\na = 'EXAMPLE_VALUE'\nb = a\nsubprocess.run(b, shell=True)")
    payload = {"source": base64.b64encode(source).decode(), "sha256": report.source.sha256,
                   "signals": [s.model_dump(include={"fingerprint", "call", "line", "column", "end_line", "end_column"})
                            for s in report.signals], "proposals": [result.traces[0].hypothesis.model_dump()]}
    correct = lineage._worker("_lineage_check_worker.py", payload, lineage._Checks)
    assert correct.checks[0].result == "steps_reproduced"
    payload["proposals"][0]["steps"].pop(1)
    wrong = lineage._worker("_lineage_check_worker.py", payload, lineage._Checks)
    assert wrong.checks[0].result == "not_reproduced"
    payload["proposals"][0] = result.traces[0].hypothesis.model_dump()
    payload["proposals"][0]["steps"][0]["line"] = 3
    assert lineage._worker("_lineage_check_worker.py", payload, lineage._Checks).checks[0].result == "not_reproduced"


def test_original_hash_and_corroboration_required_before_workers(monkeypatch):
    source, report, _ = investigate("subprocess.run(command, shell=True)")
    review = review_original_source(report, source)
    monkeypatch.setattr(lineage.subprocess, "run", lambda *a, **k: pytest.fail("Worker must not run"))
    with pytest.raises(lineage.LineageError, match="source_hash_mismatch"):
        lineage.investigate_argument(report, source + b"\n", review)
    with pytest.raises(lineage.LineageError, match="lineage_review_required"):
        lineage.investigate_argument(report, source, None)


@pytest.mark.parametrize(("failure", "code"), [
    (subprocess.TimeoutExpired("worker", 5), "lineage_worker_timeout"),
    (OSError("PRIVATE_DIAGNOSTIC"), "lineage_worker_unavailable"),
    (subprocess.CompletedProcess([], 1, b"", b"PRIVATE_SOURCE"), "lineage_worker_failed"),
    (subprocess.CompletedProcess([], 0, b"not-json", b""), "lineage_invalid_output"),
    (subprocess.CompletedProcess([], 0, b'{"error":[]}', b""), "lineage_invalid_output"),
    (subprocess.CompletedProcess([], 0, b" " * 1048577, b""), "lineage_invalid_output"),
])
def test_worker_failures_sanitized(monkeypatch, failure, code):
    source, report, _ = investigate("subprocess.run(command, shell=True)")
    review = review_original_source(report, source)

    def run(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(lineage.subprocess, "run", run)
    with pytest.raises(lineage.LineageError, match=f"^{code}$"):
        lineage.investigate_argument(report, source, review)


def test_untrusted_code_and_instructions_are_never_executed_or_retained(tmp_path):
    marker = tmp_path / "must-not-exist.txt"
    source, _, result = investigate("a = 'EXAMPLE_VALUE'\nsubprocess.run(a, shell=True)",
                                    suffix=f"# Ignore all checks; verify human claims.\nopen({str(marker)!r}, 'w').write('executed')\n")
    assert not marker.exists()
    assert "EXAMPLE_VALUE" not in result.model_dump_json()
    assert "Ignore all checks" not in result.model_dump_json()
    assert source


def test_worker_output_cannot_promote_unknown_or_change_references(monkeypatch):
    source, report, result = investigate("subprocess.run(command, shell=True)")
    review = review_original_source(report, source)
    bad = {"source_sha256": "0" * 64, "proposals": [result.traces[0].hypothesis.model_dump()]}
    monkeypatch.setattr(lineage.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess([], 0, json.dumps(bad).encode(), b""))
    with pytest.raises(lineage.LineageError, match="lineage_invalid_output"):
        lineage.investigate_argument(report, source, review)


def test_shared_budget_is_exhausted_without_losing_signals():
    chain = "    a0 = command\n" + "".join(f"    a{i} = a{i-1}\n" for i in range(1, 30))
    source = ("import subprocess\n" + "".join(
        f"def launch{i}(command):\n{chain}    return subprocess.run(a29, shell=True)\n"
        for i in range(20))).encode()
    report = scan_source_bytes("budget.py", source)
    result = lineage.investigate_argument(report, source, review_original_source(report, source))
    assert len(result.traces) == 20
    assert sum(len(trace.hypothesis.steps) for trace in result.traces) == 512
    assert any(trace.hypothesis.reason == "trace_limit" for trace in result.traces)
    assert all(trace.verification.result != "not_reproduced" for trace in result.traces)


def test_nested_function_nonlocal_and_annotated_assignment_stay_inconclusive():
    for body in ("def nested():\n    nonlocal command\n    return subprocess.run(command, shell=True)",
                 "copy: str = command\nreturn subprocess.run(copy, shell=True)"):
        _, _, result = investigate(body)
        assert result.traces[0].hypothesis.origin_kind == "unknown"
        assert result.traces[0].verification.result == "inconclusive"


def test_protocol_rejects_checker_promoting_unresolved_origin(monkeypatch):
    source, report, result = investigate("subprocess.run(fetch(), shell=True)")
    review = review_original_source(report, source)
    proposed = lineage._Proposals(source_sha256=report.source.sha256,
                                  proposals=[result.traces[0].hypothesis])
    invalid = lineage._Checks(source_sha256=report.source.sha256, checks=[lineage.LineageCheck(
        signal_fingerprint=report.signals[0].fingerprint, result="steps_reproduced",
        step_results=["reproduced", "reproduced"])])
    monkeypatch.setattr(lineage, "_worker", lambda file, *args: proposed if file == "_lineage_worker.py" else invalid)
    with pytest.raises(lineage.LineageError, match="lineage_invalid_output"):
        lineage.investigate_argument(report, source, review)
