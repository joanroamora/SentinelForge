"""Release evidence must fail closed on stale, incomplete or mismatched checks."""

import json
import os
import subprocess
import sys

import pytest

from scripts import validate_local as gate
from sentinelforge import evaluation
from sentinelforge.evaluation import evaluate_corpus, load_builtin_corpus
from sentinelforge.evaluation_contracts import BuiltinCorpus


@pytest.fixture(scope="module")
def reference_subsets():
    # Protocol tests need real reports, but not another full detector benchmark.
    subsets = {}
    for selection in BuiltinCorpus:
        reference = load_builtin_corpus(selection)
        negative = next(case for case in reference.cases
                        if case.scope == "in_scope" and not case.expected_signals)
        subsets[selection.value] = reference.model_copy(update={"cases": [negative]})
    return subsets


@pytest.fixture(scope="module")
def report_templates(reference_subsets):
    return {name: evaluate_corpus(corpus).model_dump(mode="json")
            for name, corpus in reference_subsets.items()}


@pytest.fixture(autouse=True)
def bounded_protocol_references(monkeypatch, reference_subsets, report_templates):
    monkeypatch.setattr(evaluation, "load_builtin_corpus", lambda selection=BuiltinCorpus.baseline:
                        reference_subsets[BuiltinCorpus(selection).value])


def fake_runner(templates, *, fail=None, code=1, change=None):
    def run(command, root, output, timeout):
        assert command[0] == sys.executable and timeout > 0
        name = output.stem
        if change is not None:
            change(name)
        if name in templates:
            output.write_text(json.dumps(templates[name]), encoding="utf-8")
        else:
            output.write_text("check completed\n", encoding="utf-8")
        return code if name == fail else 0
    return run


def run_gate(tmp_path, templates, **options):
    return gate.validate(tmp_path, tmp_path / "evidence", runner=fake_runner(templates, **options),
                         fingerprint=lambda root: "source-a", engine_digest=lambda: templates[
                             "baseline"]["engine_sha256"])


def test_requires_the_repository_venv_before_creating_any_evidence(tmp_path, monkeypatch):
    expected = tmp_path / ".venv"
    monkeypatch.setattr(sys, "prefix", str(expected))
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path / "system"))
    monkeypatch.setattr(sys, "executable", str(expected / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python")))
    gate.require_repo_venv(tmp_path)
    monkeypatch.setattr(sys, "prefix", sys.base_prefix)
    with pytest.raises(gate.ValidationError, match="^validation_requires_repo_venv$"):
        gate.require_repo_venv(tmp_path)
    assert not list(tmp_path.iterdir())


def test_fingerprint_tracks_product_tests_configuration_and_gate_not_generated_files(tmp_path):
    for name in ("src/sentinelforge/worker.py", "tests/case.py", "pyproject.toml",
                 ".github/workflows/ci.yml", "scripts/validate_local.py"):
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"original\r\n")
    before = gate.source_digest(tmp_path)
    cache = tmp_path / "src/sentinelforge/__pycache__/worker.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"not part of source")
    (tmp_path / "pyproject.toml").write_bytes(b"original\n")
    assert gate.source_digest(tmp_path) == before
    for name in ("src/sentinelforge/worker.py", "tests/case.py", "pyproject.toml",
                 ".github/workflows/ci.yml", "scripts/validate_local.py"):
        file = tmp_path / name
        file.write_bytes(b"changed\n")
        assert gate.source_digest(tmp_path) != before
        file.write_bytes(b"original\n")
    assert gate.source_digest(tmp_path) == before


def test_success_records_both_references_logs_and_honest_limits(tmp_path, report_templates):
    manifest = run_gate(tmp_path, report_templates)
    stored = json.loads((tmp_path / "evidence/manifest.json").read_text())
    assert stored == manifest and manifest["status"] == "passed" and manifest["exit_code"] == 0
    assert all(check["status"] == "passed" for check in manifest["checks"])
    assert set(manifest["evaluations"]) == {"baseline", "challenge"}
    assert manifest["source_sha256_before"] == manifest["source_sha256_after"]
    assert manifest["is_independent_audit"] is manifest["wheel_verified"] is False
    assert manifest["remote_ci_verified"] is False
    assert all(item["reference_review"] == "not_independently_audited"
               for item in manifest["evaluations"].values())


@pytest.mark.parametrize("name", ["ruff", "pytest", "baseline", "challenge"])
@pytest.mark.parametrize("code", [1, 2])
def test_failure_stops_later_checks_and_never_claims_success(tmp_path, report_templates, name, code):
    manifest = run_gate(tmp_path, report_templates, fail=name, code=code)
    assert manifest["status"] == ("failed" if code == 1 else "error")
    assert manifest["exit_code"] == code and manifest["error_code"] == "validation_check_failed"
    checks = manifest["checks"]
    index = next(i for i, check in enumerate(checks) if check["id"] == name)
    assert checks[index]["exit_code"] == code
    assert all(check["status"] == "not_run" for check in checks[index + 1:])


@pytest.mark.parametrize("field,value", [
    ("engine_sha256", "0" * 64), ("corpus_sha256", "0" * 64),
    ("corpus_id", "sf-py-001-challenge"), ("cases", []),
    ("acceptance", "fail"), ("status", "PARTIAL"),
    ("reference_review", "independently_audited"),
])
def test_zero_exit_cannot_hide_mixed_stale_partial_or_mislabelled_evidence(
        tmp_path, report_templates, field, value):
    templates = json.loads(json.dumps(report_templates))
    templates["baseline"][field] = value
    manifest = gate.validate(
        tmp_path, tmp_path / "evidence", runner=fake_runner(templates),
        fingerprint=lambda root: "source-a",
        engine_digest=lambda: report_templates["baseline"]["engine_sha256"])
    assert manifest["status"] == "error" and manifest["exit_code"] == 2
    assert "baseline" not in manifest["evaluations"]
    assert manifest["checks"][-1]["status"] == "not_run"


@pytest.mark.parametrize("mutation", ["source", "targets", "metrics", "truncated", "oversized"])
def test_corrupt_or_inconsistent_evidence_cannot_pass_with_exit_zero(
        tmp_path, report_templates, mutation):
    templates = json.loads(json.dumps(report_templates))
    if mutation == "source":
        templates["baseline"]["cases"][0]["source_sha256"] = "0" * 64
    elif mutation == "targets":
        templates["baseline"]["cases"][0]["scope"] = "boundary"
    elif mutation == "metrics":
        templates["baseline"]["groups"]["all"]["detection"]["false_positives"] += 1
    run = fake_runner(templates)

    def corrupt(command, root, output, timeout):
        code = run(command, root, output, timeout)
        if output.stem == "baseline" and mutation in {"truncated", "oversized"}:
            output.write_bytes(b"{" if mutation == "truncated" else b" " * 2_000_001)
        return code
    manifest = gate.validate(
        tmp_path, tmp_path / "evidence", runner=corrupt, fingerprint=lambda root: "source-a",
        engine_digest=lambda: report_templates["baseline"]["engine_sha256"])
    assert manifest["status"] == "error" and manifest["exit_code"] == 2
    assert manifest["checks"][2]["status"] == "error"
    assert manifest["checks"][-1]["status"] == "not_run"


@pytest.mark.parametrize("which", ["source", "engine"])
def test_changes_during_validation_invalidate_otherwise_green_checks(tmp_path, report_templates, which):
    source = iter(["source-a", "source-b"] if which == "source" else ["source-a"] * 2)
    engine = report_templates["baseline"]["engine_sha256"]
    engines = iter([engine, "0" * 64] if which == "engine" else [engine] * 2)
    manifest = gate.validate(
        tmp_path, tmp_path / "evidence", runner=fake_runner(report_templates),
        fingerprint=lambda root: next(source), engine_digest=lambda: next(engines))
    assert manifest["status"] == "error" and manifest["exit_code"] == 2
    assert manifest["error_code"] == "validation_sources_changed"


@pytest.mark.parametrize("failure,expected", [
    (subprocess.TimeoutExpired(["python"], 1), "validation_check_timeout"),
    (OSError("PRIVATE_OS_DETAIL"), "validation_evidence_unavailable"),
    (KeyboardInterrupt(), "validation_interrupted"),
])
def test_operational_failures_leave_a_receipt_and_no_success(tmp_path, report_templates, failure, expected):
    def unavailable(*args):
        raise failure
    manifest = gate.validate(
        tmp_path, tmp_path / "evidence", runner=unavailable,
        fingerprint=lambda root: "source-a",
        engine_digest=lambda: report_templates["baseline"]["engine_sha256"])
    assert manifest["status"] in {"error", "interrupted"}
    assert manifest["error_code"] == expected and manifest["exit_code"] != 0
    assert manifest["checks"][0]["status"] != "running"
    assert "PRIVATE_OS_DETAIL" not in (tmp_path / "evidence/manifest.json").read_text()


def test_evidence_never_overwrites_an_existing_run_or_escapes_root(tmp_path, report_templates):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    preserved = evidence / "manifest.json"
    preserved.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_gate(tmp_path, report_templates)
    assert preserved.read_text() == "original"
    with pytest.raises(gate.ValidationError, match="^validation_evidence_outside_repository$"):
        gate.validate(tmp_path, tmp_path.parent / "outside")


def test_runner_has_no_stdin_uses_log_files_and_keeps_nonzero_status(tmp_path):
    output = tmp_path / "result.log"
    code = gate.run_command(
        [sys.executable, "-c", ("import sys; print(sys.stdin.read()); "
                              "print('DIAGNOSTIC', file=sys.stderr); raise SystemExit(2)")],
        tmp_path, output, 10)
    assert code == 2 and output.read_text().strip() == ""
    assert output.with_suffix(".stderr.log").read_text().strip() == "DIAGNOSTIC"
