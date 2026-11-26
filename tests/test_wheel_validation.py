import hashlib
import json
import subprocess
import sys
import tomllib
from importlib.metadata import PackagePath
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_installed_wheel as probe
from scripts import validate_wheel as packaging
from sentinelforge import __version__
from sentinelforge.api import app


def test_package_and_openapi_agree_with_the_declared_distribution():
    project = tomllib.loads((packaging.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert app.openapi()["info"]["version"] == __version__ == project["project"]["version"]


def test_development_interpreter_is_never_evidence_of_a_clean_installation():
    result = subprocess.run([sys.executable, "-I", str(Path(probe.__file__)), "unused.whl"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2 and not result.stdout
    assert result.stderr.strip() == "wheel_requires_isolated_local_environment"


@pytest.mark.parametrize(("isolated", "inherits_system", "external_site", "expected"), [
    (True, "false", False, None),
    (False, "false", False, "wheel_requires_isolated_local_environment"),
    (True, "true", False, "wheel_requires_private_site_packages"),
    (True, "false", True, "wheel_site_outside_environment"),
])
def test_consumer_environment_must_have_its_own_packages(
        tmp_path, monkeypatch, isolated, inherits_system, external_site, expected):
    prefix = tmp_path / ".local/consumer"
    prefix.mkdir(parents=True)
    (prefix / "pyvenv.cfg").write_text(f"include-system-site-packages={inherits_system}\n")
    site = (tmp_path if external_site else prefix) / "site-packages"
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.setattr(probe, "sys", SimpleNamespace(prefix=str(prefix), base_prefix="base",
                                                       flags=SimpleNamespace(isolated=isolated)))
    monkeypatch.setattr(probe.sysconfig, "get_path", lambda _: str(site))
    if expected:
        with pytest.raises(probe.WheelCheckError, match=f"^{expected}$"):
            probe.check_environment()
    else:
        assert probe.check_environment() == site


@pytest.mark.parametrize("change", ["none", "modified", "editable", "missing", "remote"])
def test_installed_archive_identity_requires_the_actual_local_bytes(tmp_path, monkeypatch, change):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    wheel = tmp_path / "example.whl"
    wheel.write_bytes(b"local archive identity fixture")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    origin = {"url": wheel.as_uri(), "archive_info": {"hashes": {"sha256": digest}}}
    if change == "modified":
        wheel.write_bytes(b"different bytes")
    elif change == "editable":
        origin["dir_info"] = {"editable": True}
    elif change == "missing":
        origin = {}
    elif change == "remote":
        origin["url"] = "https://example.invalid/example.whl"
    dist = SimpleNamespace(read_text=lambda _: json.dumps(origin))
    if change == "none":
        assert probe.check_origin(dist, wheel) == digest
    else:
        with pytest.raises(probe.WheelCheckError, match="^wheel_installed_archive_mismatch$"):
            probe.check_origin(dist, wheel)


@pytest.mark.parametrize("change", ["none", "unlisted", "missing", "changed", "extra"])
def test_installed_inventory_and_asset_contents(tmp_path, change):
    source, installed = tmp_path / "src", tmp_path / "installed"
    files = ["__init__.py", "_scan_worker.py", "data/a.json", "static/index.html", "static/app.js"]
    for folder in (source, installed):
        for name in files:
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
    if change == "unlisted":
        files.remove("static/index.html")
    elif change == "missing":
        (installed / "data/a.json").unlink()
    elif change == "changed":
        (installed / "static/app.js").write_bytes(b"old")
    elif change == "extra":
        files.append("unintended.txt")
    record = [PackagePath(f"sentinelforge/{name}") for name in files]
    record.append(PackagePath("sentinelforge/__pycache__/__init__.cpython-311.pyc"))
    if change == "none":
        assert probe.check_payload(source, installed, record) == len(files)
    else:
        with pytest.raises(probe.WheelCheckError, match="wheel_payload_"):
            probe.check_payload(source, installed, record)


def test_offline_mode_ignores_inherited_indexes_paths_and_pip_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://example.invalid/")
    monkeypatch.setenv("PYTHONPATH", "editable-source")
    house = tmp_path / "local wheels"
    env = packaging.pip_environment(tmp_path, house, False)
    assert env["PIP_NO_INDEX"] == "1" and env["PIP_FIND_LINKS"] == house.as_uri()
    assert "PIP_INDEX_URL" not in env and "PIP_EXTRA_INDEX_URL" not in env
    assert "PYTHONPATH" not in env and env["TMPDIR"] == str(tmp_path)
    online = packaging.pip_environment(tmp_path, house, True)
    assert online["PIP_INDEX_URL"] == "https://pypi.org/simple"
    assert "PIP_EXTRA_INDEX_URL" not in online and "PIP_NO_INDEX" not in online


def test_empty_wheelhouse_stops_before_build_or_install(tmp_path, monkeypatch):
    monkeypatch.setattr(packaging, "ROOT", tmp_path)
    monkeypatch.setattr(packaging, "require_repo_venv", lambda _: None)
    with pytest.raises(packaging.ValidationError, match="^wheelhouse_empty$"):
        packaging.validate(tmp_path / ".local/run", allow_pypi=False)
    assert not (tmp_path / ".local").exists()


def test_staging_uses_tracked_working_contents_and_skips_old_build_output(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_bytes(b"modified working copy")
    (project / "stale.egg-info").mkdir()
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs:
                        b"pyproject.toml\0deleted-file\0")
    target = tmp_path / "build-input"
    packaging.stage_project(project, target)
    assert (target / "pyproject.toml").read_bytes() == b"modified working copy"
    assert len(list(target.iterdir())) == 1


@pytest.mark.parametrize("failure", [None, "install", "probe", "digest"])
def test_only_a_successful_probe_for_this_wheel_produces_a_receipt(tmp_path, monkeypatch, failure):
    destination = tmp_path / ".local/packaging/example"
    monkeypatch.setattr(packaging, "ROOT", tmp_path)
    monkeypatch.setattr(packaging, "require_repo_venv", lambda _: None)
    monkeypatch.setattr(packaging, "stage_project", lambda *_: None)
    wheel = destination / "sentinelforge-0.2.0-py3-none-any.whl"
    calls = []

    def run(args, *, cwd, env, stdin, **kwargs):
        calls.append(args)
        assert cwd.is_relative_to(tmp_path / ".local") and stdin == subprocess.DEVNULL
        if "wheel" in args:
            wheel.write_bytes(b"build result fixture")
        is_probe = len(args) == 4 and args[1] == "-I" and args[-1] == wheel
        if (failure == "install" and "install" in args) or (failure == "probe" and is_probe):
            return subprocess.CompletedProcess(args, 1, b"failed")
        digest = hashlib.sha256(b"build result fixture").hexdigest()
        output = {"status": "passed", "wheel": wheel.name,
                  "sha256": "wrong" if failure == "digest" else digest}
        return subprocess.CompletedProcess(args, 0, json.dumps(output).encode())

    monkeypatch.setattr(subprocess, "run", run)
    if failure is None:
        receipt = packaging.validate(destination, allow_pypi=True)
        assert json.loads(receipt.read_bytes())["dependency_source"] == "pypi"
        assert len(calls) == 5
        assert calls[2][:4] == [sys.executable, "-m", "pip", "--python"]
        assert calls[-1][1] == "-I" and calls[-1][0] == calls[2][4]
    else:
        with pytest.raises(packaging.ValidationError):
            packaging.validate(destination, allow_pypi=True)
        assert not (destination / "receipt.json").exists()
        assert len(calls) == (3 if failure == "install" else 5)
