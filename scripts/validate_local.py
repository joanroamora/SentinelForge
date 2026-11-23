"""Local quality gate: existing repo .venv only, no installation or publication."""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CHECKS = (
    ("ruff", ("-m", "ruff", "check", "."), 60),
    ("pytest", ("-m", "pytest", "-q"), 600),
    ("baseline", ("-m", "sentinelforge.cli", "--no-animation", "evaluate",
                  "--corpus", "baseline", "--format", "json"), 150),
    ("challenge", ("-m", "sentinelforge.cli", "--no-animation", "evaluate",
                   "--corpus", "challenge", "--format", "json"), 150),
)
LIMITATIONS = [
    "Comprueba el checkout local; no equivale a CI remota ni autoriza publicar.",
    "Los dos corpus son sintéticos de desarrollo, sin auditoría independiente.",
    "No construye ni valida un wheel; no prueba una instalación limpia.",
    "Las huellas no son firmas y solo comparan capturas al inicio y al final.",
]


class ValidationError(ValueError):
    """A stable diagnostic without source contents or parser internals."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def require_repo_venv(root: Path) -> None:
    expected = root / ".venv"
    interpreter = expected / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if (Path(sys.prefix).resolve() != expected.resolve() or sys.prefix == sys.base_prefix
            or Path(sys.executable).resolve() != interpreter.resolve()):
        raise ValidationError("validation_requires_repo_venv")


def source_digest(root: Path) -> str:
    """Fingerprint product, tests, configuration and this gate; exclude generated files."""
    files = [root / "pyproject.toml", root / "scripts/validate_local.py"]
    for folder in ("src/sentinelforge", "tests", ".github/workflows"):
        files.extend(path for path in (root / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts
                     and path.suffix not in {".pyc", ".pyo"})
    hashes = {}
    for path in sorted(files):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValidationError("validation_source_outside_repository")
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(raw).hexdigest()
    canonical = json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def run_command(command: list[str], root: Path, destination: Path, timeout: int) -> int:
    with destination.open("xb") as output, destination.with_suffix(".stderr.log").open("xb") as err:
        result = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=err, timeout=timeout, check=False)
    return result.returncode


def inspect_evaluation(path: Path, selection: str, engine: str) -> dict:
    # Imported only after require_repo_venv, from the same application used by the CLI.
    from sentinelforge.evaluation import _digest, load_builtin_corpus, summarize
    from sentinelforge.evaluation_contracts import BuiltinCorpus, EvaluationReport

    with path.open("rb") as handle:
        raw = handle.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValidationError("validation_evaluation_too_large")
    try:
        report = EvaluationReport.model_validate_json(raw)
    except ValueError:
        raise ValidationError("validation_evaluation_invalid") from None
    corpus = load_builtin_corpus(BuiltinCorpus(selection))
    if (report.corpus_id != corpus.id or report.corpus_version != corpus.version
            or report.corpus_sha256 != _digest(corpus.model_dump())
            or report.engine_sha256 != engine
            or [case.id for case in report.cases] != [case.id for case in corpus.cases]):
        raise ValidationError("validation_evaluation_identity_mismatch")
    for result, reference in zip(report.cases, corpus.cases, strict=True):
        if (result.scope != reference.scope or result.expected_error != reference.expected_error
                or result.source_sha256 != hashlib.sha256(reference.source.encode("utf-8")).hexdigest()
                or [target.expected for target in result.targets] != reference.expected_signals):
            raise ValidationError("validation_evaluation_identity_mismatch")
    for group in ("all", "in_scope", "boundary", "input_error"):
        cases = report.cases if group == "all" else [
            case for case in report.cases if case.scope == group]
        if report.groups.get(group) != summarize(cases):
            raise ValidationError("validation_evaluation_metrics_mismatch")
    if (report.status != "COMPLETED" or report.acceptance != "pass"
            or report.reference_failures or report.groups["all"].technical_errors
            or any(case.scan_status == "NOT_RUN" or case.technical_error
                   or case.scope != "boundary" and not case.reference_match
                   for case in report.cases)
            or report.boundary_gaps != [case.id for case in report.cases
                                       if case.scope == "boundary" and not case.reference_match]):
        raise ValidationError("validation_evaluation_not_passed")
    total = report.groups["all"]
    return {
        "corpus_id": report.corpus_id, "corpus_sha256": report.corpus_sha256,
        "engine_sha256": report.engine_sha256, "detector_version": report.detector_version,
        "reference_review": report.reference_review, "cases": len(report.cases),
        "signals_matched": total.localization.matched,
        "signals_missed": total.localization.missed,
        "inconclusive_traces": total.tracing.inconclusive,
        "boundary_gaps": report.boundary_gaps,
        "report_sha256": hashlib.sha256(raw).hexdigest(),
    }


def validate(root: Path, destination: Path, *, runner=run_command,
             fingerprint=source_digest, engine_digest=None) -> dict:
    """Fail closed; preserve completed evidence and mark later checks as not run."""
    from sentinelforge.evaluation import _engine_digest

    digest = engine_digest or _engine_digest
    manifest = {
        "schema_version": "1.0", "report_type": "local_quality_gate",
        "started_at": utc_now(), "finished_at": None, "status": "error", "exit_code": 2,
        "python_version": sys.version.split()[0], "is_independent_audit": False,
        "wheel_verified": False, "remote_ci_verified": False,
        "source_sha256_before": None, "source_sha256_after": None,
        "engine_sha256": None, "error_code": None, "evaluations": {},
        "checks": [{"id": name, "status": "not_run", "exit_code": None}
                   for name, _, _ in CHECKS],
        "limitations": LIMITATIONS,
    }
    if not destination.resolve().is_relative_to(root.resolve()):
        raise ValidationError("validation_evidence_outside_repository")
    destination.mkdir(parents=True, exist_ok=False)
    try:
        manifest["source_sha256_before"] = fingerprint(root)
        manifest["engine_sha256"] = digest()
        for check, (name, arguments, timeout) in zip(manifest["checks"], CHECKS, strict=True):
            print(f"Validando {name}…", flush=True)
            output = destination / f"{name}.{'json' if name in {'baseline', 'challenge'} else 'log'}"
            check.update(status="running", stdout=output.name,
                         stderr=output.with_suffix(".stderr.log").name)
            start = time.perf_counter()
            try:
                code = runner([sys.executable, *arguments], root, output, timeout)
            except subprocess.TimeoutExpired:
                check.update(status="error", error_code="validation_check_timeout")
                raise ValidationError("validation_check_timeout") from None
            finally:
                check["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
            check.update(exit_code=code, status="passed" if code == 0 else "failed")
            if code != 0:
                manifest.update(status="failed" if code == 1 else "error",
                                exit_code=1 if code == 1 else 2,
                                error_code="validation_check_failed")
                break
            if name in {"baseline", "challenge"}:
                try:
                    manifest["evaluations"][name] = inspect_evaluation(
                        output, name, manifest["engine_sha256"])
                except (OSError, ValueError):
                    check["status"] = "error"
                    raise
        else:
            manifest.update(status="passed", exit_code=0)
    except (OSError, ValueError) as error:
        for check in manifest["checks"]:
            if check["status"] == "running":
                check["status"] = "error"
        manifest.update(status="error", exit_code=2,
                        error_code=str(error) if isinstance(error, ValidationError)
                        else "validation_evidence_unavailable")
    except KeyboardInterrupt:
        for check in manifest["checks"]:
            if check["status"] == "running":
                check["status"] = "interrupted"
        manifest.update(status="interrupted", exit_code=130, error_code="validation_interrupted")
    finally:
        try:
            manifest["source_sha256_after"] = fingerprint(root)
            if (manifest["source_sha256_before"] != manifest["source_sha256_after"]
                    or manifest["engine_sha256"] != digest()):
                manifest.update(status="error", exit_code=2, error_code="validation_sources_changed")
        except (OSError, ValueError):
            manifest.update(status="error", exit_code=2, error_code="validation_snapshot_unavailable")
        manifest["finished_at"] = utc_now()
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    try:
        require_repo_venv(ROOT)
        if len(sys.argv) != 1:
            raise ValidationError("validation_unexpected_arguments")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = ROOT / ".local/validation" / f"{stamp}-{uuid4().hex[:8]}"
        manifest = validate(ROOT, destination)
    except (OSError, ValueError) as error:
        print(str(error) if isinstance(error, ValidationError)
              else "validation_evidence_unavailable", file=sys.stderr)
        return 2
    print(f"Resultado: {manifest['status']} ({manifest['exit_code']})")
    print(f"Evidencia: {destination.relative_to(ROOT).as_posix()}/manifest.json")
    if manifest["error_code"]:
        print(manifest["error_code"], file=sys.stderr)
        for check in manifest["checks"]:
            if check["status"] not in {"failed", "error"}:
                continue
            for field in ("stdout", "stderr"):
                path = destination / check[field]
                if path.is_file():
                    with path.open("rb") as handle:
                        handle.seek(max(0, path.stat().st_size - 4096))
                        print(handle.read(4096).decode("utf-8", errors="replace"), file=sys.stderr)
    return manifest["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
