import asyncio
import json
from typing import Any

from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge.api import create_app
from sentinelforge.cli import app as cli_app
from sentinelforge.contracts import AnalysisReport
from sentinelforge.service import AnalysisService


def stable_payload(report: AnalysisReport) -> dict[str, Any]:
    payload = report.model_dump(mode="json")
    payload["analysis"].pop("id")
    payload["analysis"].pop("created_at")
    for statement in payload["human_statements"]:
        statement.pop("created_at")
    return payload


def test_demo_report_keeps_simulated_evidence_and_human_statement_unverified() -> None:
    report = AnalysisService().create_demo_analysis()

    assert report.is_demo is True
    assert report.findings[0].verification_status == "inconclusive"
    assert report.evidence[0].verification_status == "simulated"
    assert report.human_statements[0].verification_status == "unverified"


def test_api_health_demo_and_report_lookup() -> None:
    async def exercise_api() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
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


def test_cli_and_api_emit_the_same_report_contract() -> None:
    cli_result = CliRunner().invoke(cli_app, ["demo"])
    assert cli_result.exit_code == 0, cli_result.output
    cli_report = AnalysisReport.model_validate(json.loads(cli_result.stdout))

    async def create_api_report() -> AnalysisReport:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://test",
        ) as client:
            response = await client.post("/v1/analyses")
            return AnalysisReport.model_validate(response.json())

    api_report = asyncio.run(create_api_report())

    assert stable_payload(cli_report) == stable_payload(api_report)
    assert cli_report.human_statements[0].verification_status == "unverified"


def test_web_page_explains_demo_limits() -> None:
    async def get_page():
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://test",
        ) as client:
            return await client.get("/")

    response = asyncio.run(get_page())
    assert response.status_code == 200
    assert "No analiza ni ejecuta código" in response.text
