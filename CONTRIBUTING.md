# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Set up

```bash
git clone https://github.com/aimanmalib/crewforge
cd crewforge
python -m venv .venv && . .venv/bin/activate   # or: uv venv
pip install -e ".[dev,docs]"
pytest
ruff check . && ruff format --check .
```

The test suite needs no API key and no network: agent, pipeline and CLI tests
run the real client against a fake OpenAI-compatible endpoint (the `fake_llm`
fixture in `tests/conftest.py`).

## Rules that keep crewforge honest

1. **A failure is never a success.** If an agent can return nothing useful, the
   run must exit non-zero and name the agent. Go through `Agent.ask` /
   `Agent.ask_json` and `Crew.step` / `Crew.parallel`; do not catch an agent's
   exception and substitute a default.
2. **Every new failure path gets a test** that would go red if the guard were
   removed.
3. **No invented numbers.** Token counts come from the provider's `usage`
   object. Do not add estimates, projections or benchmark figures.
4. **No secrets on disk.** Keys come from the environment; anything written to a
   file uses `${VAR}` references.
5. **A new recipe** lives in `src/crewforge/recipes/<name>/` with its own
   `cli.py` exporting `commands`, and its tests in `tests/recipes/<name>/`.
   Say in the PR which real provider and model you tried it against.

## Commit messages

Describe what changed and why in the imperative ("Fail review when the summary
agent returns prose"), not "update files".
