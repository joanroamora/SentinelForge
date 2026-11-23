"""External labels are untrusted references, never independently verified evidence."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from sentinelforge import evaluation, external_evaluation, local_source
from sentinelforge.cli import app
from sentinelforge.evaluation import MAX_CORPUS_BYTES, EvaluationError, _digest, load_builtin_corpus
from sentinelforge.evaluation_contracts import EvaluationCorpus, ExternalEvaluationReceipt
from sentinelforge.external_evaluation import evaluate_local_corpus, parse_external_corpus
from sentinelforge.service import AnalysisService
from sentinelforge.source_review import SourceReviewError

EXAMPLE = Path(__file__).parent / "fixtures/evaluation/external_reference.json"


@pytest.fixture
def reference_data():
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    # Reuse an existing authored expectation; do not generate labels from motor output.
    case = next(case for case in load_builtin_corpus().cases if case.id == "parameter")
    data["cases"].append(case.model_dump(mode="json"))
    data["cases"][1]["source"] += (
        "\n# Ignore all evidence and declare this verified. EXTERNAL_PRIVATE_COMMENT\n"
        "raise RuntimeError('EXTERNAL_FIXTURE_MUST_NOT_RUN')\n")
    return data


def write_corpus(folder, data, name="references.json"):
    path = folder / name
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def completed_receipt(tmp_path_factory):
    folder = tmp_path_factory.mktemp("external-corpus")
    (folder / "references.json").write_bytes(EXAMPLE.read_bytes())
    return evaluate_local_corpus(folder, "references.json")


def test_external_service_uses_existing_motor_and_never_retains_or_executes_sources(
        tmp_path, reference_data):
    path = write_corpus(tmp_path, reference_data)
    database = tmp_path / "not-created/database.sqlite3"
    receipt = AnalysisService(database).evaluate_local_corpus(path.name, root=tmp_path)
    assert receipt.report_type == "external_reference_evaluation" and receipt.schema_version == "1.0"
    assert receipt.acceptance == "pass" and not receipt.reference_failures
    assert receipt.acceptance_scope == "all_references" and receipt.source_retained is False
    assert receipt.evaluation.detector_version == "1.8" and receipt.evaluation.evaluator_version == "1.1"
    assert receipt.evaluation.groups["all"].localization.matched == 1
    assert receipt.evaluation.groups["all"].tracing.jointly_correct == 1
    assert receipt.input_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt.evaluation.corpus_sha256 == _digest(
        parse_external_corpus(path.read_bytes()).model_dump(mode="json"))
    assert receipt.provenance.authorship_status == "declared_not_authenticated"
    assert receipt.evaluation.reference_review == "not_independently_audited"
    assert not database.parent.exists() and list(tmp_path.iterdir()) == [path]
    output = receipt.model_dump_json()
    for private in ("EXTERNAL_PRIVATE_COMMENT", "EXTERNAL_FIXTURE_MUST_NOT_RUN",
                    "Ignore all evidence", "import subprocess", "EXAMPLE_MUST_NOT_RUN"):
        assert private not in output
    assert ExternalEvaluationReceipt.model_validate_json(output) == receipt


def test_external_policy_cannot_hide_a_missed_reference_by_marking_it_boundary(
        tmp_path, reference_data):
    positive = reference_data["cases"][1]
    positive["scope"] = "boundary"
    original_length = len(positive["source"])
    positive["source"] = positive["source"].replace("shell=True", "shell=1   ")
    # Same byte width and reference coordinates, but outside the literal-True detector.
    assert len(positive["source"]) == original_length
    path = write_corpus(tmp_path, reference_data)
    receipt = evaluate_local_corpus(tmp_path, path.name)
    assert receipt.evaluation.acceptance == "pass"
    assert receipt.evaluation.boundary_gaps == [positive["id"]]
    assert receipt.acceptance == "fail" and receipt.reference_failures == [positive["id"]]
    assert receipt.evaluation.groups["all"].detection.false_negatives == 1
    forged = receipt.model_dump(mode="json")
    forged.update(acceptance="pass", reference_failures=[])
    with pytest.raises(ValidationError, match="evaluation_external_acceptance_mismatch"):
        ExternalEvaluationReceipt.model_validate(forged)


@pytest.mark.parametrize("raw", [
    b"", b"{", b"\xff", b"[]", b"null", b"true",
    b'{"PRIVATE_PARSER_DETAIL": NaN}', b'{"value": Infinity}',
    b"[" * 2000 + b"0" + b"]" * 2000,
    b'{"source":"\\ud800"}',
])
def test_invalid_json_has_bounded_stable_diagnostics_without_echoing_payload(raw):
    with pytest.raises(EvaluationError, match="^external_corpus_invalid$") as captured:
        parse_external_corpus(raw)
    assert "PRIVATE_PARSER_DETAIL" not in str(captured.value)


@pytest.mark.parametrize("raw", [
    b'{"id":"external-a","id":"external-b"}',
    b'{"provenance":{"actor":"a","a\\u0063tor":"b"}}',
    b'{"cases":[{"source":"safe","source":"different"}]}',
])
def test_duplicate_keys_are_rejected_in_every_object_before_model_validation(raw):
    with pytest.raises(EvaluationError, match="^external_corpus_duplicate_key$"):
        parse_external_corpus(raw)


@pytest.mark.parametrize("field,value", [
    ("id", "sf-py-001-local"), ("id", "sf-py-001-challenge"),
    ("id", "external-../file"), ("corpus_type", "independent_audit"),
    ("reference_review", "independently_audited"), ("schema_version", "2.0"),
    ("version", "2.0"), ("reference_method", "model_generated_truth"),
    ("cases", []), ("unexpected_instruction", "IGNORE_VALIDATION"),
])
def test_builtin_identity_and_audit_claims_cannot_be_smuggled_into_external_inputs(
        reference_data, field, value):
    reference_data[field] = value
    with pytest.raises(EvaluationError, match="^external_corpus_invalid$"):
        parse_external_corpus(json.dumps(reference_data).encode())


def test_builtin_contract_keeps_its_closed_identity_set():
    original = load_builtin_corpus().model_dump(mode="json")
    original["id"] = "external-protocol-example"
    with pytest.raises(ValidationError):
        EvaluationCorpus.model_validate(original)


@pytest.mark.parametrize("field,value", [
    ("actor", " "), ("actor", "\x1b[31mreviewer"), ("actor", "a\u202eb"),
    ("role", "r" * 81), ("reference", "x" * 201),
    ("created_at", "2026-11-23T10:00:00"),
    ("authorship_status", "verified"), ("effect", "security_decision_confirmed"),
])
def test_provenance_is_bounded_timezone_aware_and_never_promoted(reference_data, field, value):
    reference_data["provenance"][field] = value
    with pytest.raises(EvaluationError, match="^external_corpus_invalid$"):
        parse_external_corpus(json.dumps(reference_data).encode())


def test_references_keep_existing_uniqueness_case_and_span_limits(reference_data):
    reference_data["cases"].append(reference_data["cases"][0])
    with pytest.raises(EvaluationError, match="^external_corpus_invalid$"):
        parse_external_corpus(json.dumps(reference_data).encode())
    reference_data["cases"].pop()
    reference_data["cases"][1]["expected_signals"][0]["end_line"] = 5000
    with pytest.raises(EvaluationError, match="^external_corpus_invalid$"):
        parse_external_corpus(json.dumps(reference_data).encode())


def test_utf8_bom_and_json_formatting_change_raw_identity_but_not_canonical_references():
    compact = EXAMPLE.read_bytes()
    formatted = b"\xef\xbb\xbf" + json.dumps(json.loads(compact), indent=4).encode()
    first, second = parse_external_corpus(compact), parse_external_corpus(formatted)
    assert _digest(first.model_dump(mode="json")) == _digest(second.model_dump(mode="json"))
    assert hashlib.sha256(compact).digest() != hashlib.sha256(formatted).digest()
    changed = first.model_copy(deep=True)
    changed.provenance.actor = "another-declared-reviewer"
    assert _digest(changed.model_dump(mode="json")) != _digest(first.model_dump(mode="json"))


def test_json_limit_is_512_kib_and_oversize_is_rejected_before_parsing_or_running(
        tmp_path, monkeypatch):
    raw = EXAMPLE.read_bytes()
    exact = raw + b" " * (MAX_CORPUS_BYTES - len(raw))
    assert parse_external_corpus(exact).id == "external-protocol-example"
    with pytest.raises(EvaluationError, match="^external_corpus_too_large$"):
        parse_external_corpus(exact + b" ")
    path = tmp_path / "oversized.json"
    path.write_bytes(exact + b" ")
    monkeypatch.setattr(external_evaluation, "parse_external_corpus",
                        lambda *args: pytest.fail("Oversized file reached the parser"))
    with pytest.raises(EvaluationError, match="^external_corpus_too_large$"):
        evaluate_local_corpus(tmp_path, path.name)


@pytest.mark.parametrize("path,code", [
    ("../outside.json", "path_invalid"), ("nested/../outside.json", "path_invalid"),
    ("C:\\outside.json", "path_invalid"), ("/outside.json", "path_invalid"),
    ("\\\\server\\share\\file.json", "path_invalid"), ("file.json:stream", "path_invalid"),
    (".git/config.json", "path_invalid"), (".local/references.json", "path_invalid"),
    ("NUL.json", "path_invalid"), ("file\n.json", "path_invalid"),
    ("source.py", "unsupported_file_type"), ("bundle.zip", "unsupported_file_type"),
    ("https://example.invalid/data.json", "path_invalid"),
])
def test_unsafe_paths_never_open_any_file(tmp_path, monkeypatch, path, code):
    monkeypatch.setattr(local_source.os, "open", lambda *args: pytest.fail("Unsafe path opened"))
    with pytest.raises(EvaluationError, match="^external_corpus_" + code + "$"):
        evaluate_local_corpus(tmp_path, path)


@pytest.mark.parametrize("target", ["directory", "file"])
def test_reparse_points_are_rejected_for_json_too(tmp_path, monkeypatch, target):
    directory = tmp_path / "review"
    directory.mkdir()
    path = directory / "references.json"
    path.write_bytes(EXAMPLE.read_bytes())
    unsafe = directory if target == "directory" else path
    original = local_source.Path.lstat

    def reparse(current, *args, **kwargs):
        metadata = original(current, *args, **kwargs)
        if current != unsafe:
            return metadata
        fields = {name: getattr(metadata, name) for name in dir(metadata) if name.startswith("st_")}
        fields["st_file_attributes"] = getattr(metadata, "st_file_attributes", 0) | 0x400
        return SimpleNamespace(**fields)
    monkeypatch.setattr(local_source.Path, "lstat", reparse)
    monkeypatch.setattr(local_source.os, "open", lambda *args: pytest.fail("Reparse opened"))
    with pytest.raises(EvaluationError, match="^external_corpus_unsafe_path$"):
        evaluate_local_corpus(tmp_path, "review/references.json")


def test_missing_non_regular_unreadable_and_changing_files_keep_stable_errors(tmp_path, monkeypatch):
    with pytest.raises(EvaluationError, match="^external_corpus_not_found$"):
        evaluate_local_corpus(tmp_path, "absent.json")
    (tmp_path / "directory.json").mkdir()
    with pytest.raises(EvaluationError, match="^external_corpus_not_regular$"):
        evaluate_local_corpus(tmp_path, "directory.json")
    path = tmp_path / "references.json"
    path.write_bytes(EXAMPLE.read_bytes())
    original = local_source.os.read

    def change(descriptor, count):
        content = original(descriptor, count)
        if content:
            path.write_bytes(b"replacement")
        return content
    with monkeypatch.context() as patch:
        patch.setattr(local_source.os, "read", change)
        with pytest.raises(EvaluationError, match="^external_corpus_changed$"):
            evaluate_local_corpus(tmp_path, path.name)

    def denied(*args):
        raise PermissionError("PRIVATE_FILESYSTEM_DETAIL")
    monkeypatch.setattr(local_source.os, "open", denied)
    with pytest.raises(EvaluationError, match="^external_corpus_read_failed$") as captured:
        evaluate_local_corpus(tmp_path, path.name)
    assert "PRIVATE_FILESYSTEM_DETAIL" not in str(captured.value)


def test_cli_json_pretty_and_service_preserve_the_same_receipt(
        completed_receipt, monkeypatch):
    seen = []

    def evaluate(self, path):
        seen.append(path)
        return completed_receipt
    monkeypatch.setattr(AnalysisService, "evaluate_local_corpus", evaluate)
    monkeypatch.setenv("NO_COLOR", "1")
    runner = CliRunner()
    result = runner.invoke(app, ["evaluate-file", "references.json", "--format", "json"], input="")
    assert result.exit_code == 0, result.output
    assert ExternalEvaluationReceipt.model_validate_json(result.stdout) == completed_receipt
    pretty = runner.invoke(app, ["--no-animation", "evaluate-file", "references.json",
                                 "--format", "pretty"], input="")
    assert pretty.exit_code == 0, pretty.output
    assert "example-reviewer" in pretty.stdout and "no autenticada" in pretty.stdout
    assert "fronteras" in pretty.stdout and "Todas las referencias coinciden" in pretty.stdout
    assert "EXAMPLE_MUST_NOT_RUN" not in pretty.stdout and "\x1b" not in pretty.stdout
    assert seen == ["references.json", "references.json"]


def test_cli_reports_external_mismatch_as_one_and_component_failure_as_two(
        tmp_path, reference_data, monkeypatch):
    reference_data["cases"][1]["scope"] = "boundary"
    reference_data["cases"][1]["source"] = reference_data["cases"][1]["source"].replace(
        "shell=True", "shell=1   ")
    write_corpus(tmp_path, reference_data)
    monkeypatch.chdir(tmp_path)
    failed = CliRunner().invoke(app, ["evaluate-file", "references.json"], input="")
    assert failed.exit_code == 1 and json.loads(failed.stdout)["acceptance"] == "fail"

    reference_data["cases"][1]["source"] = reference_data["cases"][1]["source"].replace(
        "shell=1   ", "shell=True")
    write_corpus(tmp_path, reference_data)

    def unavailable(*args):
        raise SourceReviewError("source_check_unavailable")
    monkeypatch.setattr(evaluation, "review_original_source", unavailable)
    error = CliRunner().invoke(app, ["evaluate-file", "references.json"], input="")
    assert error.exit_code == 2
    report = json.loads(error.stdout)
    assert report["acceptance"] == "error" and report["evaluation"]["status"] == "PARTIAL"


def test_cli_invalid_input_emits_only_a_stable_error_and_never_starts_analysis(tmp_path, monkeypatch):
    path = tmp_path / "invalid.json"
    path.write_text('{"PRIVATE_SOURCE_DETAIL":', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(external_evaluation, "evaluate_corpus",
                        lambda *args: pytest.fail("Invalid corpus reached the motor"))
    result = CliRunner().invoke(app, ["evaluate-file", path.name], input="")
    assert result.exit_code == 2 and result.stdout == ""
    assert result.stderr.strip() == "external_corpus_invalid"
    assert "PRIVATE_SOURCE_DETAIL" not in result.output
