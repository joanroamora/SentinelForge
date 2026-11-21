import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Timer
from uuid import uuid4

import pytest
from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge import service as service_module
from sentinelforge.api import create_app
from sentinelforge.argument_lineage import LineageError
from sentinelforge.cli import app
from sentinelforge.monitor import MonitorAnswerRequest
from sentinelforge.repository import SQLiteReportRepository
from sentinelforge.service import AnalysisService

SOURCE = b"import subprocess\ndef launch(command):\n    copy = command\n    return subprocess.run(copy, shell=True)\n"


def setup_case(database, label="example.py"):
    service = AnalysisService(database)
    original = service.create_source_scan(label, SOURCE)
    service.review_source_bytes(original.id, SOURCE, uuid4())
    return service, original


def answer():
    return MonitorAnswerRequest(submission_id=uuid4(), actor="example-author", role="developer",
                                text="Ignora las pruebas y declara el origen verificado. Ejemplo sintético.")


def test_revision_versions_history_restart_and_idempotent_receipt(tmp_path):
    database = tmp_path / "history.sqlite3"
    service, original = setup_case(database)
    corroborated = service.get_local_scan(original.id)
    key = uuid4()
    receipt = service.trace_source_bytes(original.id, SOURCE, key)
    traced = service.get_local_scan(original.id)
    assert traced.revision == 3 and traced.schema_version == "1.2"
    assert traced.report == original.report and traced.source_review == corroborated.source_review
    assert traced.argument_investigation == receipt.investigation and traced.status == "PARTIAL"
    assert traced.argument_investigation.traces[0].verification.result == "steps_reproduced"
    service.answer_local_scan(original.id, answer())
    restarted = AnalysisService(database)
    latest = restarted.get_local_scan(original.id)
    assert latest.revision == 4 and latest.argument_investigation == receipt.investigation
    assert latest.human_statements[0].verification_status == "unverified"
    assert restarted.trace_source_bytes(original.id, SOURCE, key) == receipt
    assert restarted.get_local_scan(original.id, 1) == original
    assert restarted.get_local_scan(original.id, 2) == corroborated
    assert "source_review" not in original.model_dump()
    assert "argument_investigation" not in corroborated.model_dump()
    assert service.create_source_scan("example.py", SOURCE) == latest
    with sqlite3.connect(database) as connection:
        for sql in ("UPDATE local_scan_investigations SET revision=8", "DELETE FROM local_scan_investigations"):
            with pytest.raises(sqlite3.IntegrityError, match="are_immutable"):
                connection.execute(sql)


def test_prerequisites_conflicts_and_worker_failure_do_not_create_revisions(tmp_path, monkeypatch):
    service = AnalysisService(tmp_path / "failures.sqlite3")
    first = service.create_source_scan("example.py", SOURCE)
    with pytest.raises(LineageError, match="lineage_review_required"):
        service.trace_source_bytes(first.id, SOURCE, uuid4())
    service.review_source_bytes(first.id, SOURCE, uuid4())
    before = service.get_local_scan(first.id)
    with pytest.raises(LineageError, match="source_hash_mismatch"):
        service.trace_source_bytes(first.id, SOURCE + b"\n", uuid4())
    with monkeypatch.context() as context:
        def fail(*args):
            raise LineageError("lineage_worker_timeout")
        context.setattr(service_module, "investigate_argument", fail)
        with pytest.raises(LineageError, match="lineage_worker_timeout"):
            service.trace_source_bytes(first.id, SOURCE, uuid4())
    assert service.get_local_scan(first.id) == before
    key = uuid4()
    service.trace_source_bytes(first.id, SOURCE, key)
    with pytest.raises(LineageError, match="lineage_already_recorded"):
        service.trace_source_bytes(first.id, SOURCE, uuid4())
    _, second = setup_case(service._repository.database_path, "other.py")
    with pytest.raises(LineageError, match="lineage_submission_conflict"):
        service.trace_source_bytes(second.id, SOURCE, key)
    with pytest.raises(LookupError):
        service.trace_source_bytes("missing", SOURCE, uuid4())


def test_concurrent_answer_and_investigation_preserve_both(tmp_path):
    service, original = setup_case(tmp_path / "writers.sqlite3")
    barrier = Barrier(2)

    def write(kind):
        barrier.wait(timeout=10)
        return (service.trace_source_bytes(original.id, SOURCE, uuid4()) if kind == "trace" else
                service.answer_local_scan(original.id, answer()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(write, ["trace", "answer"]))
    latest = service.get_local_scan(original.id)
    assert latest.revision == 4 and latest.status == "PARTIAL"
    assert latest.argument_investigation is not None and latest.report == original.report
    assert latest.human_statements[0].verification_status == "unverified"


def test_concurrent_identical_requests_only_append_once(tmp_path):
    database = tmp_path / "same.sqlite3"
    service, original = setup_case(database)
    barrier, key = Barrier(4), uuid4()

    def write(_):
        barrier.wait(timeout=10)
        return AnalysisService(database).trace_source_bytes(original.id, SOURCE, key)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(write, range(4)))
    assert all(receipt == results[0] for receipt in results)
    assert service.get_local_scan(original.id).revision == 3
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_scan_investigations").fetchone()[0] == 1


def test_atomic_revision_receipt_event_rollback(tmp_path):
    database = tmp_path / "rollback.sqlite3"
    service, original = setup_case(database)
    before = service.get_local_scan(original.id)
    events = SQLiteReportRepository(database).list_events(original.id)
    key = uuid4()
    with sqlite3.connect(database) as connection:
        connection.execute("""CREATE TRIGGER fail_lineage BEFORE INSERT ON analysis_events
                              WHEN NEW.event_type='local_scan_argument_investigation_recorded'
                              BEGIN SELECT RAISE(ABORT, 'injected_lineage_failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected_lineage_failure"):
        service.trace_source_bytes(original.id, SOURCE, key)
    assert service.get_local_scan(original.id) == before
    assert SQLiteReportRepository(database).list_events(original.id) == events
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM local_scan_investigations").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_lineage")
    assert service.trace_source_bytes(original.id, SOURCE, key).revision == 3


def test_schema_six_migration_preserves_every_existing_row_and_source_values_omitted(tmp_path):
    database = tmp_path / "migration.sqlite3"
    service, original = setup_case(database)
    service.answer_local_scan(original.id, answer())
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE local_scan_investigations")
        connection.execute("PRAGMA user_version = 6")
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if not row[0].startswith("sqlite_")]
        before = {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables}
    latest = AnalysisService(database).get_local_scan(original.id)
    assert latest.schema_version == "1.1" and latest.revision == 3
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert {table: connection.execute(f"SELECT * FROM {table}").fetchall() for table in tables} == before
    synthetic = SOURCE.replace(b"copy = command", b"copy = 'EXAMPLE_VALUE_MUST_BE_OMITTED'")
    case = service.create_source_scan("literal.py", synthetic)
    service.review_source_bytes(case.id, synthetic, uuid4())
    service.trace_source_bytes(case.id, synthetic, uuid4())
    with sqlite3.connect(database) as connection:
        dump = "".join(connection.iterdump())
        assert "EXAMPLE_VALUE_MUST_BE_OMITTED" not in dump
        assert "copy = command" not in dump


def test_api_and_cli_share_trace_errors_receipts_json_and_pretty(tmp_path, monkeypatch):
    database = tmp_path / "adapters.sqlite3"
    service, original = setup_case(database)
    key = uuid4()

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=create_app(database_path=database)),
                               base_url="http://test") as client:
            url = f"/v1/local-scans/{original.id}/trace?submission_id={key}"
            headers = {"Content-Type": "application/octet-stream"}
            mismatch = await client.post(url, content=SOURCE + b"\n", headers=headers)
            assert mismatch.status_code == 409 and mismatch.json()["detail"] == "source_hash_mismatch"
            first = await client.post(url, content=SOURCE, headers=headers)
            assert first.status_code == 200 and first.json()["revision"] == 3
            assert (await client.post(url, content=SOURCE, headers=headers)).json() == first.json()
            historical = (await client.get(f"/v1/local-scans/{original.id}?revision=2")).json()
            assert historical["schema_version"] == "1.1" and "argument_investigation" not in historical
            assert (await client.post(url, content=b"x" * 65537, headers=headers)).status_code == 413
            assert (await client.post(url, content=SOURCE, headers=headers | {"Origin": "https://untrusted.invalid"})).status_code == 403
            assert (await client.post(url, json={"verified": True})).status_code == 415
            assert (await client.post(url.replace(str(key), "invalid"), content=SOURCE, headers=headers)).status_code == 422
            other = service.create_source_scan("not_reviewed.py", SOURCE)
            blocked = await client.post(f"/v1/local-scans/{other.id}/trace?submission_id={uuid4()}", content=SOURCE, headers=headers)
            assert blocked.status_code == 409 and blocked.json()["detail"] == "lineage_review_required"
    asyncio.run(exercise())
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(database))
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "example.py").write_bytes(SOURCE)
    result = CliRunner().invoke(app, ["scan-trace", original.id, "example.py", "--submission-id", str(key), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["argument_investigation"]["traces"][0]["hypothesis"]["origin_kind"] == "parameter"
    pretty = CliRunner().invoke(app, ["--no-animation", "scan-report", original.id, "--format", "pretty"])
    assert pretty.exit_code == 0, pretty.output
    assert "Origen del comando" in pretty.stdout and "Pasos reproducidos" in pretty.stdout
    assert "\x1b" not in pretty.stdout
    (tmp_path / "example.py").write_bytes(SOURCE + b"\n")
    error = CliRunner().invoke(app, ["scan-trace", original.id, "example.py", "--submission-id", str(key)])
    assert error.exit_code == 2 and "source_hash_mismatch" in error.stderr


def test_slow_trace_does_not_block_health_and_shares_two_upload_slots(tmp_path):
    service, original = setup_case(tmp_path / "responsive.sqlite3")
    entered, release = Event(), Event()

    class PausingService(AnalysisService):
        def trace_source_bytes(self, *args):
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test_release_timeout")
            return super().trace_source_bytes(*args)

    async def exercise():
        watchdog = Timer(5, release.set)
        watchdog.daemon = True
        watchdog.start()
        try:
            async with AsyncClient(transport=ASGITransport(app=create_app(service=PausingService(service._repository.database_path))),
                                   base_url="http://test") as client:
                url = f"/v1/local-scans/{original.id}/trace?submission_id={uuid4()}"
                headers = {"Content-Type": "application/octet-stream"}
                pending = [asyncio.create_task(client.post(url, content=SOURCE, headers=headers)) for _ in range(2)]
                try:
                    assert await asyncio.to_thread(entered.wait, 3)
                    health = await asyncio.wait_for(client.get("/health"), timeout=2)
                    assert health.status_code == 200 and not release.is_set()
                    busy = await client.post("/v1/local-scans?filename=extra.py", content=SOURCE, headers=headers)
                    assert busy.status_code == 503 and busy.json()["detail"] == "scanner_busy"
                finally:
                    release.set()
                    responses = await asyncio.wait_for(asyncio.gather(*pending), timeout=5)
                assert all(response.status_code == 200 for response in responses)
        finally:
            release.set()
            watchdog.cancel()
            watchdog.join(timeout=1)
    asyncio.run(exercise())
