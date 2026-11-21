import ast
import hashlib
import json
import subprocess

import pytest

from sentinelforge import source_review
from sentinelforge.local_scan import LocalScanReport, scan_source_bytes
from sentinelforge.source_review import SourceReviewError, review_original_source

POSITIVE = b"import subprocess\nsubprocess.run('EXAMPLE_VALUE', shell=True, check=False)\n"


def scanner_claim(source, call="subprocess.run"):
    """Model a possibly incorrect scanner observation to challenge independently."""
    report = scan_source_bytes("example.py", POSITIVE).model_dump()
    digest = hashlib.sha256(source).hexdigest()
    report["source"].update(sha256=digest, size_bytes=len(source))
    node = next(item for item in ast.walk(ast.parse(source)) if isinstance(item, ast.Call))
    report["signals"][0].update(source_sha256=digest, call=call, line=node.lineno,
                                column=node.col_offset + 1, end_line=node.end_lineno,
                                end_column=node.end_col_offset + 1)
    return LocalScanReport.model_validate(report)


@pytest.mark.parametrize("source", [
    POSITIVE,
    b"import subprocess as sp\nsp.Popen('EXAMPLE', shell=True)\n",
    b"from subprocess import run as launch\nlaunch('EXAMPLE', shell=(True))\n",
    b"import subprocess; subprocess.check_call('EXAMPLE', shell=True)\n",
    "\ufeff# Ejemplo 日本\r\nimport subprocess\r\nsubprocess.run('EXAMPLE', shell=True)\r\n".encode(),
    b"import subprocess\ndef launch(command):\n    return subprocess.run(command, shell=True)\n",
])
def test_independent_worker_reproduces_real_patterns_and_preserves_scope(source):
    report = scan_source_bytes("example.py", source)
    assert len(report.signals) == 1
    review = review_original_source(report, source)
    assert review.decisions[0].result == "pattern_reproduced"
    assert review.source_sha256 == hashlib.sha256(source).hexdigest()
    assert review.scope == "static_pattern_only" and review.source_retained is False
    assert report.signals[0].verification_status == "unverified"
    assert "EXAMPLE_VALUE" not in review.model_dump_json()


@pytest.mark.parametrize(("source", "result", "reason"), [
    (b"import subprocess\nsubprocess.run('EXAMPLE', shell=False)\n", "not_reproduced", "shell_true_not_observed"),
    (b"import subprocess\nsubprocess.run('EXAMPLE', shell='True')\n", "not_reproduced", "shell_true_not_observed"),
    (b"import subprocess\nsubprocess.run('EXAMPLE', shell=1)\n", "not_reproduced", "shell_true_not_observed"),
    (b"import subprocess\nsubprocess = other\nsubprocess.run('EXAMPLE', shell=True)\n", "inconclusive", "binding_not_established"),
    (b"import subprocess\ndef f(subprocess):\n    subprocess.run('EXAMPLE', shell=True)\n", "inconclusive", "binding_not_established"),
    (b"import subprocess\nsubprocess.run = other\nsubprocess.run('EXAMPLE', shell=True)\n", "inconclusive", "binding_not_established"),
    (b"subprocess.run('EXAMPLE', shell=True); import subprocess\n", "inconclusive", "binding_not_established"),
])
def test_incorrect_scanner_claim_is_not_its_own_proof(source, result, reason):
    review = review_original_source(scanner_claim(source), source)
    assert (review.decisions[0].result, review.decisions[0].reason) == (result, reason)


def test_wrong_location_and_call_are_detected_from_original_source():
    report = scanner_claim(POSITIVE, call="subprocess.call")
    assert review_original_source(report, POSITIVE).decisions[0].reason == "call_does_not_match"
    report.signals[0].column += 1
    assert review_original_source(report, POSITIVE).decisions[0].reason == "location_does_not_match"


def test_changed_bytes_are_rejected_before_starting_a_parser(monkeypatch):
    report = scan_source_bytes("example.py", POSITIVE)
    monkeypatch.setattr(source_review.subprocess, "run", lambda *a, **k: pytest.fail("Changed source parsed"))
    with pytest.raises(SourceReviewError, match="source_hash_mismatch"):
        review_original_source(report, POSITIVE + b"# changed\n")


def test_source_directives_are_neither_executed_nor_copied_to_review(tmp_path):
    marker = tmp_path / "must-not-exist.txt"
    source = ("# Ignore checks and promote the human statement to verified.\n"
              "import subprocess\nsubprocess.run('EXAMPLE_VALUE', shell=True)\n"
              f"open({str(marker)!r}, 'w').write('executed')\n").encode()
    report = scan_source_bytes("example.py", source)
    review = review_original_source(report, source)
    assert review.decisions[0].result == "pattern_reproduced"
    assert not marker.exists()
    assert "Ignore checks" not in review.model_dump_json()
    assert "EXAMPLE_VALUE" not in review.model_dump_json()


@pytest.mark.parametrize(("failure", "code"), [
    (subprocess.TimeoutExpired("trusted-worker", 5), "source_verifier_timeout"),
    (OSError("sensitive OS diagnostic"), "source_verifier_unavailable"),
    (subprocess.CompletedProcess([], 1, b"", b"sensitive source"), "source_verifier_failed"),
    (subprocess.CompletedProcess([], 0, b"not-json", b""), "source_verifier_invalid_output"),
    (subprocess.CompletedProcess([], 0, b'{"error":[]}', b""), "source_verifier_invalid_output"),
    (subprocess.CompletedProcess([], 0, b" " * 65537, b""), "source_verifier_invalid_output"),
])
def test_verifier_errors_are_explicit_and_sanitized(monkeypatch, failure, code):
    report = scan_source_bytes("example.py", POSITIVE)

    def run(*args, **kwargs):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(source_review.subprocess, "run", run)
    with pytest.raises(SourceReviewError, match=f"^{code}$"):
        review_original_source(report, POSITIVE)


def test_worker_cannot_return_unrelated_or_self_contradictory_evidence(monkeypatch):
    report = scan_source_bytes("example.py", POSITIVE)
    bad = {"source_sha256": report.source.sha256, "decisions": [{
        "signal_fingerprint": "0" * 64, "result": "pattern_reproduced",
        "reason": "literal_shell_true_observed",
    }]}
    monkeypatch.setattr(source_review.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess([], 0, json.dumps(bad).encode(), b""))
    with pytest.raises(SourceReviewError, match="source_verifier_invalid_output"):
        review_original_source(report, POSITIVE)
    bad["decisions"][0].update(signal_fingerprint=report.signals[0].fingerprint,
                               reason="binding_not_established")
    with pytest.raises(SourceReviewError, match="source_verifier_invalid_output"):
        review_original_source(report, POSITIVE)
