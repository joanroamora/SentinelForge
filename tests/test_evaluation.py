import json

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from sentinelforge import evaluation
from sentinelforge.cli import app
from sentinelforge.evaluation import (
    EvaluationError,
    evaluate_corpus,
    load_builtin_corpus,
    summarize,
)
from sentinelforge.evaluation_contracts import (
    CaseEvaluation,
    EvaluationCorpus,
    SignalReference,
    TargetEvaluation,
)
from sentinelforge.local_scan import LocalScanError, LocalScanReport
from sentinelforge.service import AnalysisService
from sentinelforge.source_review import SourceReviewError


@pytest.fixture(scope="module")
def corpus():
    return load_builtin_corpus()


@pytest.fixture(scope="module")
def benchmark(tmp_path_factory):
    destination = tmp_path_factory.mktemp("evaluation") / "not-created" / "analyses.sqlite3"
    report = AnalysisService(destination).evaluate_builtin_corpus()
    assert not destination.parent.exists(), "Evaluation must not initialize SQLite or persist fixtures"
    return report


def subset(corpus, *identities):
    return EvaluationCorpus(cases=[case.model_copy(deep=True) for case in corpus.cases if case.id in identities])


def observation(reference):
    return SignalReference.model_validate(reference.model_dump(include={
        "call", "line", "column", "end_line", "end_column"}))


def metric_case(reference, predicted, *, expected=True, error=None):
    return CaseEvaluation(id="metric-example", scope="in_scope", source_sha256="0" * 64,
        expected_error=None, scan_status="ERROR" if error else "COMPLETED", error_code=error,
        technical_error=error is not None, observed_signals=predicted,
        targets=[TargetEvaluation(expected=reference, detected=bool(predicted))] if expected else [],
        reference_match=False, elapsed_ms=1)


def test_builtin_reference_baseline_separates_scope_boundaries_and_errors(benchmark):
    report = benchmark
    assert report.acceptance == "pass" and report.status == "COMPLETED"
    assert len(report.cases) == 28
    assert report.expected_error_matches == 2 and not report.reference_failures
    assert set(report.boundary_gaps) == {"unrelated-shadow-gap", "assignment-alias-gap"}
    supported = report.groups["in_scope"]
    assert supported.cases == 23 and supported.detection.true_positives == 15
    assert supported.detection.true_negatives == 8 and supported.detection.false_positives == 0
    assert supported.localization.matched == 16 and supported.tracing.traced == 16
    assert supported.tracing.inconclusive == 4
    total = report.groups["all"]
    assert total.eligible_detection_cases == 26 and total.detection.false_negatives == 2
    assert total.detection.recall == pytest.approx(16 / 18)
    assert total.localization.recall == pytest.approx(17 / 19)
    assert total.tracing.origin_accuracy_when_traced == 1
    assert total.tracing.coverage == total.tracing.reference_agreement_end_to_end == pytest.approx(17 / 19)
    assert report.groups["boundary"].detection.precision == 1


def test_report_contains_metadata_not_fixture_code_or_literal_values(benchmark):
    text = benchmark.model_dump_json()
    for fixture_text in ("SYNTHETIC_LITERAL", "FIXTURE_EXECUTION_IS_FORBIDDEN", "Ignore all checks", "def launch"):
        assert fixture_text not in text
    assert all(len(value) == 64 for value in (benchmark.corpus_sha256, benchmark.engine_sha256))
    assert benchmark.python_version and benchmark.pydantic_version and benchmark.platform
    assert benchmark.reference_review == "not_independently_audited"
    assert benchmark.is_synthetic and benchmark.case_latency_p95_ms >= benchmark.case_latency_p50_ms


def test_false_positive_false_negative_and_zero_denominators_are_not_hidden(corpus):
    reference = corpus.cases[0].expected_signals[0]
    fp = metric_case(reference, [observation(reference)], expected=False)
    fn = metric_case(reference, [])
    metrics = summarize([fp, fn])
    assert metrics.detection.false_positives == metrics.detection.false_negatives == 1
    assert metrics.detection.precision == metrics.detection.recall == metrics.detection.f1 == 0
    assert metrics.localization.extra == metrics.localization.missed == 1
    assert metrics.tracing.coverage == 0 and metrics.tracing.origin_accuracy_when_traced is None
    empty = summarize([metric_case(reference, [], expected=False)])
    assert empty.detection.true_negatives == 1
    assert empty.detection.precision is empty.detection.recall is empty.detection.f1 is None


def test_wrong_location_and_duplicate_predictions_do_not_inflate_localization(corpus):
    reference = corpus.cases[0].expected_signals[0]
    wrong = observation(reference).model_copy(update={"line": 99, "end_line": 99})
    metrics = summarize([metric_case(reference, [wrong])])
    assert metrics.detection.true_positives == 1
    assert metrics.localization.matched == 0 and metrics.localization.extra == metrics.localization.missed == 1
    double = summarize([metric_case(reference, [observation(reference), observation(reference)])])
    assert double.localization.matched == double.localization.extra == 1
    assert double.localization.precision == 0.5 and double.localization.recall == 1


def test_unexpected_parser_error_is_not_a_negative_or_missed_signal(corpus, monkeypatch):
    monkeypatch.setattr(evaluation, "scan_source_bytes", lambda *a: LocalScanReport(
        status="ERROR", errors=[LocalScanError(code="parser_timeout")]))
    report = evaluate_corpus(subset(corpus, "parameter", "shell-disabled", "invalid-syntax"))
    assert report.status == "PARTIAL" and report.acceptance == "error"
    metrics = report.groups["all"]
    assert metrics.technical_errors == 3 and metrics.eligible_detection_cases == 0
    assert metrics.detection.false_negatives == metrics.detection.true_negatives == 0
    assert report.expected_error_matches == 0


def test_failed_source_review_preserves_detection_but_reduces_trace_coverage(corpus, monkeypatch):
    def unavailable(*args):
        raise SourceReviewError("source_verifier_timeout")
    monkeypatch.setattr(evaluation, "review_original_source", unavailable)
    report = evaluate_corpus(subset(corpus, "parameter"))
    assert report.acceptance == "error" and report.groups["all"].technical_errors == 1
    assert report.groups["all"].detection.true_positives == 1
    assert report.groups["all"].tracing.coverage == 0


def test_references_are_not_rewritten_to_match_the_investigator(corpus):
    modified = subset(corpus, "parameter")
    expected = modified.cases[0].expected_signals[0]
    expected.origin_kind = "literal"
    expected.steps[0].kind = "literal"
    expected.steps[0].symbol = None
    report = evaluate_corpus(modified)
    assert report.status == "COMPLETED" and report.acceptance == "fail"
    assert report.reference_failures == ["parameter"]
    assert report.cases[0].targets[0].origin_match is False
    assert modified.cases[0].expected_signals[0].origin_kind == "literal"


def test_deadline_marks_remaining_cases_not_run_without_starting_parsers(corpus, monkeypatch):
    monkeypatch.setattr(evaluation, "scan_source_bytes", lambda *a: pytest.fail("Expired budget started a parser"))
    report = evaluate_corpus(subset(corpus, "parameter", "shell-disabled"), budget_seconds=1e-9)
    assert report.status == "PARTIAL" and report.acceptance == "error"
    assert all(case.scan_status == "NOT_RUN" and case.error_code == "evaluation_deadline_exceeded" for case in report.cases)
    assert report.groups["all"].detection.true_negatives == 0
    assert report.timed_cases == 0 and report.case_latency_p50_ms is report.case_latency_p95_ms is None


@pytest.mark.parametrize("budget", [0, -1, 121, float("nan"), float("inf")])
def test_invalid_budgets_rejected(corpus, budget):
    with pytest.raises(EvaluationError, match="^evaluation_invalid_budget$"):
        evaluate_corpus(corpus, budget_seconds=budget)


def test_engine_change_during_run_rejects_comparison(corpus, monkeypatch):
    fingerprints = iter(["0" * 64, "1" * 64])
    monkeypatch.setattr(evaluation, "_engine_digest", lambda: next(fingerprints))
    with pytest.raises(EvaluationError, match="^evaluation_inputs_changed$"):
        evaluate_corpus(subset(corpus, "shell-disabled"))


def test_repeated_evaluation_preserves_references_and_comparable_identity(corpus):
    selected = subset(corpus, "parameter", "shell-disabled")
    before = selected.model_dump_json()
    first, second = evaluate_corpus(selected), evaluate_corpus(selected)
    assert selected.model_dump_json() == before
    assert first.corpus_sha256 == second.corpus_sha256 and first.engine_sha256 == second.engine_sha256
    assert first.groups == second.groups
    assert first.cases[0].targets == second.cases[0].targets


def test_loader_and_contract_reject_missing_oversized_or_ambiguous_corpus(tmp_path, corpus, monkeypatch):
    monkeypatch.setattr(evaluation.resources, "files", lambda *a: tmp_path)
    with pytest.raises(EvaluationError, match="evaluation_corpus_invalid_or_unavailable"):
        load_builtin_corpus()
    asset = tmp_path / "data" / "evaluation_v1.json"
    asset.parent.mkdir()
    asset.write_bytes(b" " * (evaluation.MAX_CORPUS_BYTES + 1))
    with pytest.raises(EvaluationError, match="evaluation_corpus_too_large"):
        load_builtin_corpus()
    asset.write_text('{"source":"PRIVATE_DIAGNOSTIC"', encoding="utf-8")
    with pytest.raises(EvaluationError) as error:
        load_builtin_corpus()
    assert "PRIVATE_DIAGNOSTIC" not in str(error.value)
    payload = corpus.model_dump()
    payload["cases"].append(payload["cases"][0])
    with pytest.raises(ValidationError, match="evaluation_duplicate_case"):
        EvaluationCorpus.model_validate(payload)
    payload = corpus.model_dump()
    payload["cases"][0]["expected_signals"][0]["steps"][0]["line"] = 999
    payload["cases"][0]["expected_signals"][0]["steps"][0]["end_line"] = 999
    with pytest.raises(ValidationError, match="evaluation_reference_outside_source"):
        EvaluationCorpus.model_validate(payload)


def test_cli_json_pretty_and_exit_policy(benchmark, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(AnalysisService, "evaluate_builtin_corpus", lambda self: benchmark)
    result = CliRunner().invoke(app, ["evaluate"])
    assert result.exit_code == 0 and json.loads(result.stdout)["report_type"] == "static_evaluation"
    pretty = CliRunner().invoke(app, ["--no-animation", "evaluate", "--format", "pretty"])
    assert pretty.exit_code == 0, pretty.output
    assert "Detección por caso" in pretty.stdout and "Fronteras" in pretty.stdout
    assert "unrelated-shadow-gap" in pretty.stdout and "\x1b" not in pretty.stdout
    failed = benchmark.model_copy(update={"acceptance": "fail"})
    monkeypatch.setattr(AnalysisService, "evaluate_builtin_corpus", lambda self: failed)
    assert CliRunner().invoke(app, ["evaluate"]).exit_code == 1
    incomplete = benchmark.model_copy(update={"acceptance": "error", "status": "PARTIAL"})
    monkeypatch.setattr(AnalysisService, "evaluate_builtin_corpus", lambda self: incomplete)
    assert CliRunner().invoke(app, ["evaluate"]).exit_code == 2


def test_cli_loader_failure_emits_only_stable_diagnostic(monkeypatch):
    def fail(self):
        raise EvaluationError("evaluation_corpus_invalid_or_unavailable")
    monkeypatch.setattr(AnalysisService, "evaluate_builtin_corpus", fail)
    result = CliRunner().invoke(app, ["evaluate"])
    assert result.exit_code == 2 and not result.stdout
    assert result.stderr.strip() == "evaluation_corpus_invalid_or_unavailable"


def test_builtin_corpus_resolves_independently_of_working_directory(tmp_path, corpus, monkeypatch):
    monkeypatch.chdir(tmp_path)
    loaded = load_builtin_corpus()
    assert loaded == corpus
    assert list(tmp_path.iterdir()) == []
