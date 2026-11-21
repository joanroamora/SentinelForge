"""Recheck static observations against re-supplied original bytes, without execution."""

import base64
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, ValidationError, model_validator

from .contracts import Contract
from .local_scan import LocalScanReport
from .local_source import MAX_SOURCE_BYTES


class SourceReviewError(ValueError):
    @property
    def http_status(self) -> int:
        code = str(self)
        if code == "source_too_large":
            return 413
        if code in {"source_hash_mismatch", "scan_has_no_signals", "source_review_already_recorded",
                    "source_review_submission_conflict"}:
            return 409
        if code in {"source_verifier_timeout", "source_verifier_unavailable"}:
            return 503
        return 422 if code in {"source_verifier_invalid_python", "source_verifier_too_complex"} else 502


class SourceDecision(Contract):
    signal_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: Literal["pattern_reproduced", "not_reproduced", "inconclusive"]
    reason: Literal["literal_shell_true_observed", "location_does_not_match",
                    "call_does_not_match", "shell_true_not_observed", "binding_not_established"]

    @model_validator(mode="after")
    def reason_matches_result(self):
        expected = ("pattern_reproduced" if self.reason == "literal_shell_true_observed" else
                    "inconclusive" if self.reason == "binding_not_established" else "not_reproduced")
        if self.result != expected:
            raise ValueError("source_review_decision_mismatch")
        return self


class SourceReview(Contract):
    schema_version: Literal["1.0"] = "1.0"
    verifier: Literal["sentinelforge-source-check"] = "sentinelforge-source-check"
    verifier_version: Literal["1.0", "1.1", "1.2"] = "1.2"
    python_version: str = Field(default_factory=platform.python_version)
    checked_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    scope: Literal["static_pattern_only"] = "static_pattern_only"
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_retained: Literal[False] = False
    decisions: list[SourceDecision] = Field(min_length=1, max_length=100)
    limitations: list[str] = Field(default_factory=lambda: [
        "Solo corrobora patrones reportados en bytes con el hash original; no busca señales nuevas.",
        "No demuestra alcanzabilidad, inyección de comandos, origen no confiable ni explotabilidad.",
        "No verifica identidad ni declaraciones humanas. Las señales mantienen su estado unverified.",
        "Comparte el parser de Python con el detector; su implementación y proceso son distintos.",
    ])


class SourceReviewReceipt(Contract):
    schema_version: Literal["1.0"] = "1.0"
    analysis_id: str
    submission_id: UUID
    revision: int = Field(ge=2, strict=True)
    review: SourceReview


class _WorkerReview(Contract):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decisions: list[SourceDecision] = Field(min_length=1, max_length=100)


def ensure_original_bytes(report: LocalScanReport, content: bytes) -> None:
    if len(content) > MAX_SOURCE_BYTES:
        raise SourceReviewError("source_too_large")
    if report.source is None or hashlib.sha256(content).hexdigest() != report.source.sha256:
        raise SourceReviewError("source_hash_mismatch")
    if report.status != "COMPLETED" or not report.signals:
        raise SourceReviewError("scan_has_no_signals")


def review_original_source(report: LocalScanReport, content: bytes) -> SourceReview:
    ensure_original_bytes(report, content)
    signals = [signal.model_dump(include={"fingerprint", "call", "line", "column",
                                         "end_line", "end_column"}) for signal in report.signals]
    wire = json.dumps({"source": base64.b64encode(content).decode("ascii"),
                       "sha256": report.source.sha256, "signals": signals}).encode("ascii")
    try:
        process = subprocess.run(
            [sys.executable, "-I", "-S", str(Path(__file__).with_name("_review_worker.py"))],
            input=wire, capture_output=True, check=False, timeout=5,
        )
    except subprocess.TimeoutExpired as error:
        raise SourceReviewError("source_verifier_timeout") from error
    except OSError as error:
        raise SourceReviewError("source_verifier_unavailable") from error
    if process.returncode != 0:
        raise SourceReviewError("source_verifier_failed")
    if len(process.stdout) > 65536:
        raise SourceReviewError("source_verifier_invalid_output")
    try:
        data = json.loads(process.stdout)
        if isinstance(data, dict) and set(data) == {"error"} and data["error"] in {
            "source_verifier_invalid_python", "source_verifier_too_complex", "source_hash_mismatch",
        }:
            raise SourceReviewError(data["error"])
        checked = _WorkerReview.model_validate(data)
        if (checked.source_sha256 != report.source.sha256 or
                [item.signal_fingerprint for item in checked.decisions] !=
                [item.fingerprint for item in report.signals]):
            raise ValueError("review_reference_mismatch")
    except (ValidationError, ValueError, UnicodeError, TypeError, RecursionError) as error:
        if isinstance(error, SourceReviewError):
            raise
        raise SourceReviewError("source_verifier_invalid_output") from error
    return SourceReview(source_sha256=checked.source_sha256, decisions=checked.decisions)
