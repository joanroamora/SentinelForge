import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge.api import create_app
from sentinelforge.cli import app
from sentinelforge.monitor import MonitorAnswerRequest, MonitorConflictError
from sentinelforge.repository import SQLiteReportRepository
from sentinelforge.service import AnalysisService

SOURCE = b"import subprocess\nsubprocess.run('EXAMPLE_NOT_A_SECRET', shell=True, check=False)\n"


def answer(**changes):
    return MonitorAnswerRequest(submission_id=uuid4(), actor="example-author", role="developer",
                                text="Contexto de ejemplo: <b>texto literal</b>.", **changes)


def test_real_case_restarts_retries_preserves_original_and_never_stores_source(tmp_path):
    database = tmp_path / "scans.sqlite3"
    service = AnalysisService(database)
    first = service.create_source_scan("example.py", SOURCE)
    assert first.status == "PARTIAL" and first.report.status == "COMPLETED"
    assert first.is_demo is False and first.question.status == "pending"
    assert service.create_source_scan("example.py", SOURCE) == first
    request = answer()
    receipt = service.answer_local_scan(first.id, request)
    restarted = AnalysisService(database)
    assert restarted.answer_local_scan(first.id, request) == receipt
    latest = restarted.get_local_scan(first.id)
    assert latest.revision == 2 and latest.status == "PARTIAL"
    assert latest.report == first.report
    assert latest.human_statements == [receipt.statement]
    assert latest.human_statements[0].verification_status == "unverified"
    assert restarted.get_local_scan(first.id, 1) == first
    assert restarted.create_source_scan("example.py", SOURCE) == latest
    assert restarted.list_local_scans() == [latest]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_scan_revisions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM report_revisions").fetchone()[0] == 0
        assert "EXAMPLE_NOT_A_SECRET" not in "".join(connection.iterdump())
        for table in ("local_scan_revisions", "local_scan_submissions"):
            for operation in (f"UPDATE {table} SET analysis_id = 'other'", f"DELETE FROM {table}"):
                with pytest.raises(sqlite3.IntegrityError, match="are_immutable"):
                    connection.execute(operation)


def test_concurrent_scan_and_answer_converge_without_extra_revisions(tmp_path):
    service = AnalysisService(tmp_path / "concurrent.sqlite3")
    ready = Barrier(6)

    def create(_):
        ready.wait(timeout=10)
        return service.create_source_scan("case.py", SOURCE)

    with ThreadPoolExecutor(max_workers=6) as pool:
        cases = list(pool.map(create, range(6)))
    assert all(item == cases[0] for item in cases)
    request = answer()
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipts = list(pool.map(lambda _: service.answer_local_scan(cases[0].id, request), range(6)))
    assert all(item == receipts[0] for item in receipts)
    assert service.get_local_scan(cases[0].id).revision == 2
    with pytest.raises(MonitorConflictError, match="already_answered"):
        service.answer_local_scan(cases[0].id, answer())
    altered = request.model_copy(update={"text": "Changed context"})
    with pytest.raises(MonitorConflictError, match="submission_conflict"):
        service.answer_local_scan(cases[0].id, altered)


def test_answer_failure_rolls_back_context_revision_and_events(tmp_path):
    database = tmp_path / "rollback.sqlite3"
    service = AnalysisService(database)
    original = service.create_source_scan("example.py", SOURCE)
    before = SQLiteReportRepository(database).list_events(original.id)
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TRIGGER fail_context BEFORE INSERT ON local_scan_submissions
                              BEGIN SELECT RAISE(ABORT, 'test_failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="test_failure"):
        service.answer_local_scan(original.id, answer())
    assert service.get_local_scan(original.id) == original
    assert SQLiteReportRepository(database).list_events(original.id) == before


def test_migration_four_preserves_demo_monitor_and_all_previous_rows(tmp_path):
    database = tmp_path / "migration.sqlite3"
    service = AnalysisService(database)
    report = service.create_demo_analysis()
    workflow = service.create_demo_workflow(monitored=True)
    questions = service.get_monitor_questions(workflow.analysis_id)
    with sqlite3.connect(database) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if not row[0].startswith(("local_scan_", "sqlite_"))]
        before = {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
        connection.execute("DROP TABLE local_scan_verifications")
        connection.execute("DROP TABLE local_scan_submissions")
        connection.execute("DROP TABLE local_scan_revisions")
        connection.execute("PRAGMA user_version = 4")
    restarted = AnalysisService(database)
    assert restarted.get_report(report.analysis.id) == report
    assert restarted.get_monitor_questions(workflow.analysis_id) == questions
    assert restarted.list_local_scans() == []
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables} == before


def test_http_upload_history_context_and_limits_share_the_service(tmp_path):
    database = tmp_path / "api.sqlite3"

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=create_app(database_path=database)),
                               base_url="http://test") as client:
            endpoint = "/v1/local-scans?filename=example.py"
            headers = {"Content-Type": "application/octet-stream"}
            created = await client.post(endpoint, content=SOURCE, headers=headers)
            assert created.status_code == 200
            case = created.json()
            base = "/v1/local-scans/" + case["id"]
            assert (await client.post(endpoint, content=SOURCE, headers=headers)).json() == case
            assert (await client.get("/v1/local-scans")).json() == [case]
            assert (await client.get(base)).json() == case
            request = answer().model_dump(mode="json")
            receipt = (await client.post(base + "/answers", json=request)).json()
            assert receipt["revision"] == 2
            assert (await client.post(base + "/answers", json=request)).json() == receipt
            assert (await client.get(base + "?revision=1")).json() == case
            assert (await client.get(base)).json()["status"] == "PARTIAL"
            assert (await client.post(base + "/answers", json=answer().model_dump(mode="json"))).status_code == 409
            assert (await client.post(endpoint, content=b"x" * 65537, headers=headers)).status_code == 413
            assert (await client.post(endpoint, content=SOURCE, headers=headers | {"Origin": "https://untrusted.invalid"})).status_code == 403
            assert (await client.post(endpoint, json={"path": "host.py"})).status_code == 415
            assert (await client.post("/v1/local-scans?filename=../bad.py", content=SOURCE, headers=headers)).status_code == 422
            assert (await client.get("/v1/local-scans/missing")).status_code == 404
            assert (await client.get("/v1/local-scans?limit=101")).status_code == 422
            invalid = await client.post(endpoint, content=b"def bad(\n", headers=headers)
            assert invalid.status_code == 200 and invalid.json()["status"] == "ERROR"
            assert len((await client.get("/v1/local-scans?limit=1&offset=1")).json()) == 1
            for asset in ("app.css", "app.js", "demo.js"):
                assert (await client.get("/assets/" + asset)).status_code == 200
    asyncio.run(exercise())


def test_cli_json_pretty_and_recovered_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(tmp_path / "cli.sqlite3"))
    monkeypatch.setenv("NO_COLOR", "1")
    (tmp_path / "sample.py").write_bytes(SOURCE)
    runner = CliRunner()
    created = runner.invoke(app, ["scan", "sample.py", "--format", "json"])
    assert created.exit_code == 0, created.output
    case = json.loads(created.stdout)
    shown = runner.invoke(app, ["scan-report", case["id"], "--format", "pretty"])
    assert shown.exit_code == 0, shown.output
    assert "SENTINELFORGE" in shown.stdout and "SF-PY-001" in shown.stdout
    assert "\x1b" not in shown.stdout and "EXAMPLE_NOT_A_SECRET" not in shown.stdout
    listed = runner.invoke(app, ["scans", "--format", "json"])
    assert json.loads(listed.stdout) == [case]
    assert json.loads(runner.invoke(app, ["scan-report", case["id"]]).stdout) == case


def test_submission_cannot_target_another_case_and_negative_case_has_no_question(tmp_path):
    service = AnalysisService(tmp_path / "scope.sqlite3")
    first = service.create_source_scan("first.py", SOURCE)
    second = service.create_source_scan("second.py", SOURCE)
    request = answer()
    service.answer_local_scan(first.id, request)
    with pytest.raises(MonitorConflictError, match="submission_conflict"):
        service.answer_local_scan(second.id, request)
    assert service.get_local_scan(second.id).question.status == "pending"
    negative = service.create_source_scan("negative.py", b"pass\n")
    assert negative.status == "COMPLETED" and negative.question is None
    with pytest.raises(LookupError, match="question_not_found"):
        service.answer_local_scan(negative.id, answer())


def test_terminal_keeps_untrusted_markup_and_control_characters_inert(tmp_path, monkeypatch):
    from sentinelforge.terminal import OutputFormat, emit

    monkeypatch.setenv("NO_COLOR", "1")
    service = AnalysisService(tmp_path / "terminal.sqlite3")
    case = service.create_source_scan("example.py", SOURCE)
    request = MonitorAnswerRequest(submission_id=uuid4(), actor="[red]Author[/red]", role="tester",
                                   text="\x1b]0;CHANGE_TITLE\x07 <script>literal</script>")
    service.answer_local_scan(case.id, request)
    latest = service.get_local_scan(case.id)
    assert latest.human_statements[0].text == request.text
    import io
    from contextlib import redirect_stdout

    captured = io.StringIO()
    with redirect_stdout(captured):
        emit(latest, OutputFormat.pretty)
    assert "\x1b" not in captured.getvalue() and "\x07" not in captured.getvalue()
    assert "[red]Author[/red]" in captured.getvalue()
    assert "<script>literal</script>" in captured.getvalue()


def test_pretty_cli_works_in_a_legacy_cp1252_pipe_with_large_and_unicode_inputs(tmp_path):
    import os
    import subprocess
    import sys

    filename = "case_日本.py"
    (tmp_path / filename).write_bytes(SOURCE + b"#" + b"x" * 40000)
    environment = os.environ.copy()
    environment.update(PYTHONIOENCODING="cp1252", NO_COLOR="1")
    result = subprocess.run([sys.executable, "-m", "sentinelforge.cli", "scan-file", filename,
                             "--format", "pretty"], cwd=tmp_path, env=environment,
                            capture_output=True, check=False, timeout=20)
    assert result.returncode == 0, result.stderr.decode("cp1252", errors="replace")
    assert result.stderr == b"" and b"\x1b" not in result.stdout
    assert b"SF-PY-001" in result.stdout and b"SENTINELFORGE" in result.stdout
