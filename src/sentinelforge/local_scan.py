"""A bounded local static observation, separate from the synthetic demo report."""

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from .contracts import Contract
from .local_source import (
    MAX_SOURCE_BYTES,
    LocalSourceError,
    load_local_source,
    normalize_source_label,
)

DETECTOR_VERSION = "1.8"
WORKER_TIMEOUT_SECONDS = 5
MAX_WORKER_OUTPUT_BYTES = 65536
LIMITATIONS = (
    "Solo inspecciona un archivo Python explícito; no analiza el proyecto completo.",
    ("SF-PY-001 observa shell=True literal en llamadas subprocess reconocidas; "
     "no confirma inyección de comandos ni explotabilidad."),
    ("No hay análisis de flujo de datos ni de alcance en ejecución. Los alias dinámicos, "
     "wrappers, valores calculados e imports no admitidos pueden quedar sin detectar."),
    "Alias asignados: hasta 8 capturas estables en módulo; en función solo un enlace directo a un import.",
    "Capturas anotadas: solo de módulo, con valor y anotación de nombre o texto; no comprueba tipos.",
    "Imports condicionales: solo if True directo del módulo, sin else y con cuerpo formado por imports.",
    "Cero señales significa que esta regla no encontró coincidencias, no que el archivo sea seguro.",
    ("No ejecuta ni importa el artefacto. El proceso del parser tiene tiempo límite, "
     "pero no es un sandbox de permisos ni impone una cuota dura de memoria."),
    "El detector no verifica contexto humano ni confirma vulnerabilidades.",
)


class LocalSourceManifest(Contract):
    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0, le=65536, strict=True)


class LocalScanSignal(Contract):
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule_id: Literal["SF-PY-001"] = "SF-PY-001"
    severity: Literal["warning"] = "warning"
    verification_status: Literal["unverified"] = "unverified"
    message: str = "Uso explícito de shell=True; requiere revisión del origen del comando."
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    line: int = Field(ge=1, strict=True)
    column: int = Field(ge=1, strict=True)
    end_line: int = Field(ge=1, strict=True)
    end_column: int = Field(ge=1, strict=True)
    call: Literal[
        "subprocess.run", "subprocess.Popen", "subprocess.call",
        "subprocess.check_call", "subprocess.check_output",
    ]


class LocalScanError(Contract):
    code: str
    message: str = "No se completó la inspección; este error no es una alerta de seguridad."


class LocalScanReport(Contract):
    schema_version: Literal["1.0"] = "1.0"
    report_type: Literal["local_python_scan"] = "local_python_scan"
    is_demo: Literal[False] = False
    detector: Literal["sentinelforge-python-ast"] = "sentinelforge-python-ast"
    detector_version: Literal["1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8"] = DETECTOR_VERSION
    python_version: str = Field(default_factory=platform.python_version)
    rules: list[Literal["SF-PY-001"]] = Field(default_factory=lambda: ["SF-PY-001"])
    status: Literal["COMPLETED", "ERROR"]
    scan_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source: LocalSourceManifest | None = None
    signals: list[LocalScanSignal] = Field(default_factory=list)
    errors: list[LocalScanError] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=lambda: list(LIMITATIONS))

    @model_validator(mode="after")
    def outcome_is_consistent(self) -> Self:
        if self.status == "COMPLETED" and (self.source is None or self.errors):
            raise ValueError("completed_scan_requires_source_without_errors")
        if self.status == "ERROR" and (not self.errors or self.signals):
            raise ValueError("failed_scan_requires_errors_without_signals")
        if (self.source is None) != (self.scan_fingerprint is None):
            raise ValueError("scan_fingerprint_requires_source")
        if any(self.source is None or item.source_sha256 != self.source.sha256
               for item in self.signals):
            raise ValueError("signal_source_mismatch")
        return self


class _WorkerSignal(Contract):
    line: int = Field(ge=1, strict=True)
    column: int = Field(ge=1, strict=True)
    end_line: int = Field(ge=1, strict=True)
    end_column: int = Field(ge=1, strict=True)
    call: Literal[
        "subprocess.run", "subprocess.Popen", "subprocess.call",
        "subprocess.check_call", "subprocess.check_output",
    ]


class _WorkerResult(Contract):
    signals: list[_WorkerSignal] = Field(max_length=100)
    error: Literal[
        "source_too_large", "invalid_encoding", "invalid_python",
        "source_too_complex", "too_many_findings",
    ] | None


def _fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def scan_local_file(root: Path, relative_path: str) -> LocalScanReport:
    """Read one explicit file and run only our trusted parser in a child process."""
    try:
        label, content = load_local_source(root, relative_path)
    except LocalSourceError as error:
        return LocalScanReport(status="ERROR", errors=[LocalScanError(code=error.code)])
    return scan_source_bytes(label, content)


def scan_source_bytes(label: str, content: bytes) -> LocalScanReport:
    """Same detector for selected browser bytes and local files; never open the label."""
    try:
        label = normalize_source_label(label)
    except LocalSourceError as error:
        return LocalScanReport(status="ERROR", errors=[LocalScanError(code=error.code)])
    if len(content) > MAX_SOURCE_BYTES:
        return LocalScanReport(status="ERROR", errors=[LocalScanError(code="source_too_large")])

    source = LocalSourceManifest(
        relative_path=label, sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)
    )
    fingerprint = _fingerprint([
        DETECTOR_VERSION, platform.python_version(), "SF-PY-001", source.model_dump(),
    ])

    def failed(code: str) -> LocalScanReport:
        return LocalScanReport(
            status="ERROR", source=source, scan_fingerprint=fingerprint,
            errors=[LocalScanError(code=code)],
        )

    try:
        process = subprocess.run(
            [sys.executable, "-I", "-S", str(Path(__file__).with_name("_scan_worker.py"))],
            input=content, capture_output=True, timeout=WORKER_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        return failed("parser_timeout")
    except OSError:
        return failed("parser_unavailable")
    if process.returncode != 0:
        return failed("parser_failed")
    if len(process.stdout) > MAX_WORKER_OUTPUT_BYTES:
        return failed("parser_invalid_output")
    try:
        result = _WorkerResult.model_validate_json(process.stdout)
    except (ValidationError, ValueError):
        return failed("parser_invalid_output")
    if result.error is not None:
        return failed(result.error)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        return failed("parser_invalid_output")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    signals = []
    for observed in result.signals:
        # Validate the location against the same immutable bytes sent to the parser.
        if (observed.end_line < observed.line or observed.end_line > len(lines)
                or observed.line > len(lines)
                or observed.column > len(lines[observed.line - 1].encode("utf-8")) + 1
                or observed.end_column > len(lines[observed.end_line - 1].encode("utf-8")) + 1
                or (observed.line == observed.end_line
                    and observed.end_column <= observed.column)):
            return failed("parser_invalid_output")
        signals.append(LocalScanSignal(
            fingerprint=_fingerprint([fingerprint, observed.model_dump()]),
            source_sha256=source.sha256, **observed.model_dump(),
        ))
    return LocalScanReport(
        status="COMPLETED", source=source, scan_fingerprint=fingerprint, signals=signals,
    )
