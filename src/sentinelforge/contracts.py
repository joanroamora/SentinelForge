"""Versioned Pydantic contracts for the first, explicitly fictitious demo."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Analysis(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["COMPLETED", "PARTIAL"] = "COMPLETED"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    mode: Literal["demo"] = "demo"


class Evidence(Contract):
    id: str
    kind: Literal["demo_fixture"]
    description: str
    source: str
    verification_status: Literal["simulated", "unverified"] = "simulated"


class Finding(Contract):
    id: str
    title: str
    description: str
    severity: Literal["info"] = "info"
    verification_status: Literal["inconclusive"] = "inconclusive"
    evidence_ids: list[str]


class HumanStatement(Contract):
    id: str
    question: str
    text: str
    actor: str
    role: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    verification_status: Literal["unverified"] = "unverified"
    effect: str


class AnalysisReport(Contract):
    schema_version: Literal["1.0"] = "1.0"
    is_demo: Literal[True] = True
    analysis: Analysis
    findings: list[Finding]
    evidence: list[Evidence]
    human_statements: list[HumanStatement]
    limitations: list[str]
