"""Local, read-only measurement of static patterns and command-origin references."""

import hashlib
import json
import math
import platform
import statistics
import time
from collections import Counter
from importlib import resources
from pathlib import Path

from pydantic import __version__ as pydantic_version

from .argument_lineage import LineageError, investigate_argument
from .evaluation_contracts import (
    BuiltinCorpus,
    CaseEvaluation,
    DetectionMetrics,
    EvaluationCase,
    EvaluationCorpus,
    EvaluationReport,
    GroupMetrics,
    LocalizationMetrics,
    TargetEvaluation,
    TraceMetrics,
    observed_reference,
)
from .local_scan import DETECTOR_VERSION, scan_source_bytes
from .source_review import SourceReviewError, review_original_source

MAX_CORPUS_BYTES = 524288
MAX_EVALUATION_SECONDS = 120
BUILTIN_CORPORA = {
    BuiltinCorpus.baseline: ("data/evaluation_v1.json", "sf-py-001-local"),
    BuiltinCorpus.challenge: ("data/evaluation_challenge_v1.json", "sf-py-001-challenge"),
}


class EvaluationError(ValueError):
    """Stable diagnostic; never includes a fixture, a path or raw parser output."""


def _digest(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def load_builtin_corpus(selection: BuiltinCorpus = BuiltinCorpus.baseline) -> EvaluationCorpus:
    try:
        filename, identity = BUILTIN_CORPORA[BuiltinCorpus(selection)]
    except (ValueError, TypeError, KeyError):
        raise EvaluationError("evaluation_unknown_corpus") from None
    try:
        asset = resources.files("sentinelforge").joinpath(filename)
        with asset.open("rb") as handle:
            raw = handle.read(MAX_CORPUS_BYTES + 1)
        if len(raw) > MAX_CORPUS_BYTES:
            raise EvaluationError("evaluation_corpus_too_large")
        corpus = EvaluationCorpus.model_validate_json(raw)
        if corpus.id != identity or corpus.version != "1.0":
            raise EvaluationError("evaluation_corpus_identity_mismatch")
        return corpus
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, EvaluationError):
            raise
        raise EvaluationError("evaluation_corpus_invalid_or_unavailable") from None


def _engine_digest() -> str:
    filenames = (
        "contracts.py", "local_source.py", "local_scan.py", "_scan_worker.py",
        "source_review.py", "_review_worker.py", "argument_lineage.py", "_lineage_worker.py",
        "_lineage_check_worker.py", "evaluation_contracts.py", "evaluation.py",
    )
    try:
        return _digest({name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()
                        .replace(b"\r\n", b"\n")).hexdigest() for name in filenames})
    except OSError:
        raise EvaluationError("evaluation_engine_unavailable") from None


def _remaining(deadline: float) -> None:
    if time.perf_counter() >= deadline:
        raise EvaluationError("evaluation_deadline_exceeded")


def _evaluate_case(case: EvaluationCase, deadline: float) -> CaseEvaluation:
    start = time.perf_counter()
    raw = case.source.encode("utf-8")
    targets = [TargetEvaluation(expected=expected, detected=False) for expected in case.expected_signals]
    status, code, technical = "NOT_RUN", None, False
    observed, signals, review, investigation = [], [], None, None
    try:
        _remaining(deadline)
        scan = scan_source_bytes(case.id + ".py", raw)
        status, signals = scan.status, scan.signals
        observed = [observed_reference(signal) for signal in signals]
        if status == "ERROR":
            code = scan.errors[0].code
            technical = code != case.expected_error
        elif signals:
            _remaining(deadline)
            review = review_original_source(scan, raw)
            if all(decision.result == "pattern_reproduced" for decision in review.decisions):
                _remaining(deadline)
                investigation = investigate_argument(scan, raw, review)
        _remaining(deadline)
    except (EvaluationError, SourceReviewError, LineageError) as error:
        code, technical = str(error), True
    by_key = {reference.key(): signal for reference, signal in zip(observed, signals, strict=True)}
    decisions = {} if review is None else {item.signal_fingerprint: item.result for item in review.decisions}
    traces = {} if investigation is None else {item.hypothesis.signal_fingerprint: item for item in investigation.traces}
    for target in targets:
        signal = by_key.get(target.expected.key())
        if signal is None:
            continue
        target.detected = True
        target.review_result = decisions.get(signal.fingerprint)
        target.observed_trace = traces.get(signal.fingerprint)
        if target.observed_trace is not None:
            hypothesis, verification = target.observed_trace.hypothesis, target.observed_trace.verification
            target.origin_match = hypothesis.origin_kind == target.expected.origin_kind
            target.path_match = hypothesis.steps == target.expected.steps
            expected_steps = ["reproduced"] * len(target.expected.steps)
            if target.expected.verification == "inconclusive":
                expected_steps[0] = "inconclusive"
            target.verification_match = (verification.result == target.expected.verification and
                                         verification.step_results == expected_steps)
    match = (not technical and (
        status == "ERROR" and code == case.expected_error or
        status == "COMPLETED" and case.expected_error is None and
        Counter(item.key() for item in observed) == Counter(item.key() for item in case.expected_signals) and
        all(target.detected and target.review_result == "pattern_reproduced" and target.origin_match and
            target.path_match and target.verification_match for target in targets)))
    return CaseEvaluation(
        id=case.id, scope=case.scope, source_sha256=hashlib.sha256(raw).hexdigest(),
        expected_error=case.expected_error, scan_status=status, error_code=code,
        observed_signals=observed, targets=targets, reference_match=match,
        technical_error=technical, elapsed_ms=(time.perf_counter() - start) * 1000,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def summarize(cases: list[CaseEvaluation]) -> GroupMetrics:
    eligible = [case for case in cases if case.scan_status == "COMPLETED" and case.expected_error is None]
    detection, localization, tracing = DetectionMetrics(), LocalizationMetrics(), TraceMetrics()
    for case in eligible:
        expected, observed = bool(case.targets), bool(case.observed_signals)
        field = ("true_positives" if observed else "false_negatives") if expected else (
            "false_positives" if observed else "true_negatives")
        setattr(detection, field, getattr(detection, field) + 1)
        predicted = Counter(item.key() for item in case.observed_signals)
        reference = Counter(target.expected.key() for target in case.targets)
        localization.matched += sum((predicted & reference).values())
        localization.extra += sum((predicted - reference).values())
        localization.missed += sum((reference - predicted).values())
        for target in case.targets:
            tracing.expected += 1
            if target.observed_trace is not None:
                tracing.traced += 1
                tracing.inconclusive += target.observed_trace.verification.result == "inconclusive"
                tracing.origin_correct += target.origin_match is True
                tracing.path_correct += target.path_match is True
                tracing.jointly_correct += (target.origin_match is True and target.path_match is True and
                                            target.verification_match is True)
    tp, fp, fn = detection.true_positives, detection.false_positives, detection.false_negatives
    detection.precision, detection.recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    detection.f1 = _ratio(2 * tp, 2 * tp + fp + fn)
    localization.precision = _ratio(localization.matched, localization.matched + localization.extra)
    localization.recall = _ratio(localization.matched, localization.matched + localization.missed)
    tracing.coverage = _ratio(tracing.traced, tracing.expected)
    tracing.origin_accuracy_when_traced = _ratio(tracing.origin_correct, tracing.traced)
    tracing.reference_agreement_end_to_end = _ratio(tracing.jointly_correct, tracing.expected)
    tracing.inconclusive_rate_when_traced = _ratio(tracing.inconclusive, tracing.traced)
    return GroupMetrics(cases=len(cases), eligible_detection_cases=len(eligible),
                        technical_errors=sum(case.technical_error for case in cases),
                        detection=detection, localization=localization, tracing=tracing)


def evaluate_corpus(corpus: EvaluationCorpus, *, budget_seconds: float = MAX_EVALUATION_SECONDS) -> EvaluationReport:
    if not math.isfinite(budget_seconds) or not 0 < budget_seconds <= MAX_EVALUATION_SECONDS:
        raise EvaluationError("evaluation_invalid_budget")
    start = time.perf_counter()
    engine_digest = _engine_digest()
    corpus_digest = _digest(corpus.model_dump())
    cases = [_evaluate_case(case, start + budget_seconds) for case in corpus.cases]
    if _engine_digest() != engine_digest or _digest(corpus.model_dump()) != corpus_digest:
        raise EvaluationError("evaluation_inputs_changed")
    failures = [case.id for case in cases if case.scope != "boundary" and not case.reference_match]
    partial = any(case.technical_error for case in cases)
    latencies = sorted(case.elapsed_ms for case in cases if case.scan_status != "NOT_RUN")
    return EvaluationReport(
        corpus_id=corpus.id, corpus_version=corpus.version, corpus_sha256=corpus_digest,
        engine_sha256=engine_digest, detector_version=DETECTOR_VERSION,
        python_version=platform.python_version(), pydantic_version=pydantic_version,
        platform=platform.system(),
        status="PARTIAL" if partial else "COMPLETED",
        acceptance="error" if partial else "fail" if failures else "pass",
        cases=cases, groups={name: summarize(cases if name == "all" else
                         [case for case in cases if case.scope == name])
                             for name in ("all", "in_scope", "boundary", "input_error")},
        reference_failures=failures,
        boundary_gaps=[case.id for case in cases if case.scope == "boundary" and not case.reference_match],
        expected_error_matches=sum(case.expected_error is not None and case.reference_match for case in cases),
        elapsed_ms=(time.perf_counter() - start) * 1000,
        timed_cases=len(latencies),
        case_latency_p50_ms=statistics.median(latencies) if latencies else None,
        case_latency_p95_ms=latencies[math.ceil(len(latencies) * 0.95) - 1] if latencies else None,
    )
