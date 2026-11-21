"""Monitor submissions preserve reports and converge safely under retries."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest

from sentinelforge.monitor import MonitorAnswerRequest, MonitorConflictError
from sentinelforge.repository import SQLiteReportRepository
from sentinelforge.service import AnalysisService


def answer_request() -> MonitorAnswerRequest:
    return MonitorAnswerRequest(
        submission_id=uuid4(), text="Contexto humano de una fixture local.",
        actor="demo-author", role="developer",
    )


def completed_monitor(database):
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow(monitored=True)
    for version in range(1, 6):
        checkpoint = service.advance_demo_workflow(
            checkpoint.analysis_id, expected_version=version
        )
    question = service.get_monitor_questions(checkpoint.analysis_id)[0]
    return service, checkpoint, question


def test_concurrent_identical_answers_create_one_receipt_and_one_report_revision(tmp_path) -> None:
    database = tmp_path / "same-submission.sqlite3"
    service, checkpoint, question = completed_monitor(database)
    request = answer_request()
    ready = Barrier(8)

    def submit(_):
        ready.wait(timeout=10)
        return AnalysisService(database).answer_monitor_question(
            checkpoint.analysis_id, question.id, request
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(submit, range(8)))

    assert all(receipt == receipts[0] for receipt in receipts)
    assert receipts[0].report_revision == 2
    latest = service.get_revision(checkpoint.analysis_id)
    assert latest.revision == 2
    assert latest.report.human_statements.count(receipts[0].statement) == 1
    events = SQLiteReportRepository(database).list_events(checkpoint.analysis_id)
    assert sum(event["event_type"] == "monitor_answer_recorded" for event in events) == 1
    assert sum(event["event_type"] == "report_revision_created" for event in events) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM monitor_answers").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM report_revisions").fetchone()[0] == 2


def test_competing_answer_keys_accept_only_one_immutable_declaration(tmp_path) -> None:
    database = tmp_path / "competing-submissions.sqlite3"
    service, checkpoint, question = completed_monitor(database)
    requests = [answer_request(), answer_request()]
    ready = Barrier(2)

    def submit(request):
        ready.wait(timeout=10)
        try:
            return service.answer_monitor_question(checkpoint.analysis_id, question.id, request)
        except MonitorConflictError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, requests))

    conflicts = [result for result in results if isinstance(result, str)]
    accepted = [result for result in results if not isinstance(result, str)]
    assert conflicts == ["monitor_question_already_answered"]
    assert len(accepted) == 1
    answered = service.get_monitor_questions(checkpoint.analysis_id)[0]
    assert answered.answer == accepted[0].statement
    assert service.get_revision(checkpoint.analysis_id).revision == 2
    assert len([
        event for event in SQLiteReportRepository(database).list_events(checkpoint.analysis_id)
        if event["event_type"] == "monitor_answer_recorded"
    ]) == 1


def test_answer_report_and_events_roll_back_together_and_retry_succeeds(tmp_path) -> None:
    database = tmp_path / "rollback.sqlite3"
    service, checkpoint, question = completed_monitor(database)
    repository = SQLiteReportRepository(database)
    original_report = service.get_revision(checkpoint.analysis_id)
    original_trace = service.get_simulation(checkpoint.analysis_id)
    original_events = repository.list_events(checkpoint.analysis_id)
    request = answer_request()
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_monitor_report_event BEFORE INSERT ON analysis_events
            WHEN NEW.event_type = 'report_revision_created'
            BEGIN SELECT RAISE(ABORT, 'injected_monitor_report_failure'); END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected_monitor_report_failure"):
        service.answer_monitor_question(checkpoint.analysis_id, question.id, request)

    restarted = AnalysisService(database)
    assert restarted.get_monitor_questions(checkpoint.analysis_id) == [question]
    assert restarted.get_monitor_questions(checkpoint.analysis_id)[0].status == "pending"
    assert restarted.get_revision(checkpoint.analysis_id) == original_report
    assert restarted.get_simulation(checkpoint.analysis_id) == original_trace
    assert restarted.get_workflow(checkpoint.analysis_id) == checkpoint
    assert repository.list_events(checkpoint.analysis_id) == original_events
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM monitor_answers").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM report_revisions").fetchone()[0] == 1
        connection.execute("DROP TRIGGER fail_monitor_report_event")

    receipt = restarted.answer_monitor_question(checkpoint.analysis_id, question.id, request)
    assert receipt.report_revision == 2
    assert restarted.answer_monitor_question(checkpoint.analysis_id, question.id, request) == receipt
    assert restarted.get_revision(checkpoint.analysis_id).revision == 2
    assert restarted.get_monitor_questions(checkpoint.analysis_id)[0].answer == receipt.statement
    assert restarted.get_simulation(checkpoint.analysis_id) == original_trace


def test_schema_three_migration_preserves_existing_data_and_legacy_mode(tmp_path) -> None:
    database = tmp_path / "migration.sqlite3"
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow()
    for version in (1, 2):
        checkpoint = service.advance_demo_workflow(checkpoint.analysis_id, expected_version=version)
    report = service.create_demo_analysis()
    tables = ("report_revisions", "workflow_checkpoints", "workflow_simulations", "analysis_events")
    with sqlite3.connect(database) as connection:
        original_rows = {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in tables
        }
        # Model the schema from the preceding release in a disposable database.
        connection.execute("DROP TABLE local_scan_investigations")
        connection.execute("DROP TABLE local_scan_verifications")
        connection.execute("DROP TABLE local_scan_submissions")
        connection.execute("DROP TABLE local_scan_revisions")
        connection.execute("DROP TABLE monitor_answers")
        connection.execute("DROP TABLE monitor_questions")
        connection.execute("PRAGMA user_version = 3")

    restarted = AnalysisService(database)
    assert restarted.get_monitor_questions(checkpoint.analysis_id) == []
    assert restarted.get_monitor_questions(report.analysis.id) == []
    assert restarted.get_workflow(checkpoint.analysis_id) == checkpoint
    assert restarted.get_report(report.analysis.id) == report
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        for table in tables:
            assert connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall() == original_rows[table]
        assert connection.execute("SELECT COUNT(*) FROM monitor_questions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM monitor_answers").fetchone()[0] == 0

    monitored = restarted.create_demo_workflow(monitored=True)
    recovered = AnalysisService(database).get_monitor_questions(monitored.analysis_id)
    assert len(recovered) == 1
    assert recovered[0].status == "pending"


@pytest.mark.parametrize(
    ("table", "statement"),
    [
        ("monitor_questions", "UPDATE monitor_questions SET question_json = '{}' WHERE question_id = ?"),
        ("monitor_questions", "DELETE FROM monitor_questions WHERE question_id = ?"),
        ("monitor_answers", "UPDATE monitor_answers SET receipt_json = '{}' WHERE question_id = ?"),
        ("monitor_answers", "DELETE FROM monitor_answers WHERE question_id = ?"),
    ],
)
def test_monitor_records_reject_updates_and_deletes(tmp_path, table, statement) -> None:
    database = tmp_path / "immutable.sqlite3"
    service, checkpoint, question = completed_monitor(database)
    receipt = service.answer_monitor_question(checkpoint.analysis_id, question.id, answer_request())
    before = service.get_revision(checkpoint.analysis_id)
    with (
        sqlite3.connect(database) as connection,
        pytest.raises(sqlite3.IntegrityError, match=f"{table}_are_immutable"),
    ):
        connection.execute(statement, (question.id,))
    assert service.get_monitor_questions(checkpoint.analysis_id)[0].answer == receipt.statement
    assert service.get_revision(checkpoint.analysis_id) == before


def test_question_scope_and_submission_key_cannot_retarget_an_answer(tmp_path) -> None:
    database = tmp_path / "scope.sqlite3"
    service = AnalysisService(database)
    first = service.create_demo_workflow(monitored=True)
    second = service.create_demo_workflow(monitored=True)
    first_question = service.get_monitor_questions(first.analysis_id)[0]
    second_question = service.get_monitor_questions(second.analysis_id)[0]
    request = answer_request()

    with pytest.raises(LookupError, match="monitor_question_not_found"):
        service.answer_monitor_question(second.analysis_id, first_question.id, request)
    assert service.get_monitor_questions(first.analysis_id)[0].status == "pending"
    assert service.get_monitor_questions(second.analysis_id)[0].status == "pending"

    receipt = service.answer_monitor_question(first.analysis_id, first_question.id, request)
    with pytest.raises(MonitorConflictError, match="monitor_submission_conflict"):
        service.answer_monitor_question(second.analysis_id, second_question.id, request)
    assert service.answer_monitor_question(first.analysis_id, first_question.id, request) == receipt
    assert service.get_monitor_questions(second.analysis_id)[0].status == "pending"
    assert not any(
        event["event_type"] == "monitor_answer_recorded"
        for event in SQLiteReportRepository(database).list_events(second.analysis_id)
    )
