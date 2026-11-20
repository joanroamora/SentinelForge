"""Typer CLI adapter over the shared AnalysisService."""

import typer

from .service import AnalysisService

app = typer.Typer(help="Herramientas locales de demostración de SentinelForge.")


@app.callback()
def main() -> None:
    """CLI de SentinelForge AI."""


@app.command()
def demo() -> None:
    """Imprime un reporte ficticio; no analiza el proyecto actual."""
    report = AnalysisService().create_demo_analysis()
    typer.echo(report.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
