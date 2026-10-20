"""``crewforge scaffold | validate`` — API scaffolding (ported from apiforge)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from ...cli_support import (
    EXIT_FAILED,
    EXIT_USAGE,
    console,
    err_console,
    fail,
    llm_config,
    print_usage,
    report_crew_failure,
    run,
)
from ...core.errors import AgentFailure, CrewFailedError
from .agents import ValidateAgent, ValidationResult
from .appcheck import AppCheck, check_app
from .formatters import OutputFormatter
from .pipeline import ApiPipeline
from .scaffold import ProjectScaffold


def _print_validation(v: ValidationResult) -> None:
    color = "green" if v.valid else "red"
    console.print(
        f"[{color}]Validation: {'valid' if v.valid else 'INVALID'} · {v.score}/100[/] "
        f"({v.operations} operation(s) checked, {len(v.errors)} error(s), "
        f"{len(v.warnings)} warning(s))",
        highlight=False,
    )
    for e in v.errors:
        console.print(f"  [red]ERROR:[/] {e}", highlight=False, soft_wrap=True)
    for w in v.warnings:
        console.print(f"  [yellow]WARN:[/] {w}", highlight=False, soft_wrap=True)


def _print_app_check(check: AppCheck) -> None:
    if not check.ran:
        err_console.print(f"[dim]{check.note}[/]", highlight=False)
    elif check.ok:
        console.print(f"[green]App check: OK[/] — {check.note}", highlight=False)
    else:
        for e in check.errors:
            console.print(f"  [red]APP:[/] {e}", highlight=False, soft_wrap=True)


@click.command("scaffold")
@click.argument("description")
@click.option(
    "--output", "-o", default="./output", show_default=True, help="Project directory to write."
)
@click.option("--force", is_flag=True, help="Write into a non-empty directory.")
@click.pass_context
def scaffold(ctx, description, output, force):
    """Turn a plain-English API DESCRIPTION into a FastAPI project + OpenAPI spec.

    \b
    Example:
      crewforge scaffold "Todo API: list, create and delete todos" -o todo-api
    """
    out = Path(output)
    if out.exists() and any(out.iterdir()) and not force:
        fail(f"{out} is not empty (use --force to write into it)", EXIT_USAGE)

    result = run(ApiPipeline(llm_config(ctx)).generate(description))
    files = ProjectScaffold(out).scaffold(result)
    console.print(f"[green]Wrote {len(files)} files[/]")
    console.print(OutputFormatter.file_tree(files, out), highlight=False)
    _print_validation(result.validation)
    check = check_app(out, result.openapi_spec)
    _print_app_check(check)
    if result.tracker is not None:
        print_usage(result.tracker)

    if not result.validation.valid:
        sys.exit(EXIT_FAILED)
    if check.ran and not check.ok:
        # The router agent rewrote the routes; the spec promises routes the app lacks.
        failure = AgentFailure("router", "; ".join(check.errors), "mismatch")
        report_crew_failure(CrewFailedError("scaffold", [failure]))
        sys.exit(EXIT_FAILED)


@click.command("validate")
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Print the result as JSON.")
def validate(path, as_json):
    """Validate an OpenAPI spec file, or a scaffolded project directory, offline.

    For a directory, its openapi.json is checked and, when FastAPI is installed,
    the app is imported in a subprocess to confirm it serves every operation.
    No LLM call and no API key are needed.
    """
    target = Path(path)
    spec_file = target / "openapi.json" if target.is_dir() else target
    if not spec_file.is_file():
        fail(f"no openapi.json in {target}", EXIT_USAGE)
    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        fail(f"{spec_file} is not valid JSON: {exc}")

    result = asyncio.run(ValidateAgent().validate(spec))
    check = check_app(target, spec) if target.is_dir() else AppCheck(False, note="")
    ok = result.valid and (not check.ran or check.ok)
    if as_json:
        data = result.to_dict()
        data["app_check"] = {"ran": check.ran, "errors": check.errors, "note": check.note}
        data["ok"] = ok
        click.echo(json.dumps(data, indent=2))
    else:
        _print_validation(result)
        if target.is_dir():
            _print_app_check(check)
    if not ok:
        sys.exit(EXIT_FAILED)


commands = [scaffold, validate]
