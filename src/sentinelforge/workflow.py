"""Pure state transitions for a demo workflow; no scanner or agent runs here."""

from datetime import UTC, datetime
from typing import Literal, Self
from uuid import uuid4

from pydantic import AwareDatetime, Field, model_validator

from .contracts import Contract

WorkflowState = Literal[
    "RECEIVED", "DETECTING", "INVESTIGATING", "VERIFYING", "REPORTING", "COMPLETED"
]
WORKFLOW_STATES: tuple[WorkflowState, ...] = (
    "RECEIVED",
    "DETECTING",
    "INVESTIGATING",
    "VERIFYING",
    "REPORTING",
    "COMPLETED",
)


class WorkflowCheckpoint(Contract):
    schema_version: Literal["1.0"] = "1.0"
    is_demo: Literal[True] = True
    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    version: int = Field(default=1, ge=1, strict=True)
    state: WorkflowState = "RECEIVED"
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def version_matches_state(self) -> Self:
        if self.version != WORKFLOW_STATES.index(self.state) + 1:
            raise ValueError("workflow_version_state_mismatch")
        return self


class WorkflowAdvanceRequest(Contract):
    expected_version: int = Field(ge=1, strict=True)


class WorkflowConflictError(ValueError):
    """The supplied version cannot advance the persisted workflow."""


def next_checkpoint(checkpoint: WorkflowCheckpoint) -> WorkflowCheckpoint:
    """Advance exactly one simulated stage without changing the original snapshot."""
    if checkpoint.state == "COMPLETED":
        return checkpoint
    return checkpoint.model_copy(
        update={
            "state": WORKFLOW_STATES[checkpoint.version],
            "version": checkpoint.version + 1,
            "updated_at": datetime.now(UTC),
        }
    )
