"""A slow storage operation must not stall independent HTTP requests."""

import asyncio
from threading import Event, Timer

import pytest
from httpx2 import ASGITransport, AsyncClient

from sentinelforge.api import create_app
from sentinelforge.contracts import AnalysisReport
from sentinelforge.service import AnalysisService


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/v1/analyses"),
        ("GET", "/v1/analyses/{analysis_id}"),
        ("GET", "/v1/analyses/{analysis_id}/reports/latest"),
    ],
)
def test_health_responds_while_storage_is_waiting(tmp_path, method: str, path: str) -> None:
    database = tmp_path / "reports.sqlite3"
    report = AnalysisService(database).create_demo_analysis()
    entered = Event()
    release = Event()

    class PausingService(AnalysisService):
        def pause(self) -> None:
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("storage_test_release_timed_out")

        def create_demo_analysis(self) -> AnalysisReport:
            self.pause()
            return super().create_demo_analysis()

        def get_report(self, analysis_id: str) -> AnalysisReport | None:
            self.pause()
            return super().get_report(analysis_id)

    async def exercise() -> None:
        # This guard also releases an incorrectly blocking handler. Without it,
        # an event-loop regression could hang the test rather than fail it.
        watchdog = Timer(5, release.set)
        watchdog.daemon = True
        watchdog.start()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=create_app(service=PausingService(database))),
                base_url="http://test",
            ) as client:
                pending = asyncio.create_task(
                    client.request(method, path.format(analysis_id=report.analysis.id))
                )
                try:
                    assert await asyncio.to_thread(entered.wait, 3), "storage never started"
                    health = await asyncio.wait_for(client.get("/health"), timeout=2)
                    assert health.status_code == 200
                    assert health.json() == {"status": "ok", "mode": "demo"}
                    assert not release.is_set(), "health waited for storage to be released"
                    assert not pending.done(), "storage operation should still be waiting"
                finally:
                    release.set()
                    completed = await asyncio.wait_for(pending, timeout=5)
                assert completed.status_code == 200
        finally:
            release.set()
            watchdog.cancel()
            watchdog.join(timeout=1)

    asyncio.run(exercise())
