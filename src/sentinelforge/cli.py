"""Typer CLI adapter over the shared AnalysisService."""

import typer

from .service import AnalysisService
from .workflow import WorkflowConflictError

app = typer.Typer(help="Herramientas locales de demostración de SentinelForge.")


@app.callback()
def main() -> None:
    """CLI de SentinelForge AI."""


@app.command()
def demo() -> None:
    """Imprime un reporte ficticio; no analiza el proyecto actual."""
    report = AnalysisService().create_demo_analysis()
    typer.echo(report.model_dump_json(indent=2))


@app.command()
def workflow_start() -> None:
    """Inicia un ciclo simulado persistente; no ejecuta escáneres."""
    checkpoint = AnalysisService().create_demo_workflow()
    typer.echo(checkpoint.model_dump_json(indent=2))


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
