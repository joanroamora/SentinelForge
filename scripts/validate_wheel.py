"""Build our tracked project and smoke-test its wheel in a disposable local venv."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from scripts.validate_local import ROOT, ValidationError, require_repo_venv


def stage_project(root: Path, target: Path) -> None:
    """Build the working copies of tracked files, without stale build/ or egg-info."""
    names = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=root)
    for name in names.split(b"\0"):
        if not name:
            continue
        relative = Path(os.fsdecode(name))
        source = root / relative
        if source.resolve() != source or not source.is_relative_to(root):
            raise ValidationError("wheel_build_input_outside_checkout")
        if source.is_file():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def pip_environment(scratch: Path, wheelhouse: Path, allow_pypi: bool) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("PIP_", "PYTHON", "VIRTUAL_ENV"))}
    env.update(TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch),
               PIP_CONFIG_FILE=os.devnull, PIP_NO_INPUT="1", PIP_NO_CACHE_DIR="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONNOUSERSITE="1", PIP_ONLY_BINARY=":all:")
    if allow_pypi:
        env["PIP_INDEX_URL"] = "https://pypi.org/simple"
    else:
        env.update(PIP_NO_INDEX="1", PIP_FIND_LINKS=wheelhouse.as_uri())
    return env


def validate(destination: Path, *, allow_pypi: bool) -> Path:
    require_repo_venv(ROOT)
    local = (ROOT / ".local").resolve()
    wheelhouse = local / "wheels"
    if (ROOT not in local.parents or local not in destination.resolve().parents
            or wheelhouse.resolve() != wheelhouse):
        raise ValidationError("wheel_requires_local_paths")
    if not allow_pypi and not any(wheelhouse.glob("*.whl")):
        raise ValidationError("wheelhouse_empty")
    destination.mkdir(parents=True, exist_ok=False)
    print(f"Evidencia: {destination.relative_to(ROOT).as_posix()}", flush=True)
    with tempfile.TemporaryDirectory(dir=local, prefix="wheel-") as scratch_name:
        scratch = Path(scratch_name)
        env = pip_environment(scratch, wheelhouse, allow_pypi)
        project, consumer = scratch / "project", scratch / "venv"
        stage_project(ROOT, project)

        def run(step: str, command: Sequence[str | Path], timeout: int = 180) -> bytes:
            print(step, flush=True)
            with (destination / f"{step}.stderr.log").open("xb") as errors:
                result = subprocess.run(command, cwd=scratch, env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=errors, timeout=timeout,
                                        check=False)
            (destination / f"{step}.log").write_bytes(result.stdout)
            if result.returncode:
                raise ValidationError(f"wheel_step_failed_{step}")
            return result.stdout

        pip = [sys.executable, "-m", "pip"]
        run("build", [*pip, "wheel", "--no-deps", "--wheel-dir", destination, project])
        wheels = list(destination.glob("sentinelforge-*.whl"))
        if len(wheels) != 1:
            raise ValidationError("wheel_build_output_mismatch")
        run("environment", [sys.executable, "-I", "-m", "venv", "--without-pip", consumer])
        python = consumer / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        consumer_pip = [*pip, "--python", python]
        run("install", [*consumer_pip, "install", wheels[0]])
        run("dependencies", [*consumer_pip, "check"])
        raw = run("smoke", [python, "-I", ROOT / "scripts/check_installed_wheel.py", wheels[0]], 330)
        receipt = json.loads(raw)
        with wheels[0].open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if (not isinstance(receipt, dict) or receipt.get("status") != "passed"
                or receipt.get("sha256") != digest or receipt.get("wheel") != wheels[0].name):
            raise ValidationError("wheel_smoke_receipt_mismatch")
        receipt["dependency_source"] = "pypi" if allow_pypi else "local_wheelhouse"
    path = destination / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-pypi", action="store_true",
                        help="Permite descargar dependencias desde PyPI para esta prueba.")
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / ".local/packaging" / f"{stamp}-{uuid4().hex[:8]}"
    try:
        path = validate(destination, allow_pypi=args.allow_pypi)
    except ValidationError as error:
        print(error, file=sys.stderr)
    except (OSError, ValueError, subprocess.SubprocessError):
        print("wheel_validation_incomplete", file=sys.stderr)
    else:
        print(path.relative_to(ROOT).as_posix())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
