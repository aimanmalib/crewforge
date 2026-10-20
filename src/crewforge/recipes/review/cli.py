"""``crewforge review`` — multi-agent code review (ported from codeguard)."""

from __future__ import annotations

import json
from pathlib import Path

import click
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rich.markdown import Markdown

from ...cli_support import (
    EXIT_USAGE,
    console,
    err_console,
    fail,
    llm_config,
    print_usage,
    recipe_settings,
    run,
)
from ...core.config import LLMConfig
from .agents import REVIEW_AGENTS
from .pipeline import CodeReviewCrew, ReviewResult
from .report import report_dict, report_markdown
from .sources import DEFAULT_MAX_FILE_BYTES, SourceError, collect, detect_language

# Kept under the old private name: codeguard's tests and users imported it.
_detect_language = detect_language


class ReviewSettings(BaseModel):
    """Optional ``review:`` section of crewforge.yaml."""

    model_config = ConfigDict(extra="forbid")

    agents: list[str] = Field(default_factory=lambda: list(REVIEW_AGENTS))
    max_file_bytes: int = Field(default=DEFAULT_MAX_FILE_BYTES, gt=0)


async def _run_review(
    config: LLMConfig,
    code: str,
    language: str,
    *,
    agents: list[str] | None = None,
    allow_partial: bool = False,
) -> ReviewResult:
    crew = CodeReviewCrew(config, agents=agents, allow_partial=allow_partial)
    return await crew.review(code, language)


@click.command("review")
@click.argument("path", required=False, type=click.Path())
@click.option("--path", "-p", "path_opt", default=None, help="Same as PATH (codeguard style).")
@click.option("--language", "-l", default="", help="Force the language (default: detect).")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="text",
    show_default=True,
    type=click.Choice(["text", "json", "markdown"]),
)
@click.option("--output", "-o", default="", help="Write the report to this file.")
@click.option(
    "--allow-partial",
    is_flag=True,
    help="Continue when some reviewers fail (they are listed as warnings); "
    "by default any failed reviewer fails the run.",
)
@click.pass_context
def review(ctx, path, path_opt, language, fmt, output, allow_partial):
    """Review a file or directory with six specialist agents plus a summary.

    \b
    Example:
      crewforge review app.py
      crewforge review src/ -f json -o review.json
    """
    target = path or path_opt
    if not target:
        fail("give a file or directory to review (crewforge review PATH)", EXIT_USAGE)
    try:
        settings = ReviewSettings(**recipe_settings(ctx, "review"))
    except ValidationError as exc:
        fail(f"configuration: invalid review settings: {exc.errors()[0]['msg']}", EXIT_USAGE)
    unknown = [a for a in settings.agents if a not in REVIEW_AGENTS]
    if unknown:
        fail(
            f"configuration: unknown reviewer(s) {', '.join(unknown)}; "
            f"known: {', '.join(REVIEW_AGENTS)}",
            EXIT_USAGE,
        )
    try:
        sources = collect(target, max_file_bytes=settings.max_file_bytes)
    except SourceError as exc:
        fail(str(exc), EXIT_USAGE)
    language = language or sources.language
    for skipped in sources.skipped:
        err_console.print(f"[yellow]skipped {skipped}[/]", highlight=False, soft_wrap=True)

    config = llm_config(ctx)
    err_console.print(
        f"[bold cyan]crewforge review[/] · {target} · {len(sources.files)} file(s) · "
        f"language: {language or 'auto'} · {config.provider}/{config.model}",
        highlight=False,
        soft_wrap=True,
    )
    result = run(
        _run_review(
            config,
            sources.code,
            language,
            agents=settings.agents,
            allow_partial=allow_partial,
        )
    )
    _display_results(result, fmt, output)


def _display_results(result: ReviewResult, fmt: str, output: str) -> None:
    text = json.dumps(report_dict(result), indent=2) if fmt == "json" else report_markdown(result)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        err_console.print(f"[green]Report written to {output}[/]")
    elif fmt == "text":
        console.print(Markdown(text))
    else:
        click.echo(text)

    failed = result.failed_agents
    if failed:
        err_console.print(
            f"[yellow]Warning: {len(failed)} agent(s) failed and were skipped: "
            f"{', '.join(failed)}[/]",
            highlight=False,
            soft_wrap=True,
        )
    if result.tracker is not None:
        print_usage(result.tracker)


commands = [review]
