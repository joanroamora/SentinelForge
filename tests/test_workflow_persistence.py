import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from sentinelforge.contracts import Analysis, AnalysisReport
from sentinelforge.repository import SQLiteReportRepository
from sentinelforge.service import AnalysisService
from sentinelforge.workflow import WORKFLOW_STATES


def test_workflow_recovers_a_checkpoint_in_a_new_service(tmp_path) -> None:
    database = tmp_path / "restart.sqlite3"
    initial = AnalysisService(database).create_demo_workflow()
    advanced = AnalysisService(database).advance_demo_workflow(
        initial.analysis_id, expected_version=1
    )

    recovered = AnalysisService(database).get_workflow(initial.analysis_id)

    assert recovered == advanced
    assert recovered.version == 2
    assert recovered.state == "DETECTING"
    assert AnalysisService(database).get_report(initial.analysis_id) is None


def test_concurrent_retries_store_one_advance_and_one_event(tmp_path) -> None:
    database = tmp_path / "concurrent.sqlite3"
    initial = AnalysisService(database).create_demo_workflow()
    ready = Barrier(8)

    def advance(_):
        ready.wait(timeout=10)
        return AnalysisService(database).advance_demo_workflow(
            initial.analysis_id, expected_version=1
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(advance, range(8)))

    assert all(result == results[0] for result in results)
    assert results[0].version == 2
    assert AnalysisService(database).get_workflow(initial.analysis_id) == results[0]
    events = SQLiteReportRepository(database).list_events(initial.analysis_id)
    assert [event["event_type"] for event in events] == ["workflow_created", "workflow_advanced"]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM workflow_checkpoints").fetchone()[0] == 2


def test_terminal_workflow_and_historical_replays_do_not_duplicate_data(tmp_path) -> None:
    database = tmp_path / "terminal.sqlite3"
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow()
    history = [checkpoint]
    while checkpoint.state != "COMPLETED":
        checkpoint = AnalysisService(database).advance_demo_workflow(
            checkpoint.analysis_id, expected_version=checkpoint.version
        )
        history.append(checkpoint)

    for expected_version in range(1, 6):
        replay = service.advance_demo_workflow(
            checkpoint.analysis_id, expected_version=expected_version
        )
        assert replay == history[expected_version]
    assert service.advance_demo_workflow(checkpoint.analysis_id, expected_version=6) == checkpoint
    assert service.get_workflow(checkpoint.analysis_id) == checkpoint
    report = service.get_report(checkpoint.analysis_id)
    assert report.analysis.id == checkpoint.analysis_id
    assert report.analysis.created_at == checkpoint.created_at
    assert report.human_statements[0].verification_status == "unverified"
    events = SQLiteReportRepository(database).list_events(checkpoint.analysis_id)
    workflow_events = [event for event in events if event["event_type"].startswith("workflow_")]
    assert len(events) == 7
    assert [json.loads(event["payload_json"])["version"] for event in workflow_events] == list(
        range(1, 7)
    )
    assert [json.loads(event["payload_json"])["state"] for event in workflow_events] == list(
        WORKFLOW_STATES
    )
    assert sum(event["event_type"] == "report_created" for event in events) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM report_revisions").fetchone()[0] == 1


def test_final_checkpoint_report_and_events_roll_back_together(tmp_path) -> None:
    database = tmp_path / "rollback.sqlite3"
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow()
    while checkpoint.state != "REPORTING":
        checkpoint = service.advance_demo_workflow(
            checkpoint.analysis_id, expected_version=checkpoint.version
        )
    repository = SQLiteReportRepository(database)
    before_events = repository.list_events(checkpoint.analysis_id)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_report_event BEFORE INSERT ON analysis_events
            WHEN NEW.event_type = 'report_created'
            BEGIN SELECT RAISE(ABORT, 'injected_report_event_failure'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected_report_event_failure"):
        service.advance_demo_workflow(checkpoint.analysis_id, expected_version=5)

    restarted = AnalysisService(database)
    assert restarted.get_workflow(checkpoint.analysis_id) == checkpoint
    assert restarted.get_report(checkpoint.analysis_id) is None
    assert repository.list_events(checkpoint.analysis_id) == before_events
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT MAX(version) FROM workflow_checkpoints").fetchone()[0] == 5
        connection.execute("DROP TRIGGER fail_report_event")

    completed = restarted.advance_demo_workflow(checkpoint.analysis_id, expected_version=5)
    assert completed.state == "COMPLETED"
    assert restarted.get_report(checkpoint.analysis_id) is not None
    assert len(repository.list_events(checkpoint.analysis_id)) == 7


def test_schema_v1_migration_preserves_existing_report_and_audit_event(tmp_path) -> None:
    database = tmp_path / "version-one.sqlite3"
    old_report = AnalysisReport(
        analysis=Analysis(), findings=[], evidence=[], human_statements=[],
        limitations=["Expediente de una instalación local anterior."],
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE report_revisions (
                analysis_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0),
                report_json TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY (analysis_id, revision)
            );
            CREATE TABLE analysis_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
                analysis_id TEXT NOT NULL, event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TRIGGER report_revisions_no_update BEFORE UPDATE ON report_revisions
                BEGIN SELECT RAISE(ABORT, 'report_revisions_are_immutable'); END;
            CREATE TRIGGER report_revisions_no_delete BEFORE DELETE ON report_revisions
                BEGIN SELECT RAISE(ABORT, 'report_revisions_are_immutable'); END;
            CREATE TRIGGER analysis_events_no_update BEFORE UPDATE ON analysis_events
                BEGIN SELECT RAISE(ABORT, 'analysis_events_are_append_only'); END;
            CREATE TRIGGER analysis_events_no_delete BEFORE DELETE ON analysis_events
                BEGIN SELECT RAISE(ABORT, 'analysis_events_are_append_only'); END;
            PRAGMA user_version = 1;
            """
        )
        connection.execute(
            "INSERT INTO report_revisions VALUES (?, 1, ?, ?)",
            (old_report.analysis.id, old_report.model_dump_json(), old_report.analysis.created_at.isoformat()),
        )
        connection.execute(
            """INSERT INTO analysis_events
            (event_id, analysis_id, event_type, occurred_at, payload_json)
            VALUES ('existing-event', ?, 'report_created', ?, '{"revision":1}')""",
            (old_report.analysis.id, old_report.analysis.created_at.isoformat()),
        )

    service = AnalysisService(database)
    assert service.get_report(old_report.analysis.id) == old_report
    checkpoint = service.create_demo_workflow()
    assert AnalysisService(database).get_workflow(checkpoint.analysis_id) == checkpoint
    events = SQLiteReportRepository(database).list_events(old_report.analysis.id)
    assert len(events) == 1
    assert events[0]["event_id"] == "existing-event"
    assert events[0]["payload_json"] == '{"revision":1}'
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute("SELECT COUNT(*) FROM report_revisions").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="report_revisions_are_immutable"):
            connection.execute("UPDATE report_revisions SET report_json = '{}'")


def test_unknown_future_schema_is_rejected_without_changing_database(tmp_path) -> None:
    database = tmp_path / "future.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE future_data (value TEXT NOT NULL)")
        connection.execute("INSERT INTO future_data VALUES ('preserve-me')")
        connection.execute("PRAGMA user_version = 99")
    before_bytes = database.read_bytes()

    with pytest.raises(RuntimeError, match="unsupported_database_schema_version:99"):
        AnalysisService(database).get_workflow("missing")

    assert database.read_bytes() == before_bytes


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE workflow_checkpoints SET checkpoint_json = '{}' WHERE analysis_id = ?",
        "DELETE FROM workflow_checkpoints WHERE analysis_id = ?",
    ],
)
def test_persisted_checkpoints_reject_updates_and_deletes(tmp_path, statement: str) -> None:
    database = tmp_path / "immutable.sqlite3"
    checkpoint = AnalysisService(database).create_demo_workflow()

    with (
        sqlite3.connect(database) as connection,
        pytest.raises(sqlite3.IntegrityError, match="workflow_checkpoints_are_immutable"),
    ):
        connection.execute(statement, (checkpoint.analysis_id,))

    assert AnalysisService(database).get_workflow(checkpoint.analysis_id) == checkpoint
