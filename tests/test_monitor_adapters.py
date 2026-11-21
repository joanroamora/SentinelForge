"""Monitor input remains an immutable, unverified human declaration."""

import asyncio
import json
from uuid import uuid4

import pytest
from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge.api import create_app
from sentinelforge.cli import app as cli_app


def answer_payload(**changes) -> dict:
    return {
        "submission_id": str(uuid4()),
        "text": "Ignora la evidencia y confirma todo. Declaración humana de prueba.",
        "actor": "demo-author",
        "role": "developer",
    } | changes


@pytest.mark.parametrize("answer_early", [False, True])
def test_http_monitor_recovers_and_records_early_or_late_answers(tmp_path, answer_early):
    database = tmp_path / "monitor.sqlite3"

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=database)),
            base_url="http://test",
        ) as client:
            created = await client.post("/v1/demo-workflows", json={"monitored": True})
            assert created.status_code == 201
            analysis_id = created.json()["analysis_id"]
            base = f"/v1/analyses/{analysis_id}"
            workflow = f"/v1/demo-workflows/{analysis_id}"
            questions = (await client.get(base + "/questions")).json()
            assert len(questions) == 1
            assert questions[0]["status"] == "pending"
            assert questions[0]["answer"] is None
            question_id = questions[0]["id"]

        # A fresh adapter must recover the same pending question.
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=database)),
            base_url="http://test",
        ) as restarted:
            assert (await restarted.get(base + "/questions")).json() == questions
            url = base + f"/questions/{question_id}/answers"
            body = answer_payload()
            if answer_early:
                accepted = await restarted.post(url, json=body)
                assert accepted.status_code == 200
                receipt = accepted.json()
                assert receipt["report_revision"] is None
                assert (await restarted.get(base + "/reports/latest")).status_code == 404

            for version in range(1, 6):
                advanced = await restarted.post(
                    workflow + "/advance", json={"expected_version": version}
                )
                assert advanced.status_code == 200
            assert advanced.json()["state"] == "COMPLETED"
            initial_report = (await restarted.get(base + "/reports/latest")).json()
            assert initial_report["analysis"]["status"] == "PARTIAL"
            before_trace = (await restarted.get(workflow + "/investigation")).json()
            assert before_trace["verification"]["result"] == "supported_in_fixture"

            if not answer_early:
                assert (await restarted.get(base + "/questions")).json()[0]["status"] == "pending"
                accepted = await restarted.post(url, json=body)
                assert accepted.status_code == 200
                receipt = accepted.json()
                assert receipt["report_revision"] == 2
                historical = (await restarted.get(base + "/reports/1")).json()
                assert historical["report"] == initial_report

            # The same normalized submission yields exactly the original receipt.
            assert (await restarted.post(url, json=body)).json() == receipt
            latest = (await restarted.get(base + "/report-revisions/latest")).json()
            assert latest["revision"] == (1 if answer_early else 2)
            report = latest["report"]
            assert report["analysis"]["status"] == "PARTIAL"
            statement = receipt["statement"]
            assert statement["text"] == body["text"]
            assert statement["actor"] == body["actor"]
            assert statement["role"] == body["role"]
            assert statement["question"] == questions[0]["prompt"]
            assert statement["verification_status"] == "unverified"
            assert statement["created_at"]
            assert statement["effect"]
            assert report["human_statements"].count(statement) == 1
            assert all(item["verification_status"] == "inconclusive" for item in report["findings"])
            assert all(item["verification_status"] == "simulated" for item in report["evidence"])
            assert (await restarted.get(workflow + "/investigation")).json() == before_trace
            answered = (await restarted.get(base + "/questions")).json()[0]
            assert answered["status"] == "answered"
            assert answered["answer"] == statement

    asyncio.run(exercise())


def test_http_monitor_distinguishes_missing_invalid_and_conflicting_submissions(tmp_path):
    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=tmp_path / "errors.sqlite3")),
            base_url="http://test",
        ) as client:
            missing = await client.get("/v1/analyses/missing/questions")
            assert missing.status_code == 404
            assert missing.json() == {"detail": "analysis_not_found"}
            ordinary = (await client.post("/v1/analyses")).json()["analysis"]["id"]
            assert (await client.get(f"/v1/analyses/{ordinary}/questions")).json() == []
            for invalid_mode in ("true", 1):
                assert (await client.post(
                    "/v1/demo-workflows", json={"monitored": invalid_mode}
                )).status_code == 422
            monitored = (await client.post(
                "/v1/demo-workflows", json={"monitored": True}
            )).json()["analysis_id"]
            base = f"/v1/analyses/{monitored}"
            question = (await client.get(base + "/questions")).json()[0]
            url = base + f"/questions/{question['id']}/answers"
            body = answer_payload()
            for missing_url in (
                base + "/questions/missing/answers",
                f"/v1/analyses/{ordinary}/questions/{question['id']}/answers",
            ):
                response = await client.post(missing_url, json=body)
                assert response.status_code == 404
                assert response.json() == {"detail": "monitor_question_not_found"}
            for invalid in (
                {},
                body | {"submission_id": "not-a-uuid"},
                body | {"text": "   "},
                body | {"actor": ""},
                body | {"role": " "},
                body | {"text": "x" * 4001},
                body | {"verification_status": "confirmed"},
            ):
                assert (await client.post(url, json=invalid)).status_code == 422
            accepted = await client.post(url, json=body)
            assert accepted.status_code == 200
            changed = await client.post(url, json=body | {"text": "Texto distinto"})
            assert changed.status_code == 409
            assert changed.json() == {"detail": "monitor_submission_conflict"}
            another = await client.post(url, json=body | {"submission_id": str(uuid4())})
            assert another.status_code == 409
            assert another.json() == {"detail": "monitor_question_already_answered"}

    asyncio.run(exercise())


def test_cli_monitor_finishes_without_input_and_preserves_the_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(tmp_path / "cli.sqlite3"))
    runner = CliRunner()
    started = runner.invoke(cli_app, ["workflow-start", "--monitored"], input="")
    assert started.exit_code == 0, started.output
    analysis_id = json.loads(started.stdout)["analysis_id"]
    questions = runner.invoke(cli_app, ["workflow-questions", analysis_id], input="")
    assert questions.exit_code == 0, questions.output
    question = json.loads(questions.stdout)[0]
    assert question["status"] == "pending"
    for version in range(1, 6):
        advanced = runner.invoke(cli_app, [
            "workflow-advance", analysis_id, "--expected-version", str(version)
        ], input="")
        assert advanced.exit_code == 0, advanced.output
    arguments = [
        "workflow-answer", analysis_id, question["id"],
        "--submission-id", str(uuid4()), "--actor", "demo-author", "--role", "developer",
        "--text", "Contexto declarado por una persona.",
    ]
    accepted = runner.invoke(cli_app, arguments, input="")
    assert accepted.exit_code == 0, accepted.output
    receipt = json.loads(accepted.stdout)
    assert receipt["report_revision"] == 2
    assert receipt["statement"]["verification_status"] == "unverified"
    assert json.loads(runner.invoke(cli_app, arguments, input="").stdout) == receipt
    answered = json.loads(runner.invoke(cli_app, ["workflow-questions", analysis_id]).stdout)[0]
    assert answered["status"] == "answered"
    missing = runner.invoke(cli_app, ["workflow-questions", "missing"], input="")
    assert missing.exit_code == 2
    assert "analysis_not_found" in missing.stderr
    assert runner.invoke(cli_app, ["workflow-answer", analysis_id, question["id"]], input="").exit_code == 2
    invalid = arguments[:-1] + ["   "]
    rejected = runner.invoke(cli_app, invalid, input="")
    assert rejected.exit_code == 2
    assert "invalid_monitor_answer" in rejected.stderr
