"""Check migration, atomicity and concurrency of persisted investigation traces."""

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from sentinelforge.repository import SQLiteReportRepository
from sentinelforge.service import AnalysisService
from sentinelforge.simulation import FIXTURE_SOURCES, SimulationTrace
from sentinelforge.workflow import WorkflowCheckpoint


def test_schema_two_migration_preserves_legacy_workflow_without_inventing_investigation(
    tmp_path,
) -> None:
    database = tmp_path / "legacy-version-two.sqlite3"
    repository = SQLiteReportRepository(database)
    service = AnalysisService(database)
    original_report = service.create_demo_analysis()
    legacy = WorkflowCheckpoint()
    repository.create_workflow(legacy)
    for version in (1, 2):
        legacy = service.advance_demo_workflow(legacy.analysis_id, expected_version=version)
    assert legacy.state == "INVESTIGATING"
    assert repository.get_simulation(legacy.analysis_id) is None

    # This temporary fixture represents a v2 installation, which had no trace table.
    with sqlite3.connect(database) as connection:
        original_reports = connection.execute("SELECT * FROM report_revisions").fetchall()
        original_events = connection.execute("SELECT * FROM analysis_events").fetchall()
        original_checkpoints = connection.execute("SELECT * FROM workflow_checkpoints").fetchall()
        connection.execute("DROP TABLE monitor_answers")
        connection.execute("DROP TABLE monitor_questions")
        connection.execute("DROP TABLE workflow_simulations")
        connection.execute("PRAGMA user_version = 2")

    restarted = AnalysisService(database)
    assert restarted.get_workflow(legacy.analysis_id) == legacy
    assert restarted.get_report(original_report.analysis.id) == original_report
    assert restarted.get_simulation(legacy.analysis_id) is None
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
        assert connection.execute("SELECT * FROM report_revisions").fetchall() == original_reports
        assert connection.execute("SELECT * FROM analysis_events").fetchall() == original_events
        assert connection.execute("SELECT * FROM workflow_checkpoints").fetchall() == original_checkpoints

    for version in (3, 4, 5):
        completed = restarted.advance_demo_workflow(legacy.analysis_id, expected_version=version)
    assert completed.state == "COMPLETED"
    assert restarted.get_simulation(legacy.analysis_id) is None
    legacy_report = restarted.get_report(legacy.analysis_id)
    assert legacy_report is not None
    assert len(legacy_report.evidence) == 1
    assert legacy_report.evidence[0].source == "sentinelforge://fixtures/demo"
    assert all("Resultado limitado a una fixture" not in item for item in legacy_report.limitations)
    assert restarted.get_report(original_report.analysis.id) == original_report

    new_workflow = restarted.create_demo_workflow()
    trace = restarted.get_simulation(new_workflow.analysis_id)
    assert isinstance(trace, SimulationTrace)
    assert trace.fixture_id == "auth-disabled"
    assert trace.signal is trace.hypothesis is trace.verification is None


def test_failed_trace_insert_rolls_back_checkpoint_and_audit_event(tmp_path) -> None:
    database = tmp_path / "trace-rollback.sqlite3"
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow()
    checkpoint = service.advance_demo_workflow(checkpoint.analysis_id, expected_version=1)
    repository = SQLiteReportRepository(database)
    before_trace = repository.get_simulation(checkpoint.analysis_id)
    before_events = repository.list_events(checkpoint.analysis_id)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_trace BEFORE INSERT ON workflow_simulations
            WHEN NEW.checkpoint_version = 3
            BEGIN SELECT RAISE(ABORT, 'injected_trace_failure'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected_trace_failure"):
        service.advance_demo_workflow(checkpoint.analysis_id, expected_version=2)

    restarted = AnalysisService(database)
    assert restarted.get_workflow(checkpoint.analysis_id) == checkpoint
    assert restarted.get_simulation(checkpoint.analysis_id) == before_trace
    assert repository.list_events(checkpoint.analysis_id) == before_events
    assert restarted.get_report(checkpoint.analysis_id) is None
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT MAX(version) FROM workflow_checkpoints").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM workflow_simulations").fetchone()[0] == 2
        connection.execute("DROP TRIGGER fail_trace")

    recovered = restarted.advance_demo_workflow(checkpoint.analysis_id, expected_version=2)
    assert recovered.state == "INVESTIGATING"
    assert restarted.get_simulation(checkpoint.analysis_id).hypothesis is not None
    assert restarted.advance_demo_workflow(checkpoint.analysis_id, expected_version=2) == recovered
    assert len(repository.list_events(checkpoint.analysis_id)) == 3


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE workflow_simulations SET trace_json = '{}' WHERE analysis_id = ?",
        "DELETE FROM workflow_simulations WHERE analysis_id = ?",
    ],
)
def test_persisted_simulations_reject_mutation(tmp_path, statement: str) -> None:
    database = tmp_path / "immutable-traces.sqlite3"
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow()
    original = service.get_simulation(checkpoint.analysis_id)

    with (
        sqlite3.connect(database) as connection,
        pytest.raises(sqlite3.IntegrityError, match="workflow_simulations_are_immutable"),
    ):
        connection.execute(statement, (checkpoint.analysis_id,))
    assert service.get_simulation(checkpoint.analysis_id) == original


def test_concurrent_verifications_converge_without_duplicate_trace_or_event(tmp_path) -> None:
    database = tmp_path / "concurrent-verification.sqlite3"
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow("auth-enabled")
    for version in (1, 2):
        checkpoint = service.advance_demo_workflow(checkpoint.analysis_id, expected_version=version)
    ready = Barrier(8)

    def verify(_):
        restarted = AnalysisService(database)
        ready.wait(timeout=10)
        advanced = restarted.advance_demo_workflow(checkpoint.analysis_id, expected_version=3)
        return advanced, restarted.get_simulation(checkpoint.analysis_id)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(verify, range(8)))
    assert all(result == results[0] for result in results)
    verified, trace = results[0]
    assert verified.state == "VERIFYING"
    assert verified.version == 4
    assert trace.verification.result == "contradicted_in_fixture"
    assert trace.verification.source_digest == trace.hypothesis.source_digest
    assert trace.verification.source_digest == hashlib.sha256(
        FIXTURE_SOURCES["auth-enabled"].encode("utf-8")
    ).hexdigest()
    repository = SQLiteReportRepository(database)
    assert len(repository.list_events(checkpoint.analysis_id)) == 4
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM workflow_checkpoints WHERE analysis_id = ? AND version = 4",
            (checkpoint.analysis_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            """SELECT COUNT(*) FROM workflow_simulations
            WHERE analysis_id = ? AND checkpoint_version = 4""",
            (checkpoint.analysis_id,),
        ).fetchone()[0] == 1
