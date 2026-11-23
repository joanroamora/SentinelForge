"""A separate frozen corpus exposes boundaries without moving the original baseline."""

import json

import pytest
from typer.testing import CliRunner

from sentinelforge import evaluation
from sentinelforge.cli import app
from sentinelforge.evaluation import EvaluationError, _digest, load_builtin_corpus
from sentinelforge.evaluation_contracts import BuiltinCorpus
from sentinelforge.service import AnalysisService

BASELINE_HASH = "7b6e4d638246e2711d4934ab472b36671e7da03c7c6bf7e04d9db48ad1e63cbd"
CHALLENGE_HASH = "32ec0eecb77c3e50a6619187226417df54a6fdba858dd9f5e4764d1e8d5883fc"
GAPS = {
    "function-assignment-global-import", "function-assignment-local-import",
    "two-hop-module-alias", "annotated-module-capture",
    "constant-true-conditional-import", "unrelated-local-assignment",
}
RESOLVED = {"function-assignment-global-import", "function-assignment-local-import",
            "unrelated-local-assignment", "annotated-module-capture", "two-hop-module-alias",
            "constant-true-conditional-import"}


@pytest.fixture(scope="module")
def challenge_report(tmp_path_factory):
    destination = tmp_path_factory.mktemp("challenge") / "not-created" / "database.sqlite3"
    report = AnalysisService(destination).evaluate_builtin_corpus(BuiltinCorpus.challenge)
    assert not destination.parent.exists()
    return report


def test_reference_sets_have_distinct_pinned_identities_and_original_sources_are_unchanged():
    original, challenge = load_builtin_corpus(), load_builtin_corpus(BuiltinCorpus.challenge)
    assert original.id == "sf-py-001-local" and len(original.cases) == 28
    assert challenge.id == "sf-py-001-challenge" and len(challenge.cases) == 20
    assert _digest(original.model_dump()) == BASELINE_HASH
    assert _digest(challenge.model_dump()) == CHALLENGE_HASH
    assert challenge.reference_review == "not_independently_audited"
    assert {case.id for case in challenge.cases if case.scope == "boundary"} == GAPS
    assert all(case.expected_signals for case in challenge.cases if case.scope == "boundary")
    assert sum(len(case.expected_signals) for case in challenge.cases) == 13


def test_measured_challenge_separates_detection_and_trace_limits_from_supported_cases(challenge_report):
    report = challenge_report
    assert report.corpus_id == "sf-py-001-challenge" and report.corpus_sha256 == CHALLENGE_HASH
    assert report.evaluator_version == "1.1" and report.detector_version == "1.8"
    assert report.acceptance == "pass" and report.status == "COMPLETED"
    assert not report.reference_failures and report.expected_error_matches == 2
    assert set(report.boundary_gaps) == GAPS - RESOLVED
    assert all(case.reference_match for case in report.cases if case.id in RESOLVED)
    supported, total = report.groups["in_scope"], report.groups["all"]
    assert supported.cases == 12 and supported.detection.true_positives == 6
    assert supported.detection.true_negatives == 6 and supported.detection.false_positives == 0
    assert supported.localization.matched == supported.tracing.traced == 7
    assert total.eligible_detection_cases == 18 and total.technical_errors == 0
    assert total.detection.false_negatives == 0 and total.detection.recall == 1.0
    assert total.localization.matched == 13 and total.localization.missed == 0
    assert total.localization.recall == total.tracing.coverage == 1.0
    assert total.tracing.reference_agreement_end_to_end == 1.0
    assert total.tracing.inconclusive == 0
    assert all(not case.reference_match and not case.observed_signals
               for case in report.cases if case.id in GAPS - RESOLVED)


def test_challenge_output_does_not_echo_source_directives_or_literal_values(challenge_report):
    output = challenge_report.model_dump_json()
    for text in ("CHALLENGE_PROMPT_PRIVATE", "CHALLENGE_LITERAL_PRIVATE",
                 "CHALLENGE_FIXTURE_MUST_NOT_RUN", "import subprocess", "def launch"):
        assert text not in output
    assert challenge_report.source_retained is False


@pytest.mark.parametrize("selection", ["../other.json", "unknown", "", None, []])
def test_unregistered_selections_are_rejected_before_any_file_is_read(selection, monkeypatch):
    def forbidden(*args):
        pytest.fail("Unregistered corpus caused resource access")
    monkeypatch.setattr(evaluation.resources, "files", forbidden)
    with pytest.raises(EvaluationError, match="^evaluation_unknown_corpus$"):
        load_builtin_corpus(selection)


@pytest.mark.parametrize("selection", list(BuiltinCorpus))
def test_each_packaged_asset_keeps_size_and_parser_guards(selection, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation.resources, "files", lambda *args: tmp_path)
    filename, _ = evaluation.BUILTIN_CORPORA[selection]
    with pytest.raises(EvaluationError, match="^evaluation_corpus_invalid_or_unavailable$"):
        load_builtin_corpus(selection)
    asset = tmp_path / filename
    asset.parent.mkdir()
    asset.write_bytes(b" " * (evaluation.MAX_CORPUS_BYTES + 1))
    with pytest.raises(EvaluationError, match="^evaluation_corpus_too_large$"):
        load_builtin_corpus(selection)
    asset.write_text('{"source":"PRIVATE_PARSER_DIAGNOSTIC"', encoding="utf-8")
    with pytest.raises(EvaluationError, match="^evaluation_corpus_invalid_or_unavailable$") as error:
        load_builtin_corpus(selection)
    assert "PRIVATE_PARSER_DIAGNOSTIC" not in str(error.value)


@pytest.mark.parametrize("selection,other", [
    (BuiltinCorpus.baseline, BuiltinCorpus.challenge), (BuiltinCorpus.challenge, BuiltinCorpus.baseline),
])
def test_wrong_packaged_identity_cannot_silently_replace_a_reference_set(selection, other, tmp_path, monkeypatch):
    swapped = load_builtin_corpus(other).model_dump_json()
    monkeypatch.setattr(evaluation.resources, "files", lambda *args: tmp_path)
    filename, _ = evaluation.BUILTIN_CORPORA[selection]
    asset = tmp_path / filename
    asset.parent.mkdir()
    asset.write_text(swapped, encoding="utf-8")
    with pytest.raises(EvaluationError, match="^evaluation_corpus_identity_mismatch$"):
        load_builtin_corpus(selection)


def test_cli_forwards_selection_and_renders_the_completed_reference_set_in_both_formats(challenge_report, monkeypatch):
    selected = []

    def evaluate(self, corpus):
        selected.append(corpus)
        return challenge_report

    monkeypatch.setattr(AnalysisService, "evaluate_builtin_corpus", evaluate)
    monkeypatch.setenv("NO_COLOR", "1")
    result = CliRunner().invoke(app, ["evaluate", "--corpus", "challenge", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["boundary_gaps"] == challenge_report.boundary_gaps
    pretty = CliRunner().invoke(app, ["--no-animation", "evaluate", "--corpus", "challenge", "--format", "pretty"])
    assert pretty.exit_code == 0, pretty.output
    assert "sf-py-001-challenge" in pretty.stdout and "Fronteras" in pretty.stdout
    assert "Señal no detectada" not in pretty.stdout
    assert selected == [BuiltinCorpus.challenge, BuiltinCorpus.challenge]
    assert "\x1b" not in pretty.stdout


def test_cli_rejects_file_paths_before_calling_the_service(monkeypatch):
    def forbidden(*args):
        pytest.fail("CLI forwarded an unregistered corpus")
    monkeypatch.setattr(AnalysisService, "evaluate_builtin_corpus", forbidden)
    result = CliRunner().invoke(app, ["evaluate", "--corpus", "../other.json"])
    assert result.exit_code == 2


def test_both_corpora_resolve_outside_the_repository_without_executing_fixtures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert len(load_builtin_corpus().cases) == 28
    assert len(load_builtin_corpus(BuiltinCorpus.challenge).cases) == 20
    assert list(tmp_path.iterdir()) == []
