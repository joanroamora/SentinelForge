import asyncio
from concurrent.futures import ThreadPoolExecutor

from httpx2 import ASGITransport, AsyncClient

from sentinelforge.api import create_app
from sentinelforge.repository import SQLiteReportRepository


def test_api_revision_history_retry_validation_and_restart(tmp_path):
    database = tmp_path / "reports.sqlite3"

    async def exercise():
        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=database)),
            base_url="http://test",
        ) as client:
            original = (await client.post("/v1/analyses")).json()
            analysis_id = original["analysis"]["id"]
            base = f"/v1/analyses/{analysis_id}"
            assert (await client.get(f"{base}/report-revisions/latest")).json()["revision"] == 1
            body = {"expected_revision": 1, "limitation": "Contexto pendiente."}
            revised = await client.post(f"{base}/report-revisions", json=body)
            assert revised.status_code == 200
            assert revised.json()["revision"] == 2
            assert (await client.post(f"{base}/report-revisions", json=body)).json() == revised.json()
            body["limitation"] = "Otro cambio."
            assert (await client.post(f"{base}/report-revisions", json=body)).status_code == 409
            assert (await client.get(f"{base}/reports/1")).json()["report"] == original
            assert (await client.get(f"{base}/reports/99")).status_code == 404
            assert (await client.get(f"{base}/reports/0")).status_code == 422
            for invalid in ("", "   "):
                body["limitation"] = invalid
                assert (await client.post(f"{base}/report-revisions", json=body)).status_code == 422
            assert (await client.post("/v1/analyses/missing/report-revisions", json={
                "expected_revision": 1, "limitation": "Nota."
            })).status_code == 404

        async with AsyncClient(
            transport=ASGITransport(app=create_app(database_path=database)),
            base_url="http://test",
        ) as restarted:
            recovered = (await restarted.get(f"{base}/report-revisions/latest")).json()
            assert recovered == revised.json()
            assert recovered["report"]["human_statements"] == original["human_statements"]

        assert len(SQLiteReportRepository(database).list_events(analysis_id)) == 2

    asyncio.run(exercise())


def test_concurrent_api_revisions_allow_one_writer(tmp_path):
    from sentinelforge.service import AnalysisService

    database = tmp_path / "concurrent.sqlite3"
    analysis_id = AnalysisService(database).create_demo_analysis().analysis.id

    def submit(note):
        async def request():
            async with AsyncClient(
                transport=ASGITransport(app=create_app(database_path=database)),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    f"/v1/analyses/{analysis_id}/report-revisions",
                    json={"expected_revision": 1, "limitation": note},
                )
                return response.status_code

        return asyncio.run(request())

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(submit, ["Cambio A", "Cambio B"]))
    assert sorted(statuses) == [200, 409]
    repository = SQLiteReportRepository(database)
    assert repository.get_revision(analysis_id).revision == 2
    assert len(repository.list_events(analysis_id)) == 2
