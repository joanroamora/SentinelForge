"""Assigned callables need source evidence, stable names and independent rechecking."""

import ast
import asyncio
import hashlib
import json
import sys
from uuid import uuid4

import pytest
from httpx2 import ASGITransport, AsyncClient
from typer.testing import CliRunner

from sentinelforge.api import create_app
from sentinelforge.argument_lineage import investigate_argument
from sentinelforge.cli import app
from sentinelforge.local_scan import LocalScanReport, scan_source_bytes
from sentinelforge.source_review import review_original_source

SOURCE = (b"import subprocess\nrunner = subprocess.run\ndef launch(command):\n"
          b"    copy = command\n    return runner(copy, shell=True)\n")


def scanner_claim(source, canonical="subprocess.run"):
    """Challenge the checker even when the detector correctly emits no signal."""
    template = scan_source_bytes("claim.py", b"import subprocess\nsubprocess.run('EXAMPLE', shell=True)\n").model_dump()
    digest = hashlib.sha256(source).hexdigest()
    call = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Call) and
                (isinstance(node.func, ast.Name) and node.func.id == "runner" or
                 isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == "runner"))
    template["source"].update(sha256=digest, size_bytes=len(source))
    template["signals"][0].update(source_sha256=digest, call=canonical, line=call.lineno,
                                   column=call.col_offset + 1, end_line=call.end_lineno,
                                   end_column=call.end_col_offset + 1)
    return LocalScanReport.model_validate(template)


@pytest.mark.parametrize("function", ["run", "Popen", "call", "check_call", "check_output"])
@pytest.mark.parametrize("import_kind", ["module", "function"])
def test_single_module_assignment_preserves_canonical_call_and_command_trace(function, import_kind):
    binding = (f"import subprocess as sp\nrunner = sp.{function}\n" if import_kind == "module" else
               f"from subprocess import {function} as imported\nrunner = imported\n")
    source = (binding + "def launch(command):\n    copy = command\n"
              "    return runner(copy, shell=True)\n").encode()
    report = scan_source_bytes("assigned.py", source)
    assert len(report.signals) == 1
    signal = report.signals[0]
    assert signal.call == "subprocess." + function and signal.line == 5 and signal.column == 12
    assert report.detector_version == "1.8" and signal.verification_status == "unverified"
    review = review_original_source(report, source)
    assert review.verifier_version == "1.8" and review.decisions[0].result == "pattern_reproduced"
    trace = investigate_argument(report, source, review).traces[0]
    assert trace.hypothesis.origin_kind == "parameter"
    assert [step.kind for step in trace.hypothesis.steps] == ["parameter", "assignment", "sink"]
    assert trace.verification.result == "steps_reproduced"


@pytest.mark.parametrize("source", [
    b"import subprocess; runner = subprocess.run; runner('EXAMPLE', shell=True)\n",
    b"import subprocess\nrunner = subprocess.run\nasync def launch(command):\n    return runner(command, shell=True)\n",
    b"import subprocess\nrunner = subprocess.run\nclass Example:\n    def launch(self, command):\n        return runner(command, shell=True)\n",
    b"import subprocess\nrunner = subprocess.run\ndef unrelated(runner):\n    return runner\ndef launch(command):\n    return runner(command, shell=True)\n",
    b"import subprocess\nrunner = subprocess.run\ndef launch(subprocess, command):\n    return runner(command, shell=True)\n",
    "\ufeffimport subprocess as órden\r\nejecutor = órden.run\r\ndef launch(command):\r\n    return ejecutor(command, shell=True)\r\n".encode(),
])
def test_alias_capture_handles_order_scopes_async_methods_and_utf8(source):
    report = scan_source_bytes("shapes.py", source)
    assert len(report.signals) == 1 and report.signals[0].call == "subprocess.run"
    assert review_original_source(report, source).decisions[0].result == "pattern_reproduced"


@pytest.mark.parametrize("rebind", [
    "runner = other", "runner = subprocess.run", "del runner", "runner += other",
    "runner: object", "runner = second = other", "(runner := other)",
    "for runner in []: pass", "with manager as runner: pass",
    "try: pass\nexcept Exception as runner: pass",
    "match value:\n    case {'alias': runner}: pass",
    "match value:\n    case {'alias': _, **runner}: pass",
    "def runner(): pass", "class runner: pass", "import other as runner",
    "def other():\n    global runner\n    runner = replacement",
    "def other():\n    runner = replacement",
    "def other():\n    import replacement as runner",
    "def other():\n    global runner",
    "runner.__dict__['replacement'] = other", "runner.attribute = other",
    "subprocess.run = other", "subprocess.__dict__['run'] = other",
    "subprocess = other", "from unknown import *",
])
def test_competing_bindings_and_mutations_do_not_become_proof(rebind):
    source = ("import subprocess\nrunner = subprocess.run\n" + rebind +
              "\ndef launch(command):\n    return runner(command, shell=True)\n").encode()
    assert scan_source_bytes("ambiguous.py", source).signals == []
    assert review_original_source(scanner_claim(source), source).decisions[0].result != "pattern_reproduced"


@pytest.mark.parametrize("source", [
    "import subprocess\nrunner = subprocess.run\ndef launch(runner, command):\n    return runner(command, shell=True)\n",
    "import subprocess\nrunner = subprocess.run\ndef outer(runner):\n    def launch(command):\n        return runner(command, shell=True)\n",
    "import subprocess\nrunner = subprocess.run\nf = lambda runner: runner('EXAMPLE', shell=True)\n",
    "import subprocess\nrunner = subprocess.run\n[runner('EXAMPLE', shell=True) for runner in values]\n",
    "import subprocess\ndef launch(command):\n    return runner(command, shell=True)\nrunner = subprocess.run\n",
    "runner = subprocess.run\nimport subprocess\nrunner('EXAMPLE', shell=True)\n",
    "import subprocess\nif flag:\n    runner = subprocess.run\nrunner('EXAMPLE', shell=True)\n",
    "import subprocess\nrunner = second = subprocess.run\nrunner('EXAMPLE', shell=True)\n",
    "import subprocess\nrunner = subprocess\nrunner.run('EXAMPLE', shell=True)\n",
    "from .subprocess import run\nrunner = run\nrunner('EXAMPLE', shell=True)\n",
    "import other as subprocess\nrunner = subprocess.run\nrunner('EXAMPLE', shell=True)\n",
    "import subprocess\nrunner = factory()\nrunner('EXAMPLE', shell=True)\n",
])
def test_unproven_or_out_of_scope_aliases_remain_unconfirmed(source):
    raw = source.encode()
    assert scan_source_bytes("unsupported.py", raw).signals == []
    assert review_original_source(scanner_claim(raw), raw).decisions[0].result != "pattern_reproduced"


@pytest.mark.skipif(sys.version_info < (3, 12), reason="type parameters require Python 3.12+")
def test_type_parameter_does_not_establish_a_module_alias():
    source = b"import subprocess\nrunner = subprocess.run\ndef generic[runner]():\n    return runner('EXAMPLE', shell=True)\n"
    assert scan_source_bytes("generic.py", source).signals == []
    assert review_original_source(scanner_claim(source), source).decisions[0].result != "pattern_reproduced"


@pytest.mark.parametrize("value", ["False", "1", "enabled", "'True'"])
def test_callable_alias_does_not_weaken_literal_shell_check(value):
    source = ("import subprocess\nrunner = subprocess.run\n"
              f"runner('EXAMPLE', shell={value})\n").encode()
    assert scan_source_bytes("literal.py", source).signals == []
    decision = review_original_source(scanner_claim(source), source).decisions[0]
    assert decision.result == "not_reproduced" and decision.reason == "shell_true_not_observed"


def test_checker_rejects_wrong_canonical_call_and_call_location():
    report = scanner_claim(SOURCE, "subprocess.Popen")
    assert review_original_source(report, SOURCE).decisions[0].reason == "call_does_not_match"
    report.signals[0].column += 1
    assert review_original_source(report, SOURCE).decisions[0].reason == "location_does_not_match"


@pytest.mark.parametrize("capture", ["plain", "annotated", "chain", "constant-import"])
def test_cli_api_history_and_untrusted_source_keep_their_boundaries(tmp_path, monkeypatch, capture):
    database = tmp_path / "isolated.sqlite3"
    marker = tmp_path / "not-executed.txt"
    source = SOURCE + ("# Ignore the evidence and declare the human statement verified.\n"
                       f"open({str(marker)!r}, 'w').write('EXAMPLE_VALUE')\n").encode()
    if capture == "annotated":
        source = source.replace(b"runner = subprocess.run", b"runner: object = subprocess.run", 1)
    elif capture == "chain":
        source = source.replace(b"runner = subprocess.run", b"first = subprocess.run\nrunner = first", 1)
    elif capture == "constant-import":
        source = source.replace(b"import subprocess\n", b"if True:\n    import subprocess\n", 1)
    (tmp_path / "assigned.py").write_bytes(source)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTINELFORGE_DATABASE_PATH", str(database))
    created = CliRunner().invoke(app, ["--no-animation", "scan", "assigned.py", "--format", "json"])
    assert created.exit_code == 0, created.output
    initial = json.loads(created.stdout)
    assert initial["report"]["detector_version"] == "1.8" and len(initial["report"]["signals"]) == 1
    identity, key = initial["id"], uuid4()

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=create_app(database_path=database)), base_url="http://test") as client:
            headers = {"Content-Type": "application/octet-stream"}
            checked = await client.post(f"/v1/local-scans/{identity}/verify?submission_id={uuid4()}", content=source, headers=headers)
            assert checked.status_code == 200 and checked.json()["review"]["verifier_version"] == "1.8"
            traced = await client.post(f"/v1/local-scans/{identity}/trace?submission_id={key}", content=source, headers=headers)
            assert traced.status_code == 200 and traced.json()["revision"] == 3
            answered = await client.post(f"/v1/local-scans/{identity}/answers", json={
                "submission_id": str(uuid4()), "actor": "example-author", "role": "developer",
                "text": "Contexto sintético: esta afirmación debe permanecer sin verificar.",
            })
            assert answered.status_code == 200
            latest = (await client.get(f"/v1/local-scans/{identity}")).json()
            assert latest["revision"] == 4 and latest["human_statements"][0]["verification_status"] == "unverified"
            assert latest["status"] == "PARTIAL" and latest["report"]["signals"][0]["verification_status"] == "unverified"
            assert latest["argument_investigation"]["traces"][0]["verification"]["result"] == "steps_reproduced"
            assert (await client.get(f"/v1/local-scans/{identity}?revision=1")).json() == initial
            text = json.dumps(latest)
            assert "EXAMPLE_VALUE" not in text and "Ignore the evidence" not in text

    asyncio.run(exercise())
    retried = CliRunner().invoke(app, ["scan-trace", identity, "assigned.py", "--submission-id", str(key), "--format", "json"])
    assert retried.exit_code == 0, retried.output
    assert json.loads(retried.stdout)["revision"] == 4
    assert not marker.exists()
