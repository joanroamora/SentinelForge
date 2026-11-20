"""Check recovery across actual Python processes and final-write concurrency."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from sentinelforge.repository import SQLiteReportRepository
from sentinelforge.service import AnalysisService


def test_cli_recovers_checkpoint_in_another_python_process(tmp_path) -> None:
    database = tmp_path / "process.sqlite3"
    environment = dict(os.environ, SENTINELFORGE_DATABASE_PATH=str(database))

    def invoke(*arguments: str) -> dict:
        result = subprocess.run(
            [sys.executable, "-m", "sentinelforge.cli", *arguments],
            env=environment, capture_output=True, text=True, check=True, timeout=20,
        )
        return json.loads(result.stdout)

    started = invoke("workflow-start")
    analysis_id = started["analysis_id"]
    advanced = invoke("workflow-advance", analysis_id, "--expected-version", "1")
    # Each invocation has exited; recovery cannot rely on a surviving Python object.
    assert invoke("workflow-status", analysis_id) == advanced
    for version in range(2, 6):
        completed = invoke(
            "workflow-advance", analysis_id, "--expected-version", str(version)
        )
    assert completed["state"] == "COMPLETED"
    report = AnalysisService(database).get_report(analysis_id)
    assert report is not None
    assert report.analysis.id == analysis_id
    assert report.human_statements[0].verification_status == "unverified"


def test_concurrent_final_advances_publish_one_report(tmp_path) -> None:
    database = tmp_path / "final-concurrency.sqlite3"
    service = AnalysisService(database)
    checkpoint = service.create_demo_workflow()
    for version in range(1, 5):
        checkpoint = service.advance_demo_workflow(
            checkpoint.analysis_id, expected_version=version
        )

    def complete(_: int):
        return AnalysisService(database).advance_demo_workflow(
            checkpoint.analysis_id, expected_version=5
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(complete, range(8)))
    assert all(result == results[0] for result in results)
    assert results[0].state == "COMPLETED"
    repository = SQLiteReportRepository(database)
    events = repository.list_events(checkpoint.analysis_id)
    assert len(events) == 7
    assert sum(event["event_type"] == "report_created" for event in events) == 1
    assert repository.get_revision(checkpoint.analysis_id).revision == 1
