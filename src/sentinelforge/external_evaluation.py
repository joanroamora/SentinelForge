"""Untrusted local reference intake, separate from the fixed built-in regression corpora."""

import hashlib
import json
from pathlib import Path

from .evaluation import MAX_CORPUS_BYTES, EvaluationError, evaluate_corpus
from .evaluation_contracts import ExternalEvaluationCorpus, ExternalEvaluationReceipt
from .local_source import LocalSourceError, _load_local_data


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError("external_corpus_duplicate_key")
        result[key] = value
    return result


def _reject_constant(value: str):
    raise EvaluationError("external_corpus_invalid")


def parse_external_corpus(content: bytes) -> ExternalEvaluationCorpus:
    """Validate bounded UTF-8 JSON only; never import, evaluate or execute its sources."""
    if not isinstance(content, bytes):
        raise EvaluationError("external_corpus_invalid")
    if len(content) > MAX_CORPUS_BYTES:
        raise EvaluationError("external_corpus_too_large")
    try:
        data = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
        return ExternalEvaluationCorpus.model_validate(data)
    except EvaluationError:
        raise
    except (ValueError, RecursionError):
        raise EvaluationError("external_corpus_invalid") from None


def evaluate_local_corpus(root: Path, relative_path: str) -> ExternalEvaluationReceipt:
    try:
        label, content = _load_local_data(root, relative_path, suffix=".json",
                                          max_bytes=MAX_CORPUS_BYTES)
    except LocalSourceError as error:
        suffix = error.code.removeprefix("source_")
        raise EvaluationError("external_corpus_" + suffix) from None
    corpus = parse_external_corpus(content)
    result = evaluate_corpus(corpus)
    failures = [case.id for case in result.cases if not case.reference_match]
    acceptance = ("error" if result.status == "PARTIAL" or result.acceptance == "error"
                  else "fail" if failures else "pass")
    return ExternalEvaluationReceipt(
        source_label=label, input_sha256=hashlib.sha256(content).hexdigest(),
        input_size_bytes=len(content), provenance=corpus.provenance,
        acceptance=acceptance, reference_failures=failures, evaluation=result,
    )
