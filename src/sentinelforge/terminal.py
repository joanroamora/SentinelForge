"""Human terminal rendering with an explicit, machine-readable JSON mode."""

import json
import os
import sys
import unicodedata
from contextvars import ContextVar
from enum import Enum

import typer
from pydantic import BaseModel
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from .terminal_logo import show_logo


class OutputFormat(str, Enum):
    auto = "auto"
    json = "json"
    pretty = "pretty"


OUTPUT_FORMAT: ContextVar[OutputFormat] = ContextVar("output_format", default=OutputFormat.auto)


def human_output(override: OutputFormat = OutputFormat.auto) -> bool:
    selected = OUTPUT_FORMAT.get() if override == OutputFormat.auto else override
    return selected == OutputFormat.pretty or (selected == OutputFormat.auto and sys.stdout.isatty())


def console() -> Console:
    return Console(markup=False, highlight=False, emoji=False, safe_box=True,
                   force_terminal=False if "NO_COLOR" in os.environ else None)


def safe_text(value: object) -> str:
    # Source labels and human context must never inject ANSI/OSC terminal commands or Rich markup.
    text = "".join(char for char in str(value)
                   if char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cf", "Cs"})
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="backslashreplace").decode(encoding)


def payload(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [payload(item) for item in value]
    return value


def emit(value, output: OutputFormat = OutputFormat.auto) -> None:
    data = payload(value)
    if not human_output(output):
        typer.echo(json.dumps(data, ensure_ascii=True, indent=2))
        return
    term = console()
    term.print()
    show_logo(term)
    term.print(Text(" SENTINELFORGE  /  LOCAL WORKSPACE", style="bold cyan"))
    term.print(Text(" Evidencia antes que opinión.\n", style="dim"))
    if isinstance(data, list) and all(isinstance(item, dict) and "report" in item for item in data):
        table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold cyan")
        for column in ("Expediente", "Archivo", "Señales", "Estado", "Rev."):
            table.add_column(column, overflow="fold")
        for item in data:
            table.add_row(item["id"][5:17], safe_text(item["report"]["source"]["relative_path"]),
                          str(len(item["report"]["signals"])), item["status"], str(item["revision"]))
        term.print(Panel(table, title="Expedientes guardados · esta página", border_style="#24465c"))
        if not data:
            term.print(" No hay expedientes. Empieza con: sentinelforge scan archivo.py")
    elif isinstance(data, dict) and data.get("report_type") in {"local_scan_case", "local_python_scan"}:
        report = data.get("report", data)
        source = report["source"]
        state = data["status"]
        style = "red" if state == "ERROR" else "yellow" if report["signals"] else "cyan"
        info = Table.grid(padding=(0, 3)); info.add_column(style="dim"); info.add_column(overflow="fold")
        info.add_row("Archivo", safe_text(source["relative_path"]) if source else "Entrada rechazada")
        info.add_row("Estado", Text(state, style=style))
        info.add_row("Alcance", "1 archivo · SF-PY-001 · sin ejecución")
        info.add_row("Señales", str(len(report["signals"])))
        if source:
            info.add_row("Tamaño", f"{source['size_bytes']:,} bytes / 65,536 máximo")
            info.add_row("SHA-256", source["sha256"])
        if data.get("id"):
            info.add_row("Expediente", data["id"])
            info.add_row("Revisión", str(data["revision"]))
        term.print(Panel(info, title="Análisis estático local", border_style=style, padding=(1, 2)))
        if source:
            term.print(Panel(Group(Text("Uso del límite de entrada · bytes", style="dim"),
                                   ProgressBar(total=65536, completed=source["size_bytes"],
                                               width=44, complete_style="cyan")),
                             border_style="#24465c"))
        table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold cyan")
        for column in ("Regla", "Llamada", "Ubicación", "Verificación"):
            table.add_column(column)
        for signal in report["signals"]:
            table.add_row(signal["rule_id"], signal["call"],
                          f"{signal['line']}:{signal['column']} -> {signal['end_line']}:{signal['end_column']}",
                          Text("sin verificar", style="yellow"))
        if report["signals"]:
            term.print(table)
        if data.get("source_review"):
            review = data["source_review"]
            labels = {"pattern_reproduced": "Patrón reproducido", "not_reproduced": "No reproducido",
                      "inconclusive": "Inconcluso"}
            checked = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan", expand=True)
            for column in ("Señal", "Corroboración", "Motivo"):
                checked.add_column(column, overflow="fold")
            for decision in review["decisions"]:
                checked.add_row(decision["signal_fingerprint"][:12], labels[decision["result"]],
                                decision["reason"])
            term.print(Panel(checked, title="Fuente original · hash coincidente", border_style="cyan"))
            term.print(Text(" Solo patrón estático. Riesgo y declaraciones humanas sin verificar.", style="dim"))
        for error in report["errors"]:
            term.print(Panel(Text(error["code"] + "\n" + error["message"]), border_style="red"))
        if data.get("question"):
            question = data["question"]
            texts = [Text(safe_text(question["prompt"])), Text("Estado: " + question["status"], style="dim")]
            for statement in data["human_statements"]:
                texts.extend([Text(safe_text(statement["text"])),
                              Text(safe_text(statement["actor"] + " · " + statement["role"]) +
                                   " · unverified", style="dim")])
            term.print(Panel(Group(*texts), title="Contexto humano", border_style="#8270c4"))
        term.print(Text(" Cero señales no garantiza seguridad. Las coincidencias requieren revisión.",
                        style="dim"))
    else:
        term.print(Panel(Text(safe_text(json.dumps(data, ensure_ascii=False, indent=2))),
                         title="Contrato / datos de demostración" if "is_demo" in str(data)
                         else "Resultado", border_style="#24465c"))
    term.print(Text("\n JSON para automatización: --format json", style="dim"))
