"""Exercise the persistent demo cycle through its public adapters."""

import asyncio
import json

from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge.api import create_app
from sentinelforge.cli import app as cli_app
from sentinelforge.contracts import AnalysisReport
from sentinelforge.workflow import WorkflowCheckpoint


def test_http_workflow_recovers_advances_and_publishes_only_at_completion(tmp_path) -> None:
    database = tmp_path / "workflow.sqlite3"

    async def exercise() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=database)),
            base_url="http://test",
        ) as client:
            started = await client.post("/v1/demo-workflows")
            assert started.status_code == 201
            initial = WorkflowCheckpoint.model_validate(started.json())
            assert initial.state == "RECEIVED"
            assert initial.version == 1
            base = f"/v1/demo-workflows/{initial.analysis_id}"
            report_url = f"/v1/analyses/{initial.analysis_id}/reports/latest"
            assert (await client.get(base)).json() == started.json()
            assert (await client.get(report_url)).status_code == 404
            first_advance = await client.post(base + "/advance", json={"expected_version": 1})
            assert first_advance.status_code == 200
            assert first_advance.json()["state"] == "DETECTING"

        # A fresh adapter/service must continue the same persisted cycle.
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=database)),
            base_url="http://test",
        ) as restarted:
            assert (await restarted.get(base)).json() == first_advance.json()
            for version, state in enumerate(
                ["INVESTIGATING", "VERIFYING", "REPORTING", "COMPLETED"], start=2
            ):
                assert (await restarted.get(report_url)).status_code == 404
                response = await restarted.post(
                    base + "/advance", json={"expected_version": version}
                )
                assert response.status_code == 200
                assert response.json()["state"] == state
                assert response.json()["version"] == version + 1

            completed = response.json()
            assert (
                await restarted.post(base + "/advance", json={"expected_version": 6})
            ).json() == completed
            # A late replay returns its original result without advancing again.
            assert (
                await restarted.post(base + "/advance", json={"expected_version": 1})
            ).json() == first_advance.json()
            assert (await restarted.get(base)).json() == completed
            report_response = await restarted.get(report_url)
            assert report_response.status_code == 200
            report = AnalysisReport.model_validate(report_response.json())
            assert report.analysis.id == initial.analysis_id
            assert report.is_demo
            assert report.evidence[0].verification_status == "simulated"
            assert report.human_statements[0].verification_status == "unverified"

    asyncio.run(exercise())


def test_http_workflow_distinguishes_missing_conflict_and_invalid_input(tmp_path) -> None:
    async def exercise() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=tmp_path / "errors.sqlite3")),
            base_url="http://test",
        ) as client:
            missing = "/v1/demo-workflows/missing"
            assert (await client.get(missing)).json() == {"detail": "workflow_not_found"}
            assert (await client.get(missing)).status_code == 404
            assert (
                await client.post(missing + "/advance", json={"expected_version": 1})
            ).status_code == 404
            created = (await client.post("/v1/demo-workflows")).json()
            base = f"/v1/demo-workflows/{created['analysis_id']}"
            conflict = await client.post(base + "/advance", json={"expected_version": 2})
            assert conflict.status_code == 409
            assert conflict.json() == {"detail": "workflow_version_conflict"}
            for invalid in (
                {},
                {"expected_version": 0},
                {"expected_version": True},
                {"expected_version": "1"},
                {"expected_version": 1, "state": "COMPLETED"},
            ):
                assert (await client.post(base + "/advance", json=invalid)).status_code == 422
            assert (await client.get(base)).json() == created

    asyncio.run(exercise())


def test_cli_and_http_continue_the_same_persisted_workflow(tmp_path, monkeypatch) -> None:
    database = tmp_path / "shared.sqlite3"
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(database))
    runner = CliRunner()
    started = runner.invoke(cli_app, ["workflow-start"])
    assert started.exit_code == 0, started.output
    checkpoint = json.loads(started.stdout)
    analysis_id = checkpoint["analysis_id"]
    status = runner.invoke(cli_app, ["workflow-status", analysis_id])
    assert status.exit_code == 0
    assert json.loads(status.stdout) == checkpoint

    async def advance_over_http():
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=database)),
            base_url="http://test",
        ) as client:
            response = await client.post(
                f"/v1/demo-workflows/{analysis_id}/advance", json={"expected_version": 1}
            )
            assert response.status_code == 200
            return response.json()

    http_checkpoint = asyncio.run(advance_over_http())
    status = runner.invoke(cli_app, ["workflow-status", analysis_id])
    assert json.loads(status.stdout) == http_checkpoint
    advanced = runner.invoke(cli_app, ["workflow-advance", analysis_id, "--expected-version", "2"])
    assert advanced.exit_code == 0, advanced.output
    assert json.loads(advanced.stdout)["state"] == "INVESTIGATING"
    assert json.loads(advanced.stdout)["version"] == 3


def test_cli_workflow_errors_exit_without_interactive_input(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(tmp_path / "cli-errors.sqlite3"))
    runner = CliRunner()
    for arguments in (
        ["workflow-status", "missing"],
        ["workflow-advance", "missing", "--expected-version", "1"],
    ):
        missing = runner.invoke(cli_app, arguments)
        assert missing.exit_code == 2
        assert "workflow_not_found" in missing.stderr
    started = runner.invoke(cli_app, ["workflow-start"])
    analysis_id = json.loads(started.stdout)["analysis_id"]
    conflict = runner.invoke(cli_app, ["workflow-advance", analysis_id, "--expected-version", "2"])
    assert conflict.exit_code == 2
    assert "workflow_version_conflict" in conflict.stderr
    assert runner.invoke(cli_app, ["workflow-advance", analysis_id]).exit_code == 2
    invalid = runner.invoke(cli_app, ["workflow-advance", analysis_id, "--expected-version", "0"])
    assert invalid.exit_code == 2
    status = runner.invoke(cli_app, ["workflow-status", analysis_id])
    assert json.loads(status.stdout)["version"] == 1
