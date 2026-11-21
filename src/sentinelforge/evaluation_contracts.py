"""Versioned evaluation references and results; references are not security verdicts."""

from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from .argument_lineage import ArgumentTrace, SourceSpan, TraceStep
from .contracts import Contract
from .local_scan import LocalScanSignal

CaseScope = Literal["in_scope", "boundary", "input_error"]
OriginKind = Literal["literal", "parameter", "call_result", "unknown"]


class SignalReference(SourceSpan):
    call: Literal["subprocess.run", "subprocess.Popen", "subprocess.call",
                  "subprocess.check_call", "subprocess.check_output"]

    def key(self) -> tuple:
        return self.call, self.line, self.column, self.end_line, self.end_column


class ExpectedSignal(SignalReference):
    origin_kind: OriginKind
    steps: list[TraceStep] = Field(min_length=2, max_length=32)
    verification: Literal["steps_reproduced", "inconclusive"]

    @model_validator(mode="after")
    def reference_shape(self) -> Self:
        sink = self.steps[-1]
        expected = "steps_reproduced" if self.origin_kind in {"literal", "parameter"} else "inconclusive"
        if (self.steps[0].kind != self.origin_kind or sink.kind != "sink" or
                any(step.kind != "assignment" for step in self.steps[1:-1]) or
                self.verification != expected or
                (sink.symbol, sink.line, sink.column, sink.end_line, sink.end_column) != self.key()):
            raise ValueError("evaluation_invalid_reference_path")
        return self


class EvaluationCase(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    scope: CaseScope
    rationale: str = Field(min_length=1, max_length=1000)
    source: str = Field(max_length=65537)
    expected_signals: list[ExpectedSignal] = Field(default_factory=list, max_length=100)
    expected_error: Literal["invalid_python", "source_too_large"] | None = None

    @model_validator(mode="after")
    def reference_consistency(self) -> Self:
        if (len(self.source.encode("utf-8")) > 65537 or
                (self.scope == "input_error") != (self.expected_error is not None) or
                self.expected_error is not None and self.expected_signals or
                len({signal.key() for signal in self.expected_signals}) != len(self.expected_signals)):
            raise ValueError("evaluation_invalid_case")
        lines = self.source.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for signal in self.expected_signals:
            for span in [signal, *signal.steps]:
                if (span.end_line > len(lines) or span.line > len(lines) or
                        span.column > len(lines[span.line - 1].encode("utf-8")) + 1 or
                        span.end_column > len(lines[span.end_line - 1].encode("utf-8")) + 1):
                    raise ValueError("evaluation_reference_outside_source")
        return self


class EvaluationCorpus(Contract):
    schema_version: Literal["1.0"] = "1.0"
    id: Literal["sf-py-001-local"] = "sf-py-001-local"
    version: Literal["1.0"] = "1.0"
    reference_method: Literal["authored_static_expectations"] = "authored_static_expectations"
    reference_review: Literal["not_independently_audited"] = "not_independently_audited"
    cases: list[EvaluationCase] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("evaluation_duplicate_case")
        return self


class TargetEvaluation(Contract):
    expected: ExpectedSignal
    detected: bool
    review_result: Literal["pattern_reproduced", "not_reproduced", "inconclusive"] | None = None
    observed_trace: ArgumentTrace | None = None
    origin_match: bool | None = None
    path_match: bool | None = None
    verification_match: bool | None = None


class CaseEvaluation(Contract):
    id: str
    scope: CaseScope
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_error: str | None
    scan_status: Literal["COMPLETED", "ERROR", "NOT_RUN"]
    error_code: str | None = None
    observed_signals: list[SignalReference] = Field(default_factory=list)
    targets: list[TargetEvaluation] = Field(default_factory=list)
    reference_match: bool
    technical_error: bool = False
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)


class DetectionMetrics(Contract):
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None


class LocalizationMetrics(Contract):
    matched: int = 0
    extra: int = 0
    missed: int = 0
    precision: float | None = None
    recall: float | None = None


class TraceMetrics(Contract):
    expected: int = 0
    traced: int = 0
    origin_correct: int = 0
    path_correct: int = 0
    jointly_correct: int = 0
    inconclusive: int = 0
    coverage: float | None = None
    origin_accuracy_when_traced: float | None = None
    reference_agreement_end_to_end: float | None = None
    inconclusive_rate_when_traced: float | None = None


class GroupMetrics(Contract):
    cases: int
    eligible_detection_cases: int
    technical_errors: int
    detection: DetectionMetrics
    localization: LocalizationMetrics
    tracing: TraceMetrics


class EvaluationReport(Contract):
    schema_version: Literal["1.0"] = "1.0"
    report_type: Literal["static_evaluation"] = "static_evaluation"
    evaluator_version: Literal["1.0"] = "1.0"
    is_synthetic: Literal[True] = True
    source_retained: Literal[False] = False
    corpus_id: str
    corpus_version: str
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_review: Literal["not_independently_audited"] = "not_independently_audited"
    engine_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    detector_version: str
    python_version: str
    pydantic_version: str
    platform: str
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["COMPLETED", "PARTIAL"]
    acceptance: Literal["pass", "fail", "error"]
    cases: list[CaseEvaluation]
    groups: dict[Literal["all", "in_scope", "boundary", "input_error"], GroupMetrics]
    reference_failures: list[str]
    boundary_gaps: list[str]
    expected_error_matches: int
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)
    timed_cases: int
    case_latency_p50_ms: float | None
    case_latency_p95_ms: float | None
    limitations: list[str] = Field(default_factory=lambda: [
        "Corpus sintético de desarrollo, pequeño y sin auditoría independiente; no mide seguridad general.",
        "Las etiquetas describen patrones y recorridos estáticos, no vulnerabilidades ni explotabilidad.",
        "Las métricas de detección usan casos elegibles; errores técnicos se cuentan aparte, nunca como negativos.",
        "La localización mide señales exactas; la detección por caso solo mide presencia o ausencia.",
        "La exactitud condicionada al trazado excluye lo no trazado; consultar también cobertura y acuerdo total.",
        "Un resultado inconcluso puede coincidir con la referencia y sigue sin demostrar seguridad.",
        "Los tiempos incluyen procesos Python y excluyen casos no iniciados; una ejecución por caso, sin garantía de rendimiento.",
    ])


def observed_reference(signal: LocalScanSignal) -> SignalReference:
    return SignalReference.model_validate(signal.model_dump(include={
        "call", "line", "column", "end_line", "end_column"}))
