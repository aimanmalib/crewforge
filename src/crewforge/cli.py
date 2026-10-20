"""``crewforge`` command line: global provider options + the four recipes."""

from __future__ import annotations

import logging
from pathlib import Path

import click
from rich.table import Table

from . import __version__
from .cli_support import EXIT_USAGE, console, err_console, fail
from .core.config import LLMConfig, Settings
from .core.errors import ConfigError
from .core.providers import ENV_API_KEY, PROVIDERS
from .recipes.api.cli import commands as api_commands
from .recipes.content.cli import commands as content_commands
from .recipes.docs.cli import commands as docs_commands
from .recipes.review.cli import commands as review_commands


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="crewforge")
@click.option(
    "--provider",
    "-P",
    default=None,
    help="Provider preset (see `crewforge providers`). Env: CREWFORGE_PROVIDER. Default: openai.",
)
@click.option("--model", "-m", default=None, help="Model name. Env: CREWFORGE_MODEL.")
@click.option(
    "--base-url", default=None, help="OpenAI-compatible base URL. Env: CREWFORGE_BASE_URL."
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="crewforge.yaml (written by `crewforge init`); ${VAR} references are expanded.",
)
@click.option("--verbose", "-v", is_flag=True, help="Log HTTP retries and agent progress.")
@click.pass_context
def main(ctx, provider, model, base_url, config_path, verbose):
    """One crew of LLM agents, four recipes, any OpenAI-compatible provider.

    \b
    Recipes:
      review     multi-agent code review
      ingest     parse + chunk documents (no LLM calls)
      ask        document Q&A with citations (+ --verify fact-check)
      summarize  document summaries
      scaffold   natural language -> FastAPI project + OpenAPI spec
      validate   check an OpenAPI spec (and a scaffolded app) offline
      write      research -> outline -> write -> SEO -> edit -> quality -> publish

    API keys are read from the environment only (e.g. OPENAI_API_KEY) and are
    never written to disk. Exit codes: 0 ok, 1 run failed, 2 usage/config error.
    """
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )
    try:
        settings = Settings.from_yaml(config_path) if config_path else Settings()
    except ConfigError as exc:
        fail(f"configuration: {exc}", EXIT_USAGE)
    overrides = {
        k: v for k, v in {"provider": provider, "model": model, "base_url": base_url}.items() if v
    }
    if overrides:
        data = settings.llm.model_dump()
        if "provider" in overrides and overrides["provider"] != settings.llm.provider:
            # A different provider means different defaults: re-resolve from scratch,
            # keeping only explicitly given values.
            reset = ("api_key", "base_url", "model", "auth_style")
            data = {k: v for k, v in data.items() if k not in reset}
        data.update(overrides)
        settings.llm = LLMConfig(**data)
    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings


@main.command()
def providers():
    """List provider presets and the env var that holds each key."""
    table = Table(title="Provider presets", title_justify="left")
    table.add_column("Name", style="bold cyan")
    table.add_column("Provider")
    table.add_column("Base URL")
    table.add_column("Default model")
    table.add_column("Key env var")
    table.add_column("Auth")
    for p in PROVIDERS.values():
        table.add_row(
            p.name,
            p.label,
            p.base_url or "(set CREWFORGE_BASE_URL / --base-url)",
            p.default_model or "(set CREWFORGE_MODEL / --model)",
            p.env_key + (" (optional)" if p.keyless else ""),
            "api-key header" if p.auth_style == "api-key" else "Bearer",
        )
    console.print(table)
    console.print(
        f"Any preset's key, URL and model can be overridden with {ENV_API_KEY}, "
        "CREWFORGE_BASE_URL and CREWFORGE_MODEL."
    )


@main.command()
@click.option(
    "--output", "-o", default="crewforge.yaml", show_default=True, type=click.Path(dir_okay=False)
)
@click.option("--force", is_flag=True, help="Overwrite an existing file.")
@click.pass_context
def init(ctx, output, force):
    """Write a starter crewforge.yaml (the key is written as a ${VAR} reference)."""
    path = Path(output)
    if path.exists() and not force:
        fail(f"{path} already exists (use --force to overwrite)", EXIT_USAGE)
    settings: Settings = ctx.obj["settings"]
    settings.write_template(path)
    err_console.print(
        f"[green]Wrote {path}[/] — api_key is the reference "
        f"${{{settings.llm.key_env_var}}}; export that variable, never paste the key into the file."
    )


for _cmd in (*review_commands, *docs_commands, *api_commands, *content_commands):
    main.add_command(_cmd)


if __name__ == "__main__":  # pragma: no cover
    main()
