"""Code generator with Jinja2 templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


class CodeGenerator:
    """Generate code from Jinja2 templates."""

    def __init__(self, template_dir: str | Path | None = None) -> None:
        td = template_dir or Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(td)), trim_blocks=True, lstrip_blocks=True
        )

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        tpl = self.env.get_template(template_name)
        return tpl.render(**context)

    def render_fastapi_main(self, title: str, routes: list[str]) -> str:
        return self.render("fastapi_main.j2", {"title": title, "routes": routes})

    def render_route(self, path: str, method: str, func_name: str, params: list[str]) -> str:
        return self.render(
            "route.j2",
            {"path": path, "method": method, "func_name": func_name, "params": params},
        )

    def render_model(self, name: str, fields: list[dict[str, Any]]) -> str:
        return self.render("model.j2", {"name": name, "fields": fields})

    def render_test(self, test_name: str, method: str, path: str) -> str:
        return self.render("test.j2", {"test_name": test_name, "method": method, "path": path})
