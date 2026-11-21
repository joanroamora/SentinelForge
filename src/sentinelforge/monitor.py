"""Typed human context for the local Monitor, without automatic verification."""

from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .contracts import AnalysisReport, Contract, HumanStatement
from .demo_fixture import FINDING_ID

MONITOR_PENDING_LIMITATION = (
    "Monitor: pregunta pendiente. La ejecución continúa con informe parcial."
)
MONITOR_ANSWERED_LIMITATION = (
    "Monitor: respuesta humana recibida sin verificación técnica. El informe permanece parcial."
)


class MonitorQuestion(Contract):
    schema_version: Literal["1.0"] = "1.0"
    is_demo: Literal[True] = True
    id: str
    analysis_id: str
    finding_id: str
    prompt: str
    reason: str
    requested_evidence: str
    created_at: AwareDatetime
    status: Literal["pending", "answered"] = "pending"
    answer: HumanStatement | None = None

    @model_validator(mode="after")
    def answer_matches_status(self) -> Self:
        if (self.status == "answered") != (self.answer is not None):
            raise ValueError("monitor_question_answer_status_mismatch")
        if self.answer is not None and self.answer.question != self.prompt:
            raise ValueError("monitor_question_answer_prompt_mismatch")
        return self


class MonitorAnswerRequest(Contract):
    submission_id: UUID
    text: str = Field(strict=True, min_length=1, max_length=4000, pattern=r"\S")
    actor: str = Field(strict=True, min_length=1, max_length=120, pattern=r"\S")
    role: str = Field(strict=True, min_length=1, max_length=80, pattern=r"\S")


class MonitorAnswerReceipt(Contract):
    schema_version: Literal["1.0"] = "1.0"
    question_id: str
    submission_id: UUID
    statement: HumanStatement
    report_revision: int | None = Field(default=None, ge=1, strict=True)


class MonitorConflictError(ValueError):
    """A human answer conflicts with an existing immutable Monitor record."""


def make_monitor_question(analysis_id: str, created_at: datetime) -> MonitorQuestion:
    return MonitorQuestion(
        id=f"question-{analysis_id}",
        analysis_id=analysis_id,
        finding_id=FINDING_ID,
        prompt=(
            "¿Qué control de autenticación se aplica a /demo? "
            "Describe únicamente contexto y configuración no secreta."
        ),
        reason="La fixture no permite confirmar controles del entorno real.",
        requested_evidence=(
            "Descripción o configuración no secreta del control y su ubicación. "
            "No envíes contraseñas, tokens ni biometría."
        ),
        created_at=created_at,
    )


def make_monitor_statement(
    question: MonitorQuestion, request: MonitorAnswerRequest
) -> HumanStatement:
    return HumanStatement(
        id=f"statement-{request.submission_id}",
        question=question.prompt,
        text=request.text,
        actor=request.actor,
        role=request.role,
        created_at=datetime.now(UTC),
        verification_status="unverified",
        effect="Aporta contexto humano no verificado. No modifica la conclusión técnica simulada.",
    )


def apply_monitor_report(
    report: AnalysisReport,
    question: MonitorQuestion,
    statement: HumanStatement | None = None,
) -> AnalysisReport:
    """Preserve technical evidence and retain the original human declaration."""
    if report.analysis.id != question.analysis_id:
        raise MonitorConflictError("monitor_analysis_mismatch")
    if question.answer is not None and statement is not None and question.answer != statement:
        raise MonitorConflictError("monitor_question_already_answered")
    answer = question.answer if statement is None else statement
    if answer is not None and answer.question != question.prompt:
        raise MonitorConflictError("monitor_statement_question_mismatch")

    amended = AnalysisReport.model_validate(report.model_dump())
    amended.analysis.status = "PARTIAL"
    if answer is not None:
        existing = next((item for item in amended.human_statements if item.id == answer.id), None)
        if existing is not None and existing != answer:
            raise MonitorConflictError("monitor_statement_id_conflict")
        if existing is None:
            amended.human_statements.append(HumanStatement.model_validate(answer.model_dump()))

    limitation = MONITOR_PENDING_LIMITATION if answer is None else MONITOR_ANSWERED_LIMITATION
    owned = {MONITOR_PENDING_LIMITATION, MONITOR_ANSWERED_LIMITATION}
    limitations: list[str] = []
    replaced = False
    for item in amended.limitations:
        if item in owned:
            if not replaced:
                limitations.append(limitation)
                replaced = True
        else:
            limitations.append(item)
    if not replaced:
        limitations.append(limitation)
    amended.limitations = limitations
    return amended
