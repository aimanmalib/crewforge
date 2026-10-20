"""``crewforge ingest | ask | summarize`` — document Q&A (ported from documind)."""

from __future__ import annotations

import click
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ...cli_support import console, err_console, llm_config, print_usage, recipe_settings, run
from ...core.errors import ConfigError
from .pipeline import DocsPipeline
from .settings import DocsSettings

FILES = click.argument(
    "files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False)
)


def _pipeline(ctx: click.Context) -> DocsPipeline:
    # Settings errors surface as ConfigError inside run() -> exit 2.
    return DocsPipeline(llm_config(ctx), _settings_or_none(ctx))


def _settings_or_none(ctx: click.Context) -> DocsSettings | None:
    try:
        return DocsSettings.from_mapping(recipe_settings(ctx, "docs"))
    except ConfigError as exc:
        from ...cli_support import EXIT_USAGE, fail

        fail(f"configuration: {exc}", EXIT_USAGE)


@click.command("ingest")
@FILES
@click.pass_context
def ingest(ctx, files):
    """Parse, chunk and index documents (no LLM calls, no API key needed).

    Useful to check how a file is chunked before asking questions.
    """

    async def _run():
        async with _pipeline(ctx) as pipeline:
            docs = await pipeline.ingest_documents(list(files))
            table = Table(title="Ingestion results", title_justify="left")
            table.add_column("File", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Chunks", justify="right")
            table.add_column("Words", justify="right")
            for d in docs:
                table.add_row(d.filename, d.file_type, str(len(d.chunks)), str(d.total_words))
            console.print(table)

    run(_run())


@click.command("ask")
@FILES
@click.option("-q", "--question", "questions", multiple=True, help="Question to ask (repeatable).")
@click.option("--verify", is_flag=True, help="Fact-check each answer against its sources.")
@click.option("--rerank", is_flag=True, help="Let the LLM rerank retrieved passages.")
@click.option(
    "--export",
    "export_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the Q&A session to this file.",
)
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
    help="Export format.",
)
@click.pass_context
def ask(ctx, files, questions, verify, rerank, export_path, export_format):
    """Answer questions about FILES with [Source N] citations.

    \b
    Example:
      crewforge ask handbook.pdf -q "How many days of leave?" --verify
    """
    if not questions:
        raise click.UsageError("provide at least one question with -q")

    async def _run():
        async with _pipeline(ctx) as pipeline:
            pipeline.require_llm()  # fail on config before parsing anything
            docs = await pipeline.ingest_documents(list(files))
            for d in docs:
                err_console.print(f"[green]✓[/] ingested {d.filename} ({len(d.chunks)} chunks)")
            try:
                for q in questions:
                    console.print(f"\n[bold yellow]Q:[/] {q}")
                    if verify:
                        answer, check = await pipeline.ask_with_verification(q, rerank=rerank)
                    else:
                        answer = await pipeline.ask(q, rerank=rerank)
                    console.print(Markdown(answer.answer_text))
                    if verify:
                        color = {"verified": "green", "partially_verified": "yellow"}.get(
                            check.overall_verdict, "red"
                        )
                        console.print(
                            f"[{color}]Verification: {check.overall_verdict}[/] "
                            f"({check.claims_verified}/{check.claims_checked} claims verified)"
                        )
                if export_path:
                    path = await pipeline.export_session(export_path, fmt=export_format)
                    err_console.print(f"[blue]Exported to:[/] {path}")
            finally:
                print_usage(pipeline.tracker)

    run(_run())


@click.command("summarize")
@FILES
@click.option(
    "--length",
    type=click.Choice(["short", "medium", "long"]),
    default="medium",
    show_default=True,
)
@click.pass_context
def summarize(ctx, files, length):
    """Summarize each document and list its key points."""

    async def _run():
        async with _pipeline(ctx) as pipeline:
            pipeline.require_llm()
            try:
                for doc in await pipeline.ingest_documents(list(files)):
                    summary = await pipeline.summarize_document(doc, max_length=length)
                    title = f"Summary: {doc.filename}"
                    if summary.truncated:
                        title += " (first part only — document was truncated)"
                    console.print(Panel(Markdown(summary.summary_text), title=title))
            finally:
                print_usage(pipeline.tracker)

    run(_run())


commands = [ingest, ask, summarize]
