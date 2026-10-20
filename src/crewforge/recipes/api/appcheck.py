"""Optional check that a scaffolded app really serves the routes its spec promises.

Runs ``from main import app`` in a separate Python process (cwd = the project)
so the generated code never executes inside crewforge itself. Needs FastAPI
(``pip install 'crewforge[api]'``); without it the check is skipped and says so.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The app's own OpenAPI document is the stable way to list what it serves
# (FastAPI's internal route objects change shape between releases).
_PROBE = (
    "import json, sys; sys.path.insert(0, '.'); from main import app; "
    "print(json.dumps(sorted([m.upper(), p] for p, ops in app.openapi()['paths'].items() "
    "for m in ops if m in ('get', 'post', 'put', 'patch', 'delete'))))"
)


@dataclass
class AppCheck:
    ran: bool
    errors: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors


def spec_operations(spec: dict[str, Any]) -> set[tuple[str, str]]:
    servers = spec.get("servers") or [{}]
    base = str(servers[0].get("url", "") if isinstance(servers[0], dict) else "").rstrip("/")
    ops = set()
    for path, methods in (spec.get("paths") or {}).items():
        for method in methods or {}:
            if method in ("get", "post", "put", "patch", "delete"):
                ops.add((method.upper(), base + path))
    return ops


def check_app(project: str | Path, spec: dict[str, Any], timeout: float = 60) -> AppCheck:
    project = Path(project)
    if not (project / "main.py").exists():
        return AppCheck(False, note="no main.py: app check skipped")
    if importlib.util.find_spec("fastapi") is None:
        return AppCheck(
            False, note="FastAPI not installed: app check skipped (pip install 'crewforge[api]')"
        )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return AppCheck(True, [f"importing main.app took longer than {timeout:.0f}s"])
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["unknown error"])[-1]
        return AppCheck(True, [f"cannot import main.app: {last}"])
    served = {(m, p) for m, p in json.loads(proc.stdout)}
    missing = sorted(spec_operations(spec) - served)
    errors = [f"spec operation {m} {p} is not served by the app" for m, p in missing]
    return AppCheck(True, errors, note=f"app serves {len(served)} route(s)")
