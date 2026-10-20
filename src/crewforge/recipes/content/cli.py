"""``crewforge write`` — multi-agent article pipeline (ported from contentforge)."""

from __future__ import annotations

import click
from pydantic import ValidationError
from rich.panel import Panel

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
from .pipeline import ContentPipeline
from .settings import PUBLISH_TARGETS, ContentSettings
from .text import word_count


@click.command("write")
@click.argument("topic")
@click.option("--words", "-w", type=int, default=None, help="Target word count [default: 2000].")
@click.option("--language", "-l", default=None, help="Article language [default: en].")
@click.option("--output", "-o", default=None, help="Output directory [default: ./output].")
@click.option(
    "--format",
    "-f",
    "formats",
    multiple=True,
    type=click.Choice(PUBLISH_TARGETS),
    help="Publish format (repeatable) [default: markdown].",
)
@click.option("--seo/--no-seo", default=None, help="Run the SEO agent [default: on].")
@click.option("--translate", "-t", multiple=True, help="Also translate to LANG (repeatable).")
@click.option("--threshold", type=float, default=None, help="Quality threshold 0-1 [default: 0.8].")
@click.option("--max-iter", type=int, default=None, help="Max edit/quality rounds [default: 3].")
@click.option(
    "--accept-below-threshold",
    is_flag=True,
    help="Publish even if the final quality score stays below the threshold (warns).",
)
@click.pass_context
def write(
    ctx,
    topic,
    words,
    language,
    output,
    formats,
    seo,
    translate,
    threshold,
    max_iter,
    accept_below_threshold,
):
    """Research, outline, write, SEO-check, edit, score, translate and publish an article.

    The research agent has no web access: facts come from the model's own
    knowledge, so review the article before publishing it.

    \b
    Example:
      crewforge write "Why unit tests matter" --words 600 -f markdown -f html
    """
    try:
        settings = ContentSettings.from_mapping(recipe_settings(ctx, "content"))
        pipe = settings.pipeline.model_dump()
        overrides = {
            "target_word_count": words,
            "language": language,
            "seo_enabled": seo,
            "quality_threshold": threshold,
            "max_iterations": max_iter,
        }
        pipe.update({k: v for k, v in overrides.items() if v is not None})
        if formats:
            pipe["publish_targets"] = list(formats)
        if translate:
            pipe["enable_translation"] = True
            pipe["target_languages"] = list(translate)
        if accept_below_threshold:
            pipe["accept_below_threshold"] = True
        settings = ContentSettings(
            pipeline=pipe,
            agents=settings.agents,
            output_dir=output or settings.output_dir,
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        fail(f"configuration: {loc}: {first.get('msg')}", EXIT_USAGE)

    cfg = settings.pipeline
    llm = llm_config(ctx)
    langs = ", ".join(cfg.target_languages) if cfg.enable_translation else "off"
    err_console.print(
        f"[bold cyan]crewforge write[/] · {llm.provider}/{llm.model} · {cfg.target_word_count} "
        f"words · {cfg.language} · SEO {'on' if cfg.seo_enabled else 'off'} · threshold "
        f"{cfg.quality_threshold} · translate {langs}",
        highlight=False,
        soft_wrap=True,
    )
    result = run(ContentPipeline(llm, settings).run(topic))

    if result.status == "below_threshold":
        err_console.print(
            f"[yellow]warning: quality score {result.quality_score:.0f} is below the threshold "
            f"{cfg.quality_threshold * 100:.0f} (accepted with --accept-below-threshold)[/]"
        )
    files = "\n".join(f"  {f}" for f in result.output_files)
    console.print(
        Panel(
            f"Article: {word_count(result.article)} words · quality score "
            f"{result.quality_score:.0f}/100\nFiles:\n{files}\nMetrics: {result.metrics_path}",
            title=f"crewforge write — {topic}",
            border_style="green" if result.ok else "yellow",
        ),
        soft_wrap=True,
    )
    if result.tracker is not None:
        print_usage(result.tracker)


commands = [write]
