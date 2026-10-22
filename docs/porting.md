# Porting record

crewforge consolidates four earlier tools by the same author. This page records
how their test suites were carried over, so the claim "the old guarantees still
hold" can be checked rather than trusted. The `academic` recipe, added later,
replaces a fifth project and is recorded [at the end](#academic-from-hermes-mimo-writer):
unlike the other four, most of that project was deliberately not carried over.

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

## `academic` (from hermes-mimo-writer)

[hermes-mimo-writer](https://github.com/gnpa910/hermes-mimo-writer) was a
seven-agent "academic writing pipeline": give it an assignment brief and some
of your own writing, receive a finished, cited essay as a `.docx` that its
README described as "AI-detector-resistant". Read at commit `e8b6015`
(54 tests). It was not modified.

crewforge will not help anyone pass off AI text as their own or evade AI
detectors, so the recipe is a different tool built from the honest parts: it
helps a student plan and improve **their own** work and records what it did so
the student can disclose it.

### Kept

| Old | Now | What changed |
|---|---|---|
| `BriefParserAgent` | `brief` agent (`academic plan`) | Same job. A brief with no title, or a reply in prose, now fails naming `brief` instead of raising a bare `ValueError`. Citation styles are APA 7, IEEE and Harvard (MLA/Chicago dropped for a smaller, tested surface). |
| `OutlineDrafterAgent` | `planner` agent (`academic plan`) | Adds research questions, the kinds of sources to find, and database search queries. The word budget is computed in code so it always adds up to the target (the old prompt asked the model to do the arithmetic). Headings no longer carry the model's own numbering. |
| `sources_hint` | `source_needs`, `search_queries`, `suggested_readings` | Any reading the model proposes is labelled UNVERIFIED, and LIKELY FABRICATED when it has no DOI, URL or valid ISBN. |
| `CitationManagerAgent` | `formatter` agent (`academic cite`) | Inverted: it formats only references the user supplies, may not skip one (the run fails naming `formatter`) or add one (discarded and reported), and any DOI/URL/ISBN it adds is flagged. |
| Localised references heading (en/id/ms/zh) | `--language en\|ms` | Output in English or standard **Malaysian** Malay; every label is in `locales/{en,ms}.yaml`. Malay output is checked against a list of Indonesian forms (`karena`, `-itas`, `dosen`, ...), because the old prompts treated Malay and Indonesian as near-interchangeable. |
| Per-agent token ledger | core `UsageTracker` | Provider-reported numbers only. |

### Dropped, and why

| Old feature | Why it is not in crewforge |
|---|---|
| `AISanitizerAgent` and the `web/` sanitizer demo (`/api/sanitize`) | Their only purpose was to make AI-generated prose "indistinguishable from human academic writing" so detectors (GPTZero, Turnitin AI, Copyleaks) would miss it. That is help with academic misconduct; there is no honest version of it. |
| `ContentDrafterAgent` | It wrote the essay the student would submit, and its prompt told the model to "invent author/year that's plausible" for citations. Ghost-writing plus fabricated citations. `academic feedback` comments on the student's own draft instead, and its reviewers are told not to rewrite. |
| `StyleProfilerAgent` | It fingerprinted the student's past writing so the generated essay would sound like them, which only serves passing generated text off as their own. Feedback on clarity and register of the student's own draft is the honest counterpart. |
| `DocxAssemblerAgent` | It assembled the generated essay into a submission-ready file. With no generated essay there is nothing to assemble; results are Markdown, text or JSON. |
| "Plausible" reference synthesis in `CitationManagerAgent` | The prompt asked for "plausible academic title[s]" and "real-world publishers" for keys the drafter had made up. The module docstring promised a plausibility check that the code never performed. Replaced by the identifier-based labelling above. |
| `estimate` command | Hand-typed token and price heuristics; crewforge reports provider usage only. |
| `health` command, MiMo client, `.env` settings | Covered by the core: the `mimo` provider preset, `crewforge providers`, `crewforge.yaml`. |
| Indonesian (`id`) and Chinese (`zh`) output | Out of scope for now; the owner's audience is Malaysian. Adding a language is a new locale file plus tests. |

### New in the recipe

- `academic feedback`: four reviewers (structure, argument, clarity, citations)
  that return comments tied to a paragraph and an exact quote. The code checks
  each quote against the draft (re-pointing a wrong paragraph number, flagging
  a quote that is not there) and cuts suggestions longer than
  `academic.max_suggestion_words`, so feedback cannot turn into a rewrite. A
  deterministic pass cross-checks in-text citations against the reference list.
- `academic disclose`: an AI-use statement generated without an LLM from the
  usage log that `plan`, `feedback` and `cite` append to
  (`crewforge-academic-log.jsonl`: step, date, model, input file names and
  SHA-256, counts; never content, keys or URLs). It refuses to write a
  statement when nothing was recorded, and ends with a checklist the student
  must confirm (sources checked, text is their own, course allows this use).

### Tests

None of the 54 old tests were carried over. 18 test dropped features
(sanitizer 3, drafter 5, style profiler 4, DOCX assembler 4, the pipeline that
chained them 2) and 10 test the MiMo client and `.env` settings that the core
replaces and tests itself. The other 26 test the old JSON helper and pydantic
models, which were rewritten rather than ported (the core's `parse_json` covers
the helper), and `test_citation_manager_resolves_keys` asserted that invented
references come back as a bibliography, the behaviour that was inverted. The
recipe has its own tests in `tests/recipes/academic/`.

The fabricated-citation guard (`check_source` in
`recipes/academic/citations.py`) was checked by removing it: 6 tests went red,
including `TestFabricationGuard::test_model_source_without_identifier_is_flagged`,
`test_flagged_reading_is_never_presented_as_verified` (CLI) and
`test_plan_budget_readings_and_two_agents`; restoring it made the suite green.

