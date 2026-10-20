"""Helpers shared by every recipe's CLI commands.

Exit codes (stable, documented in the README):

* 0 — the run succeeded
* 1 — the run failed: an agent errored, returned empty/unparseable output, a
  validator found problems, or the LLM endpoint refused the request
* 2 — usage or configuration error (bad flags, unknown provider, missing key)
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any, NoReturn, TypeVar

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from .core.config import LLMConfig, Settings
from .core.errors import AgentError, ConfigError, CrewFailedError, LLMError
from .core.usage import UsageTracker

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

T = TypeVar("T")

console = Console()
# Status, warnings and errors go to stderr so JSON on stdout stays parseable.
err_console = Console(stderr=True)


def settings_from_ctx(ctx: click.Context) -> Settings:
    obj = ctx.find_root().obj or {}
    settings = obj.get("settings")
    if settings is None:
        settings = Settings()
        obj["settings"] = settings
    return settings


def llm_config(ctx: click.Context) -> LLMConfig:
    return settings_from_ctx(ctx).llm


def recipe_settings(ctx: click.Context, recipe: str) -> dict[str, Any]:
    return dict(getattr(settings_from_ctx(ctx), recipe, {}) or {})


def fail(message: str, code: int = EXIT_FAILED) -> NoReturn:
    err_console.print(f"[bold red]error:[/] {escape(message)}", highlight=False, soft_wrap=True)
    sys.exit(code)


def report_crew_failure(exc: CrewFailedError) -> None:
    err_console.print(f"[bold red]error:[/] {exc.crew} failed", highlight=False, soft_wrap=True)
    for f in exc.failures:
        err_console.print(
            f"  [red]✗ agent '{escape(f.agent)}'[/] ({f.kind}): {escape(f.error)}",
            highlight=False,
            soft_wrap=True,
        )


def run(coro: Coroutine[Any, Any, T]) -> T:
    """Run a recipe coroutine and translate failures into exit codes and messages."""
    try:
        return asyncio.run(coro)
    except ConfigError as exc:
        fail(f"configuration: {exc}", EXIT_USAGE)
    except CrewFailedError as exc:
        report_crew_failure(exc)
        sys.exit(EXIT_FAILED)
    except AgentError as exc:
        fail(str(exc))
    except LLMError as exc:
        fail(f"LLM request failed: {exc}")


def print_usage(tracker: UsageTracker, *, title: str = "Token usage (provider-reported)") -> None:
    """Per-agent usage table on stderr. Numbers come only from provider responses."""
    agents = tracker.by_agent()
    if not agents:
        return
    table = Table(title=title, title_justify="left")
    table.add_column("Agent", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Prompt", justify="right")
    table.add_column("Completion", justify="right")
    table.add_column("Total", justify="right", style="green")
    for name, a in agents.items():
        total = f"{a.total_tokens:,}"
        if a.unreported_calls:
            total += f" (+{a.unreported_calls} unreported)"
        table.add_row(name, str(a.calls), f"{a.prompt_tokens:,}", f"{a.completion_tokens:,}", total)
    table.add_row(
        "[bold]total[/]", str(tracker.total_calls), "", "", f"[bold]{tracker.total_tokens:,}[/]"
    )
    err_console.print(table)
    if tracker.unreported_calls:
        err_console.print(
            f"[yellow]{tracker.unreported_calls} call(s) returned no usage; "
            "they are not counted (nothing is estimated).[/]"
        )
