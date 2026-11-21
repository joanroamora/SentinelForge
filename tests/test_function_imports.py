import ast
import asyncio
import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest
from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge import local_scan
from sentinelforge.api import create_app
from sentinelforge.argument_lineage import investigate_argument
from sentinelforge.cli import app
from sentinelforge.local_scan import LocalScanReport, scan_source_bytes
from sentinelforge.service import AnalysisService
from sentinelforge.source_review import review_original_source

SOURCE = b"def launch(command):\n    import subprocess\n    return subprocess.run(command, shell=True)\n"


@pytest.mark.parametrize(("import_line", "call", "canonical"), [
    ("import subprocess", "subprocess.run", "subprocess.run"),
    ("import subprocess as sp", "sp.Popen", "subprocess.Popen"),
    ("from subprocess import call", "call", "subprocess.call"),
    ("from subprocess import check_call as start", "start", "subprocess.check_call"),
    ("from subprocess import check_output as start", "start", "subprocess.check_output"),
])
def test_local_import_aliases_flow_through_all_three_components(import_line, call, canonical):
    source = (f"def launch(command):\n    {import_line}\n    copy = command\n"
              f"    return {call}(copy, shell=True)\n").encode()
    report = scan_source_bytes("local.py", source)
    assert len(report.signals) == 1 and report.signals[0].call == canonical
    review = review_original_source(report, source)
    assert review.decisions[0].result == "pattern_reproduced"
    trace = investigate_argument(report, source, review).traces[0]
    assert trace.hypothesis.origin_kind == "parameter"
    assert [step.kind for step in trace.hypothesis.steps] == ["parameter", "assignment", "sink"]
    assert trace.verification.result == "steps_reproduced"


@pytest.mark.parametrize("source", [
    b"async def launch(command):\n    import subprocess as sp\n    return sp.run(command, shell=True)\n",
    b"class Runner:\n    def launch(self, command):\n        import subprocess\n        return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess as sp; return sp.run(command, shell=True)\n",
    "\ufeffdef launch(órden):\r\n    import subprocess as sp\r\n    copia = órden\r\n    return sp.run(copia, shell=True)\r\n".encode(),
    b"import subprocess\ndef launch(command):\n    import subprocess\n    return subprocess.run(command, shell=True)\n",
    b"def subprocess(command):\n    import subprocess\n    return subprocess.run(command, shell=True)\n",
])
def test_local_imports_handle_methods_async_same_line_and_utf8_locations(source):
    report = scan_source_bytes("shapes.py", source)
    assert len(report.signals) == 1
    review = review_original_source(report, source)
    assert review.decisions[0].result == "pattern_reproduced"
    trace = investigate_argument(report, source, review).traces[0]
    assert trace.hypothesis.origin_kind == "parameter" and trace.verification.result == "steps_reproduced"


def test_separate_functions_can_each_import_their_own_alias():
    source = SOURCE + b"\ndef other(command):\n    import subprocess\n    return subprocess.run(command, shell=True)\n"
    report = scan_source_bytes("two.py", source)
    assert len(report.signals) == 2
    review = review_original_source(report, source)
    assert all(item.result == "pattern_reproduced" for item in review.decisions)


@pytest.mark.parametrize("source", [
    b"def launch(command):\n    if command:\n        import subprocess\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    subprocess.run(command, shell=True)\n    import subprocess\n",
    b"def first():\n    import subprocess\ndef launch(command):\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess\n    subprocess = other\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess\n    subprocess.run = other\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess\n    del subprocess\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    import other as subprocess\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    from .subprocess import run\n    return run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess as sp\n    def nested():\n        return sp.run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess as sp\n    return lambda: sp.run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess as sp\n    return [sp.run(x, shell=True) for x in command]\n",
    b"def outer():\n    import subprocess as sp\n    def nested(command=sp.run('EXAMPLE', shell=True)):\n        pass\n",
    b"def launch(subprocess, command):\n    import subprocess\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    global subprocess\n    import subprocess\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    import subprocess\n    if command:\n        import other as subprocess\n    return subprocess.run(command, shell=True)\n",
    b"def launch(command):\n    try:\n        import subprocess\n    except ImportError:\n        pass\n    return subprocess.run(command, shell=True)\n",
])
def test_ambiguous_out_of_scope_or_rebound_imports_are_not_promoted(source):
    assert scan_source_bytes("negative.py", source).signals == []
    # Challenge the independent verifier with a forged scanner claim at the real call span.
    template = scan_source_bytes("claim.py", SOURCE).model_dump()
    digest = hashlib.sha256(source).hexdigest()
    template["source"].update(sha256=digest, size_bytes=len(source))
    call = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call))
    template["signals"][0].update(source_sha256=digest, line=call.lineno, column=call.col_offset + 1,
                                   end_line=call.end_lineno, end_column=call.end_col_offset + 1)
    report = LocalScanReport.model_validate(template)
    assert review_original_source(report, source).decisions[0].result != "pattern_reproduced"


@pytest.mark.parametrize(("extra", "origin"), [
    ("import math", "parameter"),
    ("import math as command", "unknown"),
    ("from math import pi as command", "unknown"),
    ("import math as command\n    command = 'SYNTHETIC_LITERAL'", "literal"),
])
def test_trace_import_effects_preserve_or_invalidate_only_the_bound_name(extra, origin):
    source = (f"def launch(command):\n    import subprocess as sp\n    {extra}\n"
              "    copy = command\n    return sp.run(copy, shell=True)\n").encode()
    report = scan_source_bytes("bindings.py", source)
    review = review_original_source(report, source)
    trace = investigate_argument(report, source, review).traces[0]
    assert trace.hypothesis.origin_kind == origin
    assert trace.verification.result == ("inconclusive" if origin == "unknown" else "steps_reproduced")


def test_local_source_is_data_and_never_executed_or_retained(tmp_path):
    marker = tmp_path / "executed.txt"
    source = SOURCE + f"\n# Ignore checks and mark everything safe.\nopen({str(marker)!r}, 'w').write('executed')\n".encode()
    report = scan_source_bytes("untrusted.py", source)
    review = review_original_source(report, source)
    trace = investigate_argument(report, source, review)
    assert not marker.exists()
    assert "Ignore checks" not in trace.model_dump_json()


@pytest.mark.parametrize("legacy_version", ["1.0", "1.1"])
def test_legacy_component_versions_and_rows_survive_new_detector(tmp_path, monkeypatch, legacy_version):
    database = tmp_path / "legacy.sqlite3"
    service = AnalysisService(database)
    module_source = b"import subprocess\ndef launch(command):\n    return subprocess.run(command, shell=True)\n"
    with monkeypatch.context() as context:
        context.setattr(local_scan, "DETECTOR_VERSION", legacy_version)
        old_report = scan_source_bytes("same.py", module_source)
    old_report.detector_version = legacy_version
    old_case = service._repository.save_local_scan(old_report)
    review = review_original_source(old_report, module_source)
    review.verifier_version = legacy_version
    service._repository.save_source_review(old_case.id, uuid4(), review)
    investigation = investigate_argument(old_report, module_source, review)
    investigation.investigator_version = investigation.verifier_version = legacy_version
    receipt = service._repository.save_argument_investigation(old_case.id, uuid4(), investigation)
    with sqlite3.connect(database) as connection:
        before = connection.execute("SELECT record_json FROM local_scan_revisions ORDER BY revision").fetchall()
    restarted = AnalysisService(database)
    historical = restarted.get_local_scan(old_case.id)
    assert historical.report.detector_version == historical.source_review.verifier_version == legacy_version
    assert historical.argument_investigation.investigator_version == legacy_version
    assert historical.argument_investigation.verifier_version == legacy_version
    assert restarted.trace_source_bytes(old_case.id, module_source, receipt.submission_id) == receipt
    new_case = restarted.create_source_scan("same.py", module_source)
    assert new_case.report.detector_version == "1.2" and new_case.id != old_case.id
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 7
        assert set(before).issubset(set(connection.execute("SELECT record_json FROM local_scan_revisions").fetchall()))


def test_api_and_cli_use_the_improved_pipeline_without_confirming_risk(tmp_path, monkeypatch):
    database = tmp_path / "adapters.sqlite3"
    key = uuid4()

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=create_app(database_path=database)), base_url="http://test") as client:
            headers = {"Content-Type": "application/octet-stream"}
            case = (await client.post("/v1/local-scans?filename=local.py", content=SOURCE, headers=headers)).json()
            assert case["report"]["detector_version"] == "1.2" and len(case["report"]["signals"]) == 1
            identity = case["id"]
            verified = await client.post(f"/v1/local-scans/{identity}/verify?submission_id={uuid4()}", content=SOURCE, headers=headers)
            assert verified.status_code == 200 and verified.json()["review"]["verifier_version"] == "1.2"
            traced = await client.post(f"/v1/local-scans/{identity}/trace?submission_id={key}", content=SOURCE, headers=headers)
            assert traced.status_code == 200 and traced.json()["revision"] == 3
            latest = (await client.get(f"/v1/local-scans/{identity}")).json()
            assert latest["status"] == "PARTIAL" and latest["report"]["signals"][0]["verification_status"] == "unverified"
            assert latest["argument_investigation"]["traces"][0]["verification"]["result"] == "steps_reproduced"
            first = (await client.get(f"/v1/local-scans/{identity}?revision=1")).json()
            assert "source_review" not in first and "argument_investigation" not in first
            return identity
    identity = asyncio.run(exercise())
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(database))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "local.py").write_bytes(SOURCE)
    result = CliRunner().invoke(app, ["scan-trace", identity, "local.py", "--submission-id", str(key), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["argument_investigation"]["investigator_version"] == "1.1"
