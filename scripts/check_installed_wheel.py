"""Smoke-test the project's own wheel from a separate local Python environment."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
from importlib import metadata, util
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class WheelCheckError(ValueError):
    """A short diagnostic suitable for the command's standard error."""


def check_environment() -> Path:
    prefix = Path(sys.prefix).resolve()
    local = (ROOT / ".local").resolve()
    if (not sys.flags.isolated or sys.prefix == sys.base_prefix
            or not local.is_relative_to(ROOT) or local not in prefix.parents):
        raise WheelCheckError("wheel_requires_isolated_local_environment")
    settings = {}
    for line in (prefix / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        settings[key.strip().lower()] = value.strip().lower()
    if settings.get("include-system-site-packages") != "false":
        raise WheelCheckError("wheel_requires_private_site_packages")
    site = Path(sysconfig.get_path("purelib")).resolve()
    if not site.is_relative_to(prefix):
        raise WheelCheckError("wheel_site_outside_environment")
    return site


def check_origin(dist: metadata.Distribution, wheel: Path) -> str:
    if wheel.suffix != ".whl" or not wheel.is_relative_to(ROOT) or not wheel.is_file():
        raise WheelCheckError("wheel_requires_local_file")
    with wheel.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    origin = json.loads(dist.read_text("direct_url.json") or "{}")
    archive = origin.get("archive_info") if isinstance(origin, dict) else None
    hashes = archive.get("hashes") if isinstance(archive, dict) else None
    if (not isinstance(hashes, dict) or hashes.get("sha256") != digest
            or not isinstance(origin.get("url"), str) or urlsplit(origin["url"]).scheme != "file"
            or "dir_info" in origin):
        raise WheelCheckError("wheel_installed_archive_mismatch")
    return digest


def check_payload(source: Path, installed: Path, files: list[metadata.PackagePath]) -> int:
    patterns = ("**/*.py", "data/*.json", "static/*.html", "static/*.css", "static/*.js")
    expected = {path.relative_to(source) for pattern in patterns for path in source.glob(pattern)}
    recorded = {Path(*path.parts[1:]) for path in files if path.parts[0] == "sentinelforge"
                and not ("__pycache__" in path.parts and path.suffix == ".pyc")}
    if not expected or recorded != expected:
        raise WheelCheckError("wheel_payload_inventory_mismatch")
    for name in expected:
        shipped = (installed / name).resolve()
        if (not shipped.is_relative_to(installed) or not shipped.is_file()
                or shipped.read_bytes() != (source / name).read_bytes()):
            raise WheelCheckError("wheel_payload_content_mismatch")
    return len(expected)


def check_cli(executable: Path, work: Path) -> dict:
    from sentinelforge.evaluation import _engine_digest, load_builtin_corpus
    from sentinelforge.evaluation_contracts import BuiltinCorpus, EvaluationReport

    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("PYTHON")}
    environment.update(PYTHONNOUSERSITE="1", PYTHONSAFEPATH="1",
                       SENTINELFORGE_DATABASE_PATH=str(work / "smoke.sqlite3"))
    summaries = {}
    for selection in BuiltinCorpus:
        corpus = load_builtin_corpus(selection)
        result = subprocess.run(
            [str(executable), "--no-animation", "evaluate", "--corpus", selection.value,
             "--format", "json"], cwd=work, env=environment, stdin=subprocess.DEVNULL,
            capture_output=True, check=False, timeout=150)
        if result.returncode:
            raise WheelCheckError(f"wheel_cli_{selection.value}_failed")
        report = EvaluationReport.model_validate_json(result.stdout)
        if (report.status != "COMPLETED" or report.acceptance != "pass"
                or report.corpus_id != corpus.id or report.engine_sha256 != _engine_digest()
                or [case.id for case in report.cases] != [case.id for case in corpus.cases]):
            raise WheelCheckError("wheel_cli_report_mismatch")
        summaries[selection.value] = len(report.cases)
    return summaries


def check(wheel: Path) -> dict:
    site = check_environment()
    dist = metadata.distribution("sentinelforge")
    digest = check_origin(dist, wheel.resolve())
    installed = site / "sentinelforge"
    spec = util.find_spec("sentinelforge")
    if (installed.resolve() != installed or not spec or not spec.origin
            or Path(spec.origin).resolve() != installed / "__init__.py"
            or Path(dist.locate_file("sentinelforge")).resolve() != installed):
        raise WheelCheckError("wheel_import_outside_installation")
    count = check_payload(ROOT / "src/sentinelforge", installed, list(dist.files or []))

    from sentinelforge import __version__
    from sentinelforge.api import app

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if (dist.version, __version__, app.openapi()["info"]["version"]) != (project["version"],) * 3:
        raise WheelCheckError("wheel_version_mismatch")
    scripts = Path(sysconfig.get_path("scripts"))
    executable = scripts / ("sentinelforge.exe" if os.name == "nt" else "sentinelforge")
    with tempfile.TemporaryDirectory(dir=Path(sys.prefix).parent) as temporary:
        summaries = check_cli(executable, Path(temporary))
    return {"schema_version": "1.0", "status": "passed", "wheel": wheel.name, "sha256": digest,
            "version": dist.version, "python": sys.version.split()[0],
            "package_files_checked": count, "cli_cases": summaries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="Wheel local construido desde este repositorio.")
    args = parser.parse_args()
    try:
        result = check(args.wheel)
    except WheelCheckError as error:
        print(error, file=sys.stderr)
    except (OSError, ValueError, ImportError, subprocess.SubprocessError):
        print("wheel_check_incomplete", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
