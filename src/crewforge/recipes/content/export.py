"""Write articles to disk as Markdown (with front matter), HTML or JSON."""

from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def export_markdown(content: str, metadata: dict, output_path: str | Path) -> Path:
    """Markdown with a YAML front-matter block."""
    import yaml

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    front = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    output.write_text(f"---\n{front}\n---\n\n{content}", encoding="utf-8")
    return output


def _markdown_to_html(content: str) -> str:
    """Deliberately small Markdown subset: headings, bold, italics, paragraphs."""
    lines = []
    for raw in content.splitlines():
        line = html_lib.escape(raw)
        if not line.strip():
            continue
        m = re.match(r"^(#{1,3}) (.+)$", line)
        if m:
            level = len(m.group(1))
            lines.append(f"<h{level}>{m.group(2)}</h{level}>")
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
        lines.append(f"<p>{line}</p>")
    return "\n        ".join(lines)


def export_html(content: str, metadata: dict, output_path: str | Path) -> Path:
    """Standalone semantic HTML5 page."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    esc = html_lib.escape
    title = esc(str(metadata.get("title", "Untitled")))
    description = esc(str(metadata.get("description", "")))
    lang = esc(str(metadata.get("language", "en")))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    page = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{description}">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.6; }}
    </style>
</head>
<body>
    <article>
        {_markdown_to_html(content)}
    </article>
    <footer>
        <p><small>Generated {date} with crewforge (content recipe).
        Review before publishing.</small></p>
    </footer>
</body>
</html>
"""
    output.write_text(page, encoding="utf-8")
    return output


def export_json_report(data: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return output
