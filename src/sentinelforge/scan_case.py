"""Persistent real scan contracts; static signals remain unverified observations."""

from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, model_serializer, model_validator

from .argument_lineage import ArgumentInvestigation, require_corroboration
from .contracts import Contract, HumanStatement
from .local_scan import LocalScanReport
from .monitor import MonitorAnswerRequest, MonitorConflictError
from .source_review import SourceReview


class ScanContextQuestion(Contract):
    id: str
    signal_fingerprint: str
    prompt: str = (
        "¿De dónde proviene el comando y qué controles limitan sus argumentos? "
        "Describe solo contexto no secreto para la primera señal."
    )
    status: Literal["pending", "answered"] = "pending"


class ScanCase(Contract):
    schema_version: Literal["1.0", "1.1", "1.2"] = "1.0"
    report_type: Literal["local_scan_case"] = "local_scan_case"
    is_demo: Literal[False] = False
    id: str = Field(pattern=r"^scan-[0-9a-f]{64}$")
    revision: int = Field(ge=1, strict=True)
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["COMPLETED", "PARTIAL", "ERROR"]
    report: LocalScanReport
    question: ScanContextQuestion | None = None
    human_statements: list[HumanStatement] = Field(default_factory=list, max_length=1)
    source_review: SourceReview | None = None
    argument_investigation: ArgumentInvestigation | None = None

    @model_serializer(mode="wrap")
    def versioned_payload(self, handler):
        data = handler(self)
        if self.schema_version == "1.0":
            data.pop("source_review", None)
        if self.schema_version != "1.2":
            data.pop("argument_investigation", None)
        return data

    @model_validator(mode="after")
    def case_matches_observation(self) -> Self:
        if (self.source_review is None) != (self.schema_version == "1.0"):
            raise ValueError("scan_case_review_version_mismatch")
        if (self.argument_investigation is not None) != (self.schema_version == "1.2"):
            raise ValueError("scan_case_investigation_version_mismatch")
        if self.report.scan_fingerprint is None or self.id != "scan-" + self.report.scan_fingerprint:
            raise ValueError("scan_case_identity_mismatch")
        expected = ("ERROR" if self.report.status == "ERROR" else
                    "PARTIAL" if self.report.signals else "COMPLETED")
        if self.status != expected or bool(self.question) != bool(self.report.signals):
            raise ValueError("scan_case_status_mismatch")
        if self.question is not None:
            if (self.question.id != "question-" + self.id or
                    self.question.signal_fingerprint != self.report.signals[0].fingerprint or
                    (self.question.status == "answered") != bool(self.human_statements)):
                raise ValueError("scan_case_question_mismatch")
            if any(item.question != self.question.prompt for item in self.human_statements):
                raise ValueError("scan_case_statement_mismatch")
        elif self.human_statements:
            raise ValueError("scan_case_has_no_question")
        if self.source_review is not None and (
                self.report.source is None or self.source_review.source_sha256 != self.report.source.sha256
                or [item.signal_fingerprint for item in self.source_review.decisions] !=
                [item.fingerprint for item in self.report.signals]):
            raise ValueError("scan_case_review_reference_mismatch")
        if self.argument_investigation is not None:
            require_corroboration(self.source_review)
            investigation = self.argument_investigation
            if (investigation.source_sha256 != self.report.source.sha256 or
                    [item.hypothesis.signal_fingerprint for item in investigation.traces] !=
                    [item.fingerprint for item in self.report.signals]):
                raise ValueError("scan_case_investigation_reference_mismatch")
            for trace, signal in zip(investigation.traces, self.report.signals, strict=True):
                sink = trace.hypothesis.steps[-1]
                if sink.symbol != signal.call or any(getattr(sink, key) != getattr(signal, key)
                        for key in ("line", "column", "end_line", "end_column")):
                    raise ValueError("scan_case_investigation_sink_mismatch")
        return self


class ScanAnswerReceipt(Contract):
    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str
    submission_id: UUID
    question_id: str
    revision: int = Field(ge=2)
    statement: HumanStatement


def new_scan_case(report: LocalScanReport) -> ScanCase:
    if report.scan_fingerprint is None:
        raise ValueError(report.errors[0].code if report.errors else "scan_source_missing")
    identity = "scan-" + report.scan_fingerprint
    return ScanCase(
        id=identity, revision=1, report=report,
        status="ERROR" if report.status == "ERROR" else "PARTIAL" if report.signals else "COMPLETED",
        question=(ScanContextQuestion(id="question-" + identity,
                                     signal_fingerprint=report.signals[0].fingerprint)
                  if report.signals else None),
    )


def answer_scan_case(case: ScanCase, request: MonitorAnswerRequest) -> ScanCase:
    if case.question is None:
        raise LookupError("scan_question_not_found")
    if case.human_statements:
        raise MonitorConflictError("monitor_question_already_answered")
    statement = HumanStatement(
        id="statement-" + str(request.submission_id), question=case.question.prompt,
        text=request.text, actor=request.actor, role=request.role,
        effect="Contexto humano recibido sin verificar. No modifica la observación técnica.",
    )
    payload = case.model_dump()
    payload["revision"] += 1
    payload["question"]["status"] = "answered"
    payload["human_statements"] = [statement.model_dump()]
    return ScanCase.model_validate(payload)
