"""Render docs/architecture.mmd to docs/architecture.png.

PyPI does not draw Mermaid, so the README embeds this PNG instead. Re-render after editing the .mmd:

    uv run --with playwright python scripts/render_architecture.py \
        docs/architecture.mmd docs/architecture.png
"""

import json
import sys

from playwright.sync_api import sync_playwright

MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
CONFIG = {
    "startOnLoad": False,
    "theme": "neutral",
    "themeVariables": {"fontSize": "18px"},
    "flowchart": {
        "htmlLabels": True,
        "curve": "basis",
        "useMaxWidth": False,
        "wrappingWidth": 420,
        "subGraphTitleMargin": {"top": 10, "bottom": 34},
    },
}
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>
body{{margin:0;background:#fff;font-family:system-ui,sans-serif}}
#d{{display:inline-block;padding:28px}}
</style>
<script src="{mermaid}"></script></head><body><div id="d"></div><script>
mermaid.initialize({config});
mermaid.render("g", {source})
  .then(r => {{
    document.getElementById("d").innerHTML = r.svg;
    document.body.dataset.done = "1";
  }})
  .catch(e => {{ document.body.dataset.error = String(e); }});
</script></body></html>"""


def main(source_path: str, out_path: str) -> None:
    with open(source_path, encoding="utf-8") as f:
        source = f.read()
    html = PAGE.format(mermaid=MERMAID, config=json.dumps(CONFIG), source=json.dumps(source))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=1.5, viewport={"width": 3000, "height": 1200})
        page.set_content(html)
        page.wait_for_function(
            "document.body.dataset.done || document.body.dataset.error", timeout=30000
        )
        error = page.evaluate("document.body.dataset.error")
        if error:
            raise SystemExit(f"mermaid failed: {error}")
        page.locator("#d").screenshot(path=out_path)
        browser.close()
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
