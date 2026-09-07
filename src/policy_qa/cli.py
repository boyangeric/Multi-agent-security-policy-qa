"""Command-line interface: ingest | ask | interactive | evaluate.

Heavy modules (orchestrator, ingestion, evaluator) are imported inside the
commands so `--help` and startup stay fast.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

from .config import Settings
from .utils.logging_setup import setup_logging
from .report import WIDTH, render_report
from .tracing import QueryTrace

app = typer.Typer(
    help="Multi-Agent Security Policy Q&A: RAG experiments with Microsoft Agent Framework and Azure AI Search.",
    invoke_without_command=True,
)


async def _run_query_with_status(orchestrator: "Orchestrator", question: str) -> QueryTrace:
    """Run one query with a spinner so the user sees the pipeline is working."""
    from rich.console import Console

    with Console().status(
        "Processing — moderating, planning, retrieving, and grounding the answer..."
    ):
        return await orchestrator.run_query(question)


def _settings() -> Settings:
    settings = Settings.from_env()
    setup_logging(
        settings.log_level,
        log_file=settings.log_file,
        log_to_console=settings.log_to_console,
    )
    return settings


@app.command()
def ingest() -> None:
    """Download NIST SP 800-53 Rev 5, build the index and ingest all records."""
    settings = _settings()
    from .ingestion.pipeline import run_ingestion

    count = run_ingestion(settings)
    typer.echo(f"Ingested {count} records into index '{settings.search_index_name}'.")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Security policy question"),
    json_output: bool = typer.Option(False, "--json", help="Print the full trace as JSON"),
) -> None:
    """Ask a question through the Planner -> Retrieval -> Response pipeline."""
    settings = _settings()
    from .orchestrator import Orchestrator

    trace = asyncio.run(_run_query_with_status(Orchestrator(settings), question))

    if json_output:
        typer.echo(json.dumps(trace.to_dict(), indent=2, ensure_ascii=False))
        return

    typer.echo(render_report(trace, settings))


@app.callback()
def main(ctx: typer.Context) -> None:
    """Drop into interactive mode when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        interactive()


@app.command()
def interactive() -> None:
    """Start an interactive session: ask questions in a loop until 'exit'."""
    settings = _settings()
    from .orchestrator import Orchestrator

    typer.echo("=" * WIDTH)
    typer.echo("MULTI-AGENT SECURITY POLICY Q&A — interactive mode")
    typer.echo("Ask a security policy question, or type 'exit' to quit.")
    typer.echo("=" * WIDTH)

    async def _session() -> None:
        # One orchestrator for the whole session: Azure clients are built once
        # and reused across questions.
        orchestrator = Orchestrator(settings)
        while True:
            try:
                question = (await asyncio.to_thread(input, "\nUser > ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question:
                continue
            if question.lower() in {"exit", "quit", "q"}:
                break
            trace = await _run_query_with_status(orchestrator, question)
            typer.echo(render_report(trace, settings))

    asyncio.run(_session())
    typer.echo("Goodbye.")


@app.command()
def evaluate() -> None:
    """Run the evaluation suite over the test queries and write a report."""
    settings = _settings()
    from .evaluator import run_evaluation

    report_path = asyncio.run(run_evaluation(settings))
    typer.echo(f"Evaluation complete. Report: {report_path}")


if __name__ == "__main__":
    app()
