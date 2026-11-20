from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from sentinelforge.workflow import (
    WORKFLOW_STATES,
    WorkflowAdvanceRequest,
    WorkflowCheckpoint,
    next_checkpoint,
)


def test_workflow_advances_one_stage_and_preserves_its_identity() -> None:
    initial = WorkflowCheckpoint()
    assert str(UUID(initial.analysis_id)) == initial.analysis_id
    checkpoint = initial

    for version, state in enumerate(WORKFLOW_STATES, start=1):
        assert checkpoint.version == version
        assert checkpoint.state == state
        assert checkpoint.analysis_id == initial.analysis_id
        assert checkpoint.created_at == initial.created_at
        assert checkpoint.schema_version == "1.0"
        assert checkpoint.is_demo is True
        assert checkpoint.updated_at.utcoffset() is not None
        assert WorkflowCheckpoint.model_validate_json(checkpoint.model_dump_json()) == checkpoint
        checkpoint = next_checkpoint(checkpoint)

    assert initial.state == "RECEIVED"
    assert initial.version == 1
    assert checkpoint.state == "COMPLETED"
    assert next_checkpoint(checkpoint) == checkpoint


@pytest.mark.parametrize(
    "payload",
    [
        {"state": "DETECTING", "version": 1},
        {"state": "COMPLETED", "version": 7},
        {"state": "UNKNOWN"},
        {"version": True},
        {"version": "1"},
        {"schema_version": "2.0"},
        {"is_demo": False},
        {"created_at": datetime(2026, 11, 20)},
        {"updated_at": datetime(2026, 11, 20)},
        {"unexpected": "ignored?"},
    ],
)
def test_workflow_checkpoint_rejects_invalid_contracts(payload) -> None:
    with pytest.raises(ValidationError):
        WorkflowCheckpoint.model_validate(payload)


@pytest.mark.parametrize("version", [True, False, "1", 0, -1, 1.5])
def test_advance_request_requires_a_positive_integer_version(version) -> None:
    with pytest.raises(ValidationError):
        WorkflowAdvanceRequest(expected_version=version)


def test_advance_request_rejects_extra_fields() -> None:
    assert WorkflowAdvanceRequest(expected_version=1).expected_version == 1
    with pytest.raises(ValidationError):
        WorkflowAdvanceRequest.model_validate({"expected_version": 1, "state": "COMPLETED"})
