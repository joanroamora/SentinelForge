"""Bounded command-origin hypotheses and independent source-based binding replay."""

import base64
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from .contracts import Contract
from .local_scan import LocalScanReport
from .source_review import SourceReview, SourceReviewError, ensure_original_bytes


class LineageError(ValueError):
    @property
    def http_status(self) -> int:
        code = str(self)
        if code == "source_too_large":
            return 413
        if code in {"source_hash_mismatch", "scan_has_no_signals", "lineage_review_required",
                    "lineage_already_recorded", "lineage_submission_conflict"}:
            return 409
        if code in {"lineage_worker_timeout", "lineage_worker_unavailable"}:
            return 503
        return 422 if code in {"lineage_invalid_python", "lineage_too_complex"} else 502


class SourceSpan(Contract):
    line: int = Field(ge=1, strict=True)
    column: int = Field(ge=1, strict=True)
    end_line: int = Field(ge=1, strict=True)
    end_column: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if (self.end_line, self.end_column) <= (self.line, self.column):
            raise ValueError("lineage_invalid_span")
        return self


class TraceStep(SourceSpan):
    kind: Literal["literal", "parameter", "call_result", "assignment", "sink", "unknown"]
    symbol: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def metadata_only(self) -> Self:
        if self.kind in {"literal", "call_result"} and self.symbol is not None:
            raise ValueError("lineage_value_forbidden")
        if (self.symbol is not None and self.kind != "sink" and not self.symbol.isidentifier()):
            raise ValueError("lineage_invalid_identifier")
        if self.kind == "sink" and self.symbol not in {
                "subprocess.run", "subprocess.Popen", "subprocess.call",
                "subprocess.check_call", "subprocess.check_output"}:
            raise ValueError("lineage_invalid_sink")
        return self


class LineageHypothesis(Contract):
    signal_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    function: SourceSpan | None
    origin_kind: Literal["literal", "parameter", "call_result", "unknown"]
    reason: Literal["straight_line_bindings", "callee_not_followed", "binding_out_of_scope",
                    "expression_out_of_scope", "control_flow_or_opaque_statement",
                    "function_out_of_scope", "dynamic_arguments", "trace_limit", "argument_missing"]
    steps: list[TraceStep] = Field(min_length=2, max_length=32)

    @model_validator(mode="after")
    def path_shape(self) -> Self:
        if (self.steps[0].kind != self.origin_kind or self.steps[-1].kind != "sink" or
                any(step.kind != "assignment" for step in self.steps[1:-1])):
            raise ValueError("lineage_invalid_path")
        expected = ("straight_line_bindings" if self.origin_kind in {"literal", "parameter"}
                    else "callee_not_followed" if self.origin_kind == "call_result" else None)
        if (expected is not None and self.reason != expected or
                expected is None and self.reason in {"straight_line_bindings", "callee_not_followed"}):
            raise ValueError("lineage_origin_reason_mismatch")
        return self


class LineageCheck(Contract):
    signal_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: Literal["steps_reproduced", "inconclusive", "not_reproduced"]
    step_results: list[Literal["reproduced", "inconclusive", "not_reproduced"]] = Field(
        min_length=2, max_length=32)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        states = set(self.step_results)
        expected = ("not_reproduced" if "not_reproduced" in states else
                    "inconclusive" if "inconclusive" in states else "steps_reproduced")
        if self.result != expected:
            raise ValueError("lineage_check_mismatch")
        return self


class ArgumentTrace(Contract):
    hypothesis: LineageHypothesis
    verification: LineageCheck

    @model_validator(mode="after")
    def aligned(self) -> Self:
        if (self.hypothesis.signal_fingerprint != self.verification.signal_fingerprint or
                len(self.hypothesis.steps) != len(self.verification.step_results) or
                self.hypothesis.origin_kind in {"unknown", "call_result"} and
                self.verification.result == "steps_reproduced"):
            raise ValueError("lineage_trace_mismatch")
        return self


class ArgumentInvestigation(Contract):
    schema_version: Literal["1.0"] = "1.0"
    investigator: Literal["sentinelforge-backward-slice"] = "sentinelforge-backward-slice"
    investigator_version: Literal["1.0"] = "1.0"
    verifier: Literal["sentinelforge-forward-bindings"] = "sentinelforge-forward-bindings"
    verifier_version: Literal["1.0"] = "1.0"
    python_version: str = Field(default_factory=platform.python_version)
    checked_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    scope: Literal["single_function_assignments"] = "single_function_assignments"
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_retained: Literal[False] = False
    traces: list[ArgumentTrace] = Field(min_length=1, max_length=100)
    limitations: list[str] = Field(default_factory=lambda: [
        "Solo sigue asignaciones simples dentro de una función del mismo archivo; no ejecuta código.",
        "Parámetro no significa entrada externa; literal no significa seguro. No evalúa sanitizadores.",
        "No sigue llamadas, flujo de control, atributos, colecciones, cierres ni efectos de otros hilos.",
        "32 pasos por señal, 512 en total y 128 sentencias previas; los límites dejan origen desconocido.",
        "El comprobador usa otra estrategia en otro proceso, pero comparte el parser de Python.",
        "No demuestra alcanzabilidad ni explotabilidad. Señales y declaraciones siguen sin verificar.",
        "Guarda identificadores y ubicaciones; omite código, comentarios y valores literales.",
    ])

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if (sum(len(trace.hypothesis.steps) for trace in self.traces) > 512 or
                len({trace.hypothesis.signal_fingerprint for trace in self.traces}) != len(self.traces)):
            raise ValueError("lineage_trace_budget_or_identity")
        return self


class ArgumentInvestigationReceipt(Contract):
    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str
    submission_id: UUID
    revision: int = Field(ge=3, strict=True)
    investigation: ArgumentInvestigation


class _Proposals(Contract):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposals: list[LineageHypothesis] = Field(min_length=1, max_length=100)


class _Checks(Contract):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks: list[LineageCheck] = Field(min_length=1, max_length=100)


def require_corroboration(review: SourceReview | None) -> None:
    if review is None or any(item.result != "pattern_reproduced" for item in review.decisions):
        raise LineageError("lineage_review_required")


def original_lineage_bytes(report: LocalScanReport, content: bytes) -> None:
    try:
        ensure_original_bytes(report, content)
    except SourceReviewError as error:
        raise LineageError(str(error)) from error


_WorkerModel = TypeVar("_WorkerModel", bound=Contract)


def _worker(filename: str, data: dict, model: type[_WorkerModel]) -> _WorkerModel:
    wire = json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    try:
        process = subprocess.run([sys.executable, "-I", "-S", str(Path(__file__).with_name(filename))],
                                 input=wire, capture_output=True, timeout=5, check=False)
    except subprocess.TimeoutExpired as error:
        raise LineageError("lineage_worker_timeout") from error
    except OSError as error:
        raise LineageError("lineage_worker_unavailable") from error
    if process.returncode:
        raise LineageError("lineage_worker_failed")
    if len(process.stdout) > 1048576:
        raise LineageError("lineage_invalid_output")
    try:
        result = json.loads(process.stdout)
        if isinstance(result, dict) and set(result) == {"error"} and result["error"] in (
                "lineage_invalid_python", "lineage_too_complex", "source_hash_mismatch"):
            raise LineageError(result["error"])
        return model.model_validate(result)
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        if isinstance(error, LineageError):
            raise
        raise LineageError("lineage_invalid_output") from error


def investigate_argument(report: LocalScanReport, content: bytes,
                         review: SourceReview | None) -> ArgumentInvestigation:
    original_lineage_bytes(report, content)
    require_corroboration(review)
    if (review.source_sha256 != report.source.sha256 or
            [item.signal_fingerprint for item in review.decisions] !=
            [item.fingerprint for item in report.signals]):
        raise LineageError("lineage_review_required")
    signals = [signal.model_dump(include={"fingerprint", "call", "line", "column",
                                         "end_line", "end_column"}) for signal in report.signals]
    data = {"source": base64.b64encode(content).decode("ascii"),
                "sha256": report.source.sha256, "signals": signals}
    proposed = _worker("_lineage_worker.py", data, _Proposals)
    fingerprints = [signal.fingerprint for signal in report.signals]
    if (proposed.source_sha256 != report.source.sha256 or
            [item.signal_fingerprint for item in proposed.proposals] != fingerprints or
            sum(len(item.steps) for item in proposed.proposals) > 512):
        raise LineageError("lineage_invalid_output")
    for proposal, signal in zip(proposed.proposals, report.signals, strict=True):
        end = proposal.steps[-1]
        if (end.symbol != signal.call or any(getattr(end, key) != getattr(signal, key)
                for key in ("line", "column", "end_line", "end_column"))):
            raise LineageError("lineage_invalid_output")
    checked = _worker("_lineage_check_worker.py",
                      data | {"proposals": [item.model_dump() for item in proposed.proposals]}, _Checks)
    if (checked.source_sha256 != report.source.sha256 or
            [item.signal_fingerprint for item in checked.checks] != fingerprints):
        raise LineageError("lineage_invalid_output")
    try:
        return ArgumentInvestigation(source_sha256=report.source.sha256, traces=[
            ArgumentTrace(hypothesis=proposal, verification=check)
            for proposal, check in zip(proposed.proposals, checked.checks, strict=True)])
    except ValueError as error:
        raise LineageError("lineage_invalid_output") from error
