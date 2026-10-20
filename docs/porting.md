# Porting record

crewforge consolidates four earlier tools by the same author. This page records
how their test suites were carried over, so the claim "the old guarantees still
hold" can be checked rather than trusted.

| Source repo | Tests on `main` | Carried over | Dropped | Where they live now |
|---|---|---|---|---|
| [codeguard](https://github.com/aimanmalib/codeguard) | 65 | 65 | 0 | `tests/recipes/review/` |
| [documind](https://github.com/aimanmalib/documind) | 125 | 125 | 0 | `tests/recipes/docs/` |
| [apiforge](https://github.com/aimanmalib/apiforge) | 163 | 151 | 12 | `tests/recipes/api/` |
| [contentforge](https://github.com/aimanmalib/contentforge) | 132 | 132 | 0 | `tests/recipes/content/` |

Counts are from running each repo's suite on its `main` branch on 20 Oct 2026.
Run `pytest --collect-only -q` here for crewforge's current total.

## How tests were carried over

- **Ported**: same assertion, new imports. Agent, pipeline and CLI tests now run
  the real client against a fake HTTP endpoint (`fake_llm` in `tests/conftest.py`)
  instead of mocking internal methods.
- **Re-targeted**: each tool had its own config, client, token tracker and
  exception classes. Those tests now assert the same guarantee against the shared
  core and live in `tests/recipes/<recipe>/test_core_compat.py`, one test per
  original, with a comment naming it where the mapping is not obvious.
  Environment variables moved from `DOCUMIND_*` / `APIFORGE_*` /
  `CONTENTFORGE_*` to `CREWFORGE_*`; MiMo-specific aliases became the `mimo`
  provider preset.
- **Inverted on purpose**: where the old test asserted a silent fallback that was
  itself the bug, the ported test asserts the failure instead.
  - apiforge `test_parse_handles_invalid_json`, `test_parse_non_object_json_falls_back`,
    `test_prompt_specifies_json_shape`: an unparseable or endpoint-less parser reply
    now fails naming `parser` (it used to become an empty spec that scored 100/100).
  - apiforge `test_generate_routes`, `test_generate_models`, `test_generate_apikey`,
    `test_generate_docs_fallback`: a reply without code (or empty docs) now fails
    naming the agent instead of reusing the template.
  - documind `test_summary_structure`, apiforge `test_summary`: the usage summary
    must *not* contain projected or estimated token figures.
  - codeguard `test_markdown_report_shows_agent_output`: a run with a failed
    reviewer only exits 0 with `--allow-partial`.

## Dropped (12, all apiforge)

| Tests | Reason |
|---|---|
| `test_web_api.py` (10) | apiforge's FastAPI web dashboard is not part of crewforge, which is a CLI and library. |
| `test_cli.py::test_stats` | The `stats` command printed hand-typed daily token estimates. crewforge reports provider-reported usage only. |
| `test_token_tracker.py::test_daily_estimates` | Same: the `DAILY_ESTIMATES` table was removed. |

## Honest-failure guards and the sabotage check

Each guard was removed temporarily while building crewforge, the full suite was
run, and the guard was restored:

| Guard removed | Tests that went red |
|---|---|
| Blank-completion check in `Agent.ask` (`core/agent.py`) | 15, including `test_agent_ask_rejects_blank_completion`, the docs CLI failure tests and `test_blank_reply_fails_the_run_naming_the_agent[ask]` / `[summarize]` |
| Empty-result check in `Crew._checked` (`core/crew.py`) | 7: `test_crew_step_rejects_empty_result[*]`, `test_crew_parallel_rejects_empty_result` |
| "Checked 0 operations" rule in the api validator | `test_paths_without_operations_score_nothing` |

With the first guard removed, `review`, `scaffold` and `write` still failed
because their agents must return parseable JSON (a second, independent guard);
`ask` and `summarize` would have reported success with an empty answer.
