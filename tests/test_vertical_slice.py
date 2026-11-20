import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge.api import create_app
from sentinelforge.cli import app as cli_app
from sentinelforge.contracts import AnalysisReport
from sentinelforge.repository import ReportConflictError, SQLiteReportRepository
from sentinelforge.service import AnalysisService


def stable_payload(report: AnalysisReport) -> dict[str, Any]:
    payload = report.model_dump(mode="json")
    payload["analysis"].pop("id")
    payload["analysis"].pop("created_at")
    for statement in payload["human_statements"]:
        statement.pop("created_at")
    return payload


def test_demo_report_keeps_simulated_evidence_and_human_statement_unverified(
    tmp_path,
) -> None:
    report = AnalysisService(tmp_path / "reports.sqlite3").create_demo_analysis()

    assert report.is_demo is True
    assert report.findings[0].verification_status == "inconclusive"
    assert report.evidence[0].verification_status == "simulated"
    assert report.human_statements[0].verification_status == "unverified"


def test_api_health_demo_and_report_lookup(tmp_path) -> None:
    async def exercise_api() -> None:
        async with AsyncClient(
            transport=ASGITransport(
                app=create_app(database_path=tmp_path / "api.sqlite3")
            ),
            base_url="http://test",
        ) as client:
            assert (await client.get("/health")).json() == {
                "status": "ok",
                "mode": "demo",
            }
            created = await client.post("/v1/analyses")
            assert created.status_code == 200
            report = AnalysisReport.model_validate(created.json())
            assert (
                await client.get(f"/v1/analyses/{report.analysis.id}")
            ).json() == created.json()
            assert (
                await client.get(
                    f"/v1/analyses/{report.analysis.id}/reports/latest"
                )
            ).json() == created.json()
            assert (await client.get("/v1/analyses/missing")).status_code == 404

    asyncio.run(exercise_api())


def test_cli_and_api_emit_the_same_report_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(
        "SENTINELFORGE_DATABASE_PATH", str(tmp_path / "cli.sqlite3")
    )
    cli_result = CliRunner().invoke(cli_app, ["demo"])
    assert cli_result.exit_code == 0, cli_result.output
    cli_report = AnalysisReport.model_validate(json.loads(cli_result.stdout))

    async def create_api_report() -> AnalysisReport:
        async with AsyncClient(
            transport=ASGITransport(
                app=create_app(database_path=tmp_path / "api.sqlite3")
            ),
            base_url="http://test",
        ) as client:
            response = await client.post("/v1/analyses")
            return AnalysisReport.model_validate(response.json())

    api_report = asyncio.run(create_api_report())

    assert stable_payload(cli_report) == stable_payload(api_report)
    assert cli_report.human_statements[0].verification_status == "unverified"


def test_web_page_explains_demo_limits(tmp_path) -> None:
    async def get_page():
        async with AsyncClient(
            transport=ASGITransport(
                app=create_app(database_path=tmp_path / "web.sqlite3")
            ),
            base_url="http://test",
        ) as client:
            return await client.get("/")

    response = asyncio.run(get_page())
    assert response.status_code == 200
    assert "No analiza ni ejecuta código" in response.text


def test_report_survives_service_restart_and_records_one_event(tmp_path) -> None:
    database_path = tmp_path / "restart.sqlite3"
    report = AnalysisService(database_path).create_demo_analysis()

    recovered = AnalysisService(database_path).get_report(report.analysis.id)
    events = SQLiteReportRepository(database_path).list_events(report.analysis.id)

    assert recovered == report
    assert len(events) == 1
    assert events[0]["event_type"] == "report_created"
    assert json.loads(events[0]["payload_json"]) == {"revision": 1}


def test_saving_same_report_is_idempotent_and_conflicting_content_fails(
    tmp_path,
) -> None:
    repository = SQLiteReportRepository(tmp_path / "idempotency.sqlite3")
    report = AnalysisService(tmp_path / "idempotency.sqlite3").create_demo_analysis()

    repository.save_report(report)
    assert len(repository.list_events(report.analysis.id)) == 1

    conflicting_report = report.model_copy(deep=True)
    conflicting_report.analysis.status = "PARTIAL"
    with pytest.raises(ReportConflictError, match="report_revision_conflict"):
        repository.save_report(conflicting_report)


def test_new_report_revision_preserves_history_and_is_retry_safe(tmp_path) -> None:
    database_path = tmp_path / "revisions.sqlite3"
    service = AnalysisService(database_path)
    original = service.create_demo_analysis()
    revised = original.model_copy(deep=True)
    revised.limitations.append("Revisión sintética para probar historial.")

    revision = service.append_report_revision(revised, expected_revision=1)
    retried_revision = service.append_report_revision(revised, expected_revision=1)
    events = SQLiteReportRepository(database_path).list_events(original.analysis.id)

    assert revision == retried_revision == 2
    assert service.get_report(original.analysis.id) == revised
    assert len(events) == 2
    assert events[1]["event_type"] == "report_revision_created"
    assert json.loads(events[1]["payload_json"]) == {"revision": 2}
    assert original.limitations != revised.limitations

    stale_revision = original.model_copy(deep=True)
    with pytest.raises(ReportConflictError, match="report_revision_conflict"):
        service.append_report_revision(stale_revision, expected_revision=1)


def test_reports_and_events_are_immutable_in_sqlite(tmp_path) -> None:
    database_path = tmp_path / "immutable.sqlite3"
    report = AnalysisService(database_path).create_demo_analysis()

    with sqlite3.connect(database_path) as connection:
        try:
            connection.execute(
                "UPDATE report_revisions SET report_json = '{}' WHERE analysis_id = ?",
                (report.analysis.id,),
            )
        except sqlite3.IntegrityError as error:
            assert "report_revisions_are_immutable" in str(error)
        else:
            raise AssertionError("report revisions must reject updates")

        try:
            connection.execute(
                "DELETE FROM analysis_events WHERE analysis_id = ?",
                (report.analysis.id,),
            )
        except sqlite3.IntegrityError as error:
            assert "analysis_events_are_append_only" in str(error)
        else:
            raise AssertionError("analysis events must reject deletes")


def test_concurrent_demo_reports_are_recoverable(tmp_path) -> None:
    database_path = tmp_path / "concurrent.sqlite3"

    with ThreadPoolExecutor(max_workers=6) as executor:
        reports = list(
            executor.map(
                lambda _: AnalysisService(database_path).create_demo_analysis(),
                range(12),
            )
        )

    repository = SQLiteReportRepository(database_path)
    assert len({report.analysis.id for report in reports}) == 12
    assert all(repository.get_report(report.analysis.id) == report for report in reports)
