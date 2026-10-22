"""``crewforge academic plan | feedback | cite | disclose``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from rich.markdown import Markdown

from ...cli_support import (
    EXIT_FAILED,
    EXIT_USAGE,
    console,
    err_console,
    fail,
    llm_config,
    print_usage,
    recipe_settings,
    run,
)
from ...core.errors import ConfigError
from ..docs.ingest import IngestAgent
from .agents import FEEDBACK_AGENTS, STYLES
from .citations import split_references
from .disclosure import DisclosureError, append_record, build_statement, make_record, read_records
from .language import LANGUAGES, t
from .pipeline import AcademicCrew
from .report import (
    cite_dict,
    cite_markdown,
    feedback_dict,
    feedback_markdown,
    plan_dict,
    plan_markdown,
)
from .settings import AcademicSettings


def _settings(ctx: click.Context) -> AcademicSettings:
    try:
        return AcademicSettings.from_mapping(recipe_settings(ctx, "academic"))
    except ConfigError as exc:
        fail(f"configuration: {exc}", EXIT_USAGE)


def _read(path: str, settings: AcademicSettings, what: str) -> str:
    """Read a .txt/.md (or, with the docs extra, .docx/.pdf) file within the size limit."""
    try:
        text = IngestAgent()._read_file(Path(path))
    except ConfigError as exc:
        fail(f"configuration: {exc}", EXIT_USAGE)
    except OSError as exc:
        fail(f"cannot read {path}: {exc}", EXIT_USAGE)
    if not text.strip():
        fail(f"the {what} {path} is empty", EXIT_USAGE)
    if len(text) > settings.max_input_chars:
        fail(
            f"the {what} {path} has {len(text):,} characters; the limit is "
            f"{settings.max_input_chars:,} (academic.max_input_chars)",
            EXIT_USAGE,
        )
    return text


def _common(fn):
    """Options shared by plan / feedback / cite."""
    fn = click.option(
        "--no-log", is_flag=True, help="Do not record this step for `academic disclose`."
    )(fn)
    fn = click.option(
        "--log",
        "log_path",
        default=None,
        type=click.Path(dir_okay=False),
        help="Usage record to append to (default: academic.log_file, "
        "crewforge-academic-log.jsonl).",
    )(fn)
    fn = click.option("--output", "-o", default="", help="Write the result to this file.")(fn)
    fn = click.option(
        "--format",
        "-f",
        "fmt",
        default="text",
        show_default=True,
        type=click.Choice(["text", "markdown", "json"]),
    )(fn)
    fn = click.option(
        "--style",
        "-s",
        default=None,
        type=click.Choice(STYLES, case_sensitive=False),
        help="Citation style (default: academic.citation_style, apa).",
    )(fn)
    fn = click.option(
        "--language",
        "-L",
        default=None,
        type=click.Choice(LANGUAGES),
        help="Output language: en (English) or ms (Bahasa Melayu, Malaysia).",
    )(fn)
    return fn


def _emit(markdown: str, data: dict[str, Any], fmt: str, output: str) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) if fmt == "json" else markdown
    if output:
        Path(output).write_text(text, encoding="utf-8")
        err_console.print(f"[green]Written to {output}[/]", highlight=False)
    elif fmt == "text":
        console.print(Markdown(markdown))
    else:
        click.echo(text)


def _record(
    ctx: click.Context,
    settings: AcademicSettings,
    step: str,
    *,
    log_path: str | None,
    no_log: bool,
    language: str,
    inputs: list[tuple[str, str]],
    counts: dict[str, int],
    style: str | None,
    tokens: int,
) -> None:
    if no_log:
        return
    path = log_path or settings.log_file
    record = make_record(
        step,
        config=llm_config(ctx),
        language=language,
        inputs=inputs,
        counts=counts,
        style=style,
        tokens=tokens,
    )
    try:
        append_record(path, record)
    except OSError as exc:
        # The run itself succeeded; say clearly that the record is missing.
        fail(f"the result is above, but the usage record could not be written to {path}: {exc}")
    err_console.print(t(language, "labels.recorded", path=path), highlight=False, soft_wrap=True)


def _header(ctx: click.Context, step: str, target: str, language: str) -> None:
    config = llm_config(ctx)
    err_console.print(
        f"[bold cyan]crewforge academic {step}[/] · {target} · {language} · "
        f"{config.provider}/{config.model}",
        highlight=False,
        soft_wrap=True,
    )


@click.group("academic")
def academic():
    """Honest academic writing assistant: plan, feedback, cite, disclose.

    \b
    It helps you plan and improve YOUR work. It does not write the
    assignment, does not invent references, and keeps a record of each
    step so `disclose` can write your AI-use statement.

    \b
    Examples:
      crewforge academic plan brief.md --language ms
      crewforge academic feedback draft.md --brief brief.md
      crewforge academic cite references.txt --style ieee
      crewforge academic disclose
    """


@academic.command("plan")
@click.argument("brief", type=click.Path(exists=True, dir_okay=False))
@click.option("--words", "-w", type=click.IntRange(min=50), default=None, help="Target length.")
@_common
@click.pass_context
def plan_cmd(ctx, brief, words, language, style, fmt, output, log_path, no_log):
    """Turn an assignment BRIEF into research questions, an outline and a word budget."""
    settings = _settings(ctx)
    language = language or settings.language
    text = _read(brief, settings, "brief")
    _header(ctx, "plan", brief, language)
    crew = AcademicCrew(llm_config(ctx), language=language)
    result = run(crew.plan(text, words=words, style=style.lower() if style else None))
    _emit(plan_markdown(result), plan_dict(result), fmt, output)
    _warn_malay(result.malay_issues, language)
    print_usage(result.tracker)
    _record(
        ctx,
        settings,
        "plan",
        log_path=log_path,
        no_log=no_log,
        language=language,
        inputs=[(brief, text)],
        counts=result.counts(),
        style=result.style,
        tokens=result.tracker.total_tokens,
    )


@academic.command("feedback")
@click.argument("draft", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--brief",
    "brief_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="The assignment brief, so feedback can check the draft against it.",
)
@click.option(
    "--reviewer",
    "reviewers",
    multiple=True,
    type=click.Choice(list(FEEDBACK_AGENTS)),
    help="Run only these reviewers (repeatable). Default: all four.",
)
@click.option(
    "--allow-partial",
    is_flag=True,
    help="Continue when some reviewers fail (they are listed); by default any failure fails.",
)
@_common
@click.pass_context
def feedback_cmd(
    ctx, draft, brief_path, reviewers, allow_partial, language, style, fmt, output, log_path, no_log
):
    """Comment on your DRAFT: structure, argument, clarity and citations. No rewriting."""
    settings = _settings(ctx)
    language = language or settings.language
    text = _read(draft, settings, "draft")
    brief_text = _read(brief_path, settings, "brief") if brief_path else ""
    _header(ctx, "feedback", draft, language)
    crew = AcademicCrew(
        llm_config(ctx), language=language, max_suggestion_words=settings.max_suggestion_words
    )
    result = run(
        crew.feedback(
            text,
            name=Path(draft).name,
            brief_text=brief_text,
            style=(style or settings.citation_style).lower(),
            reviewers=list(reviewers) or None,
            allow_partial=allow_partial,
        )
    )
    _emit(feedback_markdown(result), feedback_dict(result), fmt, output)
    _warn_malay(result.malay_issues, language)
    print_usage(result.tracker)
    inputs = [(draft, text)] + ([(brief_path, brief_text)] if brief_path else [])
    _record(
        ctx,
        settings,
        "feedback",
        log_path=log_path,
        no_log=no_log,
        language=language,
        inputs=inputs,
        counts=result.counts(),
        style=result.style,
        tokens=result.tracker.total_tokens,
    )


@academic.command("cite")
@click.argument("references", type=click.Path(exists=True, dir_okay=False))
@_common
@click.pass_context
def cite_cmd(ctx, references, language, style, fmt, output, log_path, no_log):
    """Format the REFERENCES you supply (one per line or per paragraph). Adds none."""
    settings = _settings(ctx)
    language = language or settings.language
    style = (style or settings.citation_style).lower()
    text = _read(references, settings, "references file")
    refs = split_references(text)
    if not refs:
        fail(f"no references found in {references}", EXIT_USAGE)
    _header(ctx, "cite", f"{references} ({len(refs)} reference(s))", language)
    crew = AcademicCrew(llm_config(ctx), language=language)
    result = run(crew.cite(refs, style=style))
    _emit(cite_markdown(result), cite_dict(result), fmt, output)
    print_usage(result.tracker)
    _record(
        ctx,
        settings,
        "cite",
        log_path=log_path,
        no_log=no_log,
        language=language,
        inputs=[(references, text)],
        counts=result.counts(),
        style=style,
        tokens=result.tracker.total_tokens,
    )


@academic.command("disclose")
@click.option(
    "--log",
    "log_path",
    default=None,
    type=click.Path(dir_okay=False),
    help="Usage record written by plan/feedback/cite (default: academic.log_file).",
)
@click.option("--language", "-L", default=None, type=click.Choice(LANGUAGES))
@click.option(
    "--format",
    "-f",
    "fmt",
    default="markdown",
    show_default=True,
    type=click.Choice(["text", "markdown", "json"]),
)
@click.option("--output", "-o", default="", help="Write the statement to this file.")
@click.pass_context
def disclose_cmd(ctx, log_path, language, fmt, output):
    """Write an AI-use statement from the recorded steps (no LLM, no key needed)."""
    settings = _settings(ctx)
    language = language or settings.language
    path = Path(log_path or settings.log_file)
    if not path.exists():
        fail(t(language, "disclosure.empty", path=path))
    try:
        records = read_records(path)
    except DisclosureError as exc:
        fail(str(exc))
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")
    if not records:
        fail(t(language, "disclosure.empty", path=path), EXIT_FAILED)
    statement = build_statement(records, language)
    _emit(statement, {"statement": statement, "records": records}, fmt, output)


def _warn_malay(issues: dict[str, str], language: str) -> None:
    if issues:
        found = ", ".join(f"{k} → {v}" for k, v in issues.items())
        err_console.print(
            f"[yellow]{t(language, 'labels.malay_warning', found=found)}[/]",
            highlight=False,
            soft_wrap=True,
        )


commands = [academic]
