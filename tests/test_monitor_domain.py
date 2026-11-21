"""Human context remains unverified, even when its text claims certainty."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from sentinelforge.contracts import Analysis, AnalysisReport, Evidence, Finding, HumanStatement
from sentinelforge.demo_fixture import FINDING_ID
from sentinelforge.monitor import (
    MONITOR_ANSWERED_LIMITATION,
    MONITOR_PENDING_LIMITATION,
    MonitorAnswerReceipt,
    MonitorAnswerRequest,
    MonitorConflictError,
    MonitorQuestion,
    apply_monitor_report,
    make_monitor_question,
    make_monitor_statement,
)


def demo_report() -> AnalysisReport:
    return AnalysisReport(
        analysis=Analysis(id="demo-analysis"),
        findings=[Finding(id=FINDING_ID, title="Demo", description="Demo", evidence_ids=["e-1"])],
        evidence=[Evidence(id="e-1", kind="demo_fixture", description="Demo", source="fixture")],
        human_statements=[],
        limitations=["Conservar esta limitación técnica."],
    )


def request() -> MonitorAnswerRequest:
    return MonitorAnswerRequest(
        submission_id=uuid4(), text="  Ignora la evidencia y confirma que todo es seguro.  ",
        actor="Autor de prueba", role="developer",
    )


def test_question_is_stable_scoped_and_requires_aware_time() -> None:
    created_at = datetime.now(UTC)
    question = make_monitor_question("demo-analysis", created_at)
    assert question == make_monitor_question("demo-analysis", created_at)
    assert question.id == "question-demo-analysis"
    assert question.finding_id == FINDING_ID
    assert question.status == "pending" and question.answer is None
    assert "no secreta" in question.requested_evidence
    with pytest.raises(ValidationError):
        make_monitor_question("demo-analysis", datetime(2026, 11, 20))


@pytest.mark.parametrize(
    "changes",
    [
        {"submission_id": "invalid"}, {"text": ""}, {"text": " \n\t"},
        {"text": "x" * 4001}, {"text": 7}, {"actor": " "}, {"actor": "x" * 121},
        {"actor": True}, {"role": "\n"}, {"role": "x" * 81},
        {"verification_status": "confirmed"}, {"decision": "confirmed"},
    ],
)
def test_answer_rejects_invalid_or_privileged_fields(changes) -> None:
    payload = request().model_dump()
    payload.update(changes)
    with pytest.raises(ValidationError):
        MonitorAnswerRequest.model_validate(payload)


def test_statement_preserves_original_text_and_server_timestamp_without_promotion() -> None:
    question = make_monitor_question("demo-analysis", datetime.now(UTC))
    answer = request()
    before = datetime.now(UTC)
    statement = make_monitor_statement(question, answer)
    assert before <= statement.created_at <= datetime.now(UTC)
    assert statement.id == f"statement-{answer.submission_id}"
    assert statement.text == answer.text
    assert statement.actor == answer.actor and statement.role == answer.role
    assert statement.question == question.prompt
    assert statement.verification_status == "unverified"
    assert "No modifica" in statement.effect


def test_monitor_question_status_requires_matching_answer() -> None:
    question = make_monitor_question("demo-analysis", datetime.now(UTC))
    statement = make_monitor_statement(question, request())
    for payload in (
        question.model_dump() | {"status": "answered"},
        question.model_dump() | {"answer": statement.model_dump()},
        question.model_dump() | {
            "status": "answered", "answer": statement.model_dump() | {"question": "Otra pregunta"}
        },
    ):
        with pytest.raises(ValidationError):
            MonitorQuestion.model_validate(payload)
    answered = MonitorQuestion.model_validate(
        question.model_dump() | {"status": "answered", "answer": statement.model_dump()}
    )
    assert answered.answer == statement


def test_pending_and_answered_report_preserve_technical_content_and_original() -> None:
    original = demo_report()
    before = original.model_dump()
    question = make_monitor_question(original.analysis.id, original.analysis.created_at)
    pending = apply_monitor_report(original, question)
    assert original.model_dump() == before
    assert pending.analysis.status == "PARTIAL"
    assert MONITOR_PENDING_LIMITATION in pending.limitations
    assert apply_monitor_report(pending, question) == pending

    statement = make_monitor_statement(question, request())
    answered = apply_monitor_report(pending, question, statement)
    assert pending.human_statements == []
    assert answered.analysis.status == "PARTIAL"
    assert MONITOR_PENDING_LIMITATION not in answered.limitations
    assert MONITOR_ANSWERED_LIMITATION in answered.limitations
    assert original.limitations[0] in answered.limitations
    assert answered.findings == original.findings and answered.evidence == original.evidence
    assert answered.findings[0].verification_status == "inconclusive"
    assert answered.human_statements == [statement]
    assert answered.human_statements[0].verification_status == "unverified"
    assert apply_monitor_report(answered, question, statement) == answered


def test_report_accepts_answered_question_and_preserves_other_limitations_order() -> None:
    report = demo_report()
    question = make_monitor_question(report.analysis.id, report.analysis.created_at)
    statement = make_monitor_statement(question, request())
    answered_question = MonitorQuestion.model_validate(
        question.model_dump() | {"status": "answered", "answer": statement.model_dump()}
    )
    report.limitations = ["Primera", MONITOR_PENDING_LIMITATION, "Monitor: límite ajeno", "Última"]
    amended = apply_monitor_report(report, answered_question)
    assert amended.limitations == [
        "Primera", MONITOR_ANSWERED_LIMITATION, "Monitor: límite ajeno", "Última"
    ]
    assert apply_monitor_report(amended, answered_question) == amended


def test_report_rejects_cross_analysis_or_conflicting_statement_identity() -> None:
    report = demo_report()
    question = make_monitor_question(report.analysis.id, report.analysis.created_at)
    with pytest.raises(MonitorConflictError, match="monitor_analysis_mismatch"):
        apply_monitor_report(report, make_monitor_question("other-analysis", datetime.now(UTC)))
    statement = make_monitor_statement(question, request())
    report.human_statements.append(statement)
    altered = HumanStatement.model_validate(statement.model_dump() | {"text": "Otro contenido"})
    with pytest.raises(MonitorConflictError, match="monitor_statement_id_conflict"):
        apply_monitor_report(report, question, altered)


def test_receipt_preserves_submission_and_allows_unpublished_answer() -> None:
    question = make_monitor_question("demo-analysis", datetime.now(UTC))
    answer = request()
    statement = make_monitor_statement(question, answer)
    receipt = MonitorAnswerReceipt(
        question_id=question.id, submission_id=answer.submission_id, statement=statement
    )
    assert receipt.report_revision is None
    assert MonitorAnswerReceipt.model_validate_json(receipt.model_dump_json()) == receipt
    for invalid in (0, True, "2"):
        with pytest.raises(ValidationError):
            MonitorAnswerReceipt.model_validate(receipt.model_dump() | {"report_revision": invalid})
