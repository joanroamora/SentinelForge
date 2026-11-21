"""Typer CLI adapter over the shared AnalysisService."""

from enum import Enum
from typing import Annotated, cast
from uuid import UUID

import typer
from pydantic import ValidationError

from .monitor import MonitorAnswerRequest, MonitorConflictError
from .service import AnalysisService
from .simulation import DemoFixtureId
from .terminal import OUTPUT_FORMAT, OutputFormat, console, emit, human_output
from .terminal_logo import ANIMATION_ENABLED, show_logo
from .workflow import WorkflowConflictError

app = typer.Typer(help="Demo y análisis estático local acotado de SentinelForge.",
                  pretty_exceptions_show_locals=False)


class DemoFixtureOption(str, Enum):
    auth_disabled = "auth-disabled"
    auth_enabled = "auth-enabled"
    source_missing = "source-missing"


@app.callback()
def main(output: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.auto,
         no_animation: Annotated[bool, typer.Option("--no-animation")] = False) -> None:
    """CLI de SentinelForge AI."""
    OUTPUT_FORMAT.set(output)
    ANIMATION_ENABLED.set(not no_animation)


@app.command()
def logo(seconds: Annotated[float, typer.Option(min=0.1, max=30)] = 6,
         output: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.auto) -> None:
    """Muestra el emblema SF 3D girando sobre el eje vertical; no ejecuta análisis."""
    if not human_output(output):
        emit({"logo": "SF", "axis": "Y", "animation": False}, OutputFormat.json)
        return
    term = console()
    try:
        show_logo(term, seconds=seconds)
    except KeyboardInterrupt as error:
        raise typer.Exit(code=130) from error
    term.print(" SENTINELFORGE / LOCAL WORKSPACE", style="bold cyan")


@app.command()
def scan_file(file: str, output: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.auto) -> None:
    """Inspecciona un .py relativo al directorio actual sin ejecutar su código."""
    report = AnalysisService().scan_local_file(file)
    emit(report, output)
    if report.status == "ERROR":
        raise typer.Exit(code=2)


@app.command()
def scan(file: str, output: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.auto) -> None:
    """Analiza un .py y guarda un expediente local recuperable."""
    try:
        if human_output(output):
            with console().status("Inspeccionando archivo y guardando expediente…", spinner="dots"):
                case = AnalysisService().create_local_scan(file)
        else:
            case = AnalysisService().create_local_scan(file)
    except ValueError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    emit(case, output)
    if case.status == "ERROR":
        raise typer.Exit(code=2)


@app.command()
def scans(limit: Annotated[int, typer.Option(min=1, max=100)] = 25,
          offset: Annotated[int, typer.Option(min=0)] = 0,
          output: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.auto) -> None:
    """Lista expedientes reales guardados en esta base local."""
    emit(AnalysisService().list_local_scans(limit=limit, offset=offset), output)


@app.command()
def scan_report(analysis_id: str, revision: Annotated[int | None, typer.Option(min=1)] = None,
                output: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.auto) -> None:
    """Recupera la última revisión o una revisión histórica de un expediente real."""
    case = AnalysisService().get_local_scan(analysis_id, revision)
    if case is None:
        typer.echo("local_scan_not_found", err=True)
        raise typer.Exit(code=2)
    emit(case, output)


@app.command()
def scan_answer(analysis_id: str, submission_id: Annotated[UUID, typer.Option()],
                actor: Annotated[str, typer.Option()], role: Annotated[str, typer.Option()],
                text: Annotated[str, typer.Option()]) -> None:
    """Guarda una respuesta humana sin verificar; nunca espera stdin."""
    try:
        receipt = AnalysisService().answer_local_scan(analysis_id, MonitorAnswerRequest(
            submission_id=submission_id, actor=actor, role=role, text=text))
    except (ValidationError, LookupError, MonitorConflictError) as error:
        typer.echo("invalid_monitor_answer" if isinstance(error, ValidationError) else str(error), err=True)
        raise typer.Exit(code=2) from error
    emit(receipt)


@app.command()
def demo() -> None:
    """Imprime un reporte ficticio; no analiza el proyecto actual."""
    report = AnalysisService().create_demo_analysis()
    emit(report)


@app.command()
def workflow_start(
    fixture_id: Annotated[DemoFixtureOption, typer.Option()] = DemoFixtureOption.auth_disabled,
    monitored: Annotated[bool, typer.Option()] = False,
) -> None:
    """Inicia un ciclo simulado persistente; no ejecuta escáneres."""
    checkpoint = AnalysisService().create_demo_workflow(
        fixture_id=cast(DemoFixtureId, fixture_id.value), monitored=monitored
    )
    emit(checkpoint)


@app.command()
def workflow_questions(analysis_id: str) -> None:
    """Lista preguntas persistentes sin esperar entrada interactiva."""
    try:
        questions = AnalysisService().get_monitor_questions(analysis_id)
    except LookupError as error:
        typer.echo("analysis_not_found", err=True)
        raise typer.Exit(code=2) from error
    emit(questions)


@app.command()
def workflow_answer(
    analysis_id: str,
    question_id: str,
    submission_id: Annotated[UUID, typer.Option()],
    actor: Annotated[str, typer.Option()],
    role: Annotated[str, typer.Option()],
    text: Annotated[str, typer.Option()],
) -> None:
    """Registra una declaración humana sin promoverla a evidencia confirmada."""
    try:
        request = MonitorAnswerRequest(
            submission_id=submission_id, actor=actor, role=role, text=text
        )
        receipt = AnalysisService().answer_monitor_question(analysis_id, question_id, request)
    except ValidationError as error:
        typer.echo("invalid_monitor_answer", err=True)
        raise typer.Exit(code=2) from error
    except LookupError as error:
        typer.echo("monitor_question_not_found", err=True)
        raise typer.Exit(code=2) from error
    except MonitorConflictError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=2) from error
    emit(receipt)


@app.command()
def workflow_investigation(
    analysis_id: str,
    checkpoint_version: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Consulta señal, hipótesis y verificación simuladas de un ciclo."""
    simulation = AnalysisService().get_simulation(
        analysis_id, checkpoint_version=checkpoint_version
    )
    if simulation is None:
        typer.echo("simulation_not_found", err=True)
        raise typer.Exit(code=2)
    emit(simulation)


@app.command()
def workflow_status(analysis_id: str) -> None:
    """Consulta el último estado guardado de un ciclo simulado."""
    checkpoint = AnalysisService().get_workflow(analysis_id)
    if checkpoint is None:
        typer.echo("workflow_not_found", err=True)
        raise typer.Exit(code=2)
    emit(checkpoint)


@app.command()
def workflow_advance(
    analysis_id: str,
    expected_version: int = typer.Option(..., min=1),
) -> None:
    """Avanza una fase; reintentar la misma versión conserva su resultado."""
    try:
        checkpoint = AnalysisService().advance_demo_workflow(
            analysis_id, expected_version=expected_version
        )
    except LookupError as error:
        typer.echo("workflow_not_found", err=True)
        raise typer.Exit(code=2) from error
    except WorkflowConflictError as error:
        typer.echo("workflow_version_conflict", err=True)
        raise typer.Exit(code=2) from error
    emit(checkpoint)


if __name__ == "__main__":
    app()
