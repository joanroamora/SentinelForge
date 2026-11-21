"""Typer CLI adapter over the shared AnalysisService."""

from enum import Enum
from typing import Annotated, cast
from uuid import UUID

import typer
from pydantic import ValidationError

from .monitor import MonitorAnswerRequest, MonitorConflictError
from .service import AnalysisService
from .simulation import DemoFixtureId
from .workflow import WorkflowConflictError

app = typer.Typer(help="Herramientas locales de demostración de SentinelForge.")


class DemoFixtureOption(str, Enum):
    auth_disabled = "auth-disabled"
    auth_enabled = "auth-enabled"
    source_missing = "source-missing"


@app.callback()
def main() -> None:
    """CLI de SentinelForge AI."""


@app.command()
def demo() -> None:
    """Imprime un reporte ficticio; no analiza el proyecto actual."""
    report = AnalysisService().create_demo_analysis()
    typer.echo(report.model_dump_json(indent=2))


@app.command()
def workflow_start(
    fixture_id: Annotated[DemoFixtureOption, typer.Option()] = DemoFixtureOption.auth_disabled,
    monitored: Annotated[bool, typer.Option()] = False,
) -> None:
    """Inicia un ciclo simulado persistente; no ejecuta escáneres."""
    checkpoint = AnalysisService().create_demo_workflow(
        fixture_id=cast(DemoFixtureId, fixture_id.value), monitored=monitored
    )
    typer.echo(checkpoint.model_dump_json(indent=2))


@app.command()
def workflow_questions(analysis_id: str) -> None:
    """Lista preguntas persistentes sin esperar entrada interactiva."""
    try:
        questions = AnalysisService().get_monitor_questions(analysis_id)
    except LookupError as error:
        typer.echo("analysis_not_found", err=True)
        raise typer.Exit(code=2) from error
    typer.echo("[" + ",\n".join(question.model_dump_json(indent=2) for question in questions) + "]")


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
    typer.echo(receipt.model_dump_json(indent=2))


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
    typer.echo(simulation.model_dump_json(indent=2))


@app.command()
def workflow_status(analysis_id: str) -> None:
    """Consulta el último estado guardado de un ciclo simulado."""
    checkpoint = AnalysisService().get_workflow(analysis_id)
    if checkpoint is None:
        typer.echo("workflow_not_found", err=True)
        raise typer.Exit(code=2)
    typer.echo(checkpoint.model_dump_json(indent=2))


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
    typer.echo(checkpoint.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
