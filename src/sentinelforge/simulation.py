"""Deterministic demo roles that keep signal, hypothesis and source checks separate."""

import hashlib
import json
from types import MappingProxyType
from typing import Literal, Self

from pydantic import Field, model_validator

from .contracts import AnalysisReport, Contract, Evidence
from .demo_fixture import FINDING_ID

DemoFixtureId = Literal["auth-disabled", "auth-enabled", "source-missing"]
VerificationResult = Literal["supported_in_fixture", "contradicted_in_fixture", "inconclusive"]
FIXTURE_SOURCES = MappingProxyType({
    "auth-disabled": '{"route":"/demo","auth_required":false}',
    "auth-enabled": '{"route":"/demo","auth_required":true}',
})


class SimulationStartRequest(Contract):
    fixture_id: DemoFixtureId = "auth-disabled"
    monitored: bool = Field(default=False, strict=True)


class MockSignal(Contract):
    id: str
    role: Literal["mock_detector"] = "mock_detector"
    rule_id: Literal["mock_authentication_disabled"] = "mock_authentication_disabled"
    source_id: DemoFixtureId
    source_uri: str
    claim: Literal["authentication_disabled"] = "authentication_disabled"


class MockHypothesis(Contract):
    id: str
    role: Literal["mock_investigator"] = "mock_investigator"
    signal_id: str
    source_id: DemoFixtureId
    source_uri: str
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    claim: Literal["authentication_disabled"] = "authentication_disabled"
    rationale: str


class MockVerification(Contract):
    id: str
    role: Literal["independent_fixture_verifier"] = "independent_fixture_verifier"
    hypothesis_id: str
    source_id: DemoFixtureId
    source_uri: str
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    original_source: str | None = None
    result: VerificationResult
    reason: str


class SimulationTrace(Contract):
    schema_version: Literal["1.0"] = "1.0"
    is_demo: Literal[True] = True
    fixture_id: DemoFixtureId = "auth-disabled"
    signal: MockSignal | None = None
    hypothesis: MockHypothesis | None = None
    verification: MockVerification | None = None

    @model_validator(mode="after")
    def components_have_predecessors(self) -> Self:
        if self.hypothesis is not None and self.signal is None:
            raise ValueError("simulation_signal_required")
        if self.verification is not None and self.hypothesis is None:
            raise ValueError("simulation_hypothesis_required")
        return self


def _uri(fixture_id: str) -> str:
    return f"sentinelforge://fixtures/{fixture_id}"


def _digest(source: str | None) -> str | None:
    return None if source is None else hashlib.sha256(source.encode("utf-8")).hexdigest()


def detect_signal(fixture_id: DemoFixtureId) -> MockSignal:
    """Emit an intentionally suspicious signal, including for the safe fixture."""
    return MockSignal(
        id=f"signal-{fixture_id}", source_id=fixture_id, source_uri=_uri(fixture_id)
    )


def investigate_signal(signal: MockSignal) -> MockHypothesis:
    return MockHypothesis(
        id=f"hypothesis-{signal.source_id}", signal_id=signal.id,
        source_id=signal.source_id, source_uri=signal.source_uri,
        source_digest=_digest(FIXTURE_SOURCES.get(signal.source_id)),
        rationale="Hipótesis de demostración derivada de una señal ficticia, pendiente de verificar.",
    )


def verify_hypothesis(
    fixture_id: DemoFixtureId, signal: MockSignal, hypothesis: MockHypothesis
) -> MockVerification:
    """Re-read original fixture data rather than trusting the investigator's prose."""
    original = FIXTURE_SOURCES.get(fixture_id)
    digest = _digest(original)
    linked = (
        signal.id == f"signal-{fixture_id}"
        and signal.source_id == hypothesis.source_id == fixture_id
        and signal.source_uri == hypothesis.source_uri == _uri(fixture_id)
        and hypothesis.id == f"hypothesis-{fixture_id}"
        and hypothesis.signal_id == signal.id
        and signal.claim == hypothesis.claim == "authentication_disabled"
    )
    result: VerificationResult = "inconclusive"
    if not linked:
        reason = "Las referencias de señal, hipótesis o fuente no coinciden con la fixture original."
    elif original is None:
        reason = "Falta la fuente original; la hipótesis permanece sin respaldo."
    elif hypothesis.source_digest != digest:
        reason = "El hash citado no coincide con la fuente original."
    else:
        try:
            data = json.loads(original)
            auth_required = data.get("auth_required") if isinstance(data, dict) else None
        except (json.JSONDecodeError, TypeError):
            auth_required = None
        if type(auth_required) is not bool:
            reason = "La fuente original no contiene un booleano auth_required válido."
        elif auth_required:
            result = "contradicted_in_fixture"
            reason = "La fixture exige autenticación y contradice la señal ficticia."
        else:
            result = "supported_in_fixture"
            reason = "La fixture declara auth_required=false; solo respalda este caso simulado."
    return MockVerification(
        id=f"verification-{fixture_id}", hypothesis_id=hypothesis.id,
        source_id=fixture_id, source_uri=_uri(fixture_id), source_digest=digest,
        original_source=original, result=result, reason=reason,
    )


def advance_simulation(trace: SimulationTrace, state: str) -> SimulationTrace:
    """Produce one role's result on entering its corresponding demo phase."""
    values = trace.model_dump()
    if state == "DETECTING" and trace.signal is None and trace.hypothesis is None:
        values["signal"] = detect_signal(trace.fixture_id).model_dump()
    elif state == "INVESTIGATING" and trace.signal is not None and trace.hypothesis is None:
        values["hypothesis"] = investigate_signal(trace.signal).model_dump()
    elif state == "VERIFYING" and trace.signal is not None and trace.hypothesis is not None:
        if trace.verification is not None:
            raise ValueError("simulation_stage_out_of_order")
        values["verification"] = verify_hypothesis(
            trace.fixture_id, trace.signal, trace.hypothesis
        ).model_dump()
    elif state in ("REPORTING", "COMPLETED") and trace.verification is not None:
        pass
    else:
        raise ValueError("simulation_stage_out_of_order")
    return SimulationTrace.model_validate(values)


def enrich_demo_report(report: AnalysisReport, trace: SimulationTrace) -> AnalysisReport:
    """Attach qualified fixture evidence while preserving human declarations."""
    if trace.signal is None or trace.hypothesis is None or trace.verification is None:
        raise ValueError("simulation_verification_required")
    checked = verify_hypothesis(trace.fixture_id, trace.signal, trace.hypothesis)
    if checked != trace.verification:
        raise ValueError("simulation_verification_mismatch")
    enriched = AnalysisReport.model_validate(report.model_dump())
    evidence = Evidence(
        id=f"evidence-simulation-{trace.fixture_id}", kind="demo_fixture",
        source=checked.source_uri,
        description=(
            f"Verificación simulada: {checked.result}. {checked.reason} "
            f"SHA-256: {checked.source_digest or 'ausente'}. "
            f"Fuente original: {checked.original_source or 'no disponible'}."
        ),
    )
    existing = next((item for item in enriched.evidence if item.id == evidence.id), None)
    if existing is not None and existing != evidence:
        raise ValueError("simulation_evidence_id_conflict")
    if existing is None:
        enriched.evidence.append(evidence)
    for finding in enriched.findings:
        if finding.id == FINDING_ID and evidence.id not in finding.evidence_ids:
            finding.evidence_ids.append(evidence.id)
    limitation = (
        f"Resultado limitado a una fixture: {checked.result}. "
        "No confirma vulnerabilidades reales ni verifica declaraciones humanas."
    )
    if limitation not in enriched.limitations:
        enriched.limitations.append(limitation)
    return enriched
