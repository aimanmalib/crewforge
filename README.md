# crewforge

**One crew of LLM agents, five recipes — code review, document Q&A, API scaffolding, content and honest academic-writing help — on any OpenAI-compatible provider, and it fails loudly instead of pretending.**

[![CI](https://github.com/aimanmalib/crewforge/actions/workflows/ci.yml/badge.svg)](https://github.com/aimanmalib/crewforge/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/crewforge)](https://pypi.org/project/crewforge/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/aimanmalib/crewforge/badge)](https://scorecard.dev/viewer/?uri=github.com/aimanmalib/crewforge)
![Python 3.10–3.14](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

```bash
crewforge review src/                                  # six reviewers + a summary
crewforge ask handbook.pdf -q "How many leave days?" --verify
crewforge scaffold "Todo API: list, create and delete todos" -o todo-api
crewforge write "Why unit tests matter" -f markdown -f html
crewforge academic feedback draft.md --brief brief.md --language ms
```

<p align="center">
  <img src="https://raw.githubusercontent.com/aimanmalib/crewforge/main/docs/demo/review.gif" alt="Terminal demo: crewforge review on a login function finds the SQL injection (CWE-89) as critical and requests changes" width="900">
</p>
<p align="center"><sub>A real run of <code>crewforge review</code>: seven agents, ~25 s, provider-reported tokens. Recorded with <a href="https://github.com/charmbracelet/vhs">VHS</a> from <a href="https://github.com/aimanmalib/crewforge/blob/main/docs/demo/review.tape"><code>docs/demo/review.tape</code></a> using Gemini 3.8 Flash through an OpenAI-compatible gateway (the <code>custom</code> provider). The wait for the model is shown in full.</sub></p>

## Why one crew, many recipes

crewforge started as four separate command-line tools —
[codeguard](https://github.com/aimanmalib/codeguard),
[documind](https://github.com/aimanmalib/documind),
[apiforge](https://github.com/aimanmalib/apiforge) and
[contentforge](https://github.com/aimanmalib/contentforge). Each had its own copy
of the same scaffold: provider presets, an HTTP client, an agent base class, an
asyncio pipeline and a token tracker. Running all four against a real model
showed the copies had drifted and that each hid its failures differently:

- codeguard reported success when every review came back empty;
- documind's `ask` command was a stub;
- apiforge scored a spec with **no endpoints** 100/100;
- contentforge wrote the real API key into its YAML file, and sent `${OPENAI_API_KEY}` literally as the key.

crewforge keeps one core — so a fix lands once — and turns each tool into a
*recipe*: a set of agents plus the steps that connect them. The same core rules
apply to every recipe: non-streaming requests, bounded retries, usage numbers
taken only from the provider, keys only from the environment, and no run that
reports success when an agent produced nothing.

A fifth recipe, `academic`, replaces a standalone "academic writing pipeline"
that drafted essays and marketed itself as AI-detector-resistant. Only the
honest parts were kept; see [docs/porting.md](https://github.com/aimanmalib/crewforge/blob/main/docs/porting.md#academic-from-hermes-mimo-writer).

## 60-second quickstart

```bash
pip install crewforge
# optional extras: PDF/DOCX ingestion, and the FastAPI app check in `validate`
pip install "crewforge[docs,api]"
# or the latest main: pip install "crewforge @ git+https://github.com/aimanmalib/crewforge.git"

export OPENAI_API_KEY=sk-...          # or any provider below
crewforge providers                   # list presets and the variable each one reads
crewforge review path/to/file.py
```

Any provider works the same way:

```bash
export GROQ_API_KEY=...
crewforge --provider groq review src/

# any other OpenAI-compatible server (vLLM, LM Studio, a gateway, ...)
crewforge --provider custom --base-url http://localhost:8000/v1 --model my-model ask notes.md -q "..."
```

`crewforge init` writes a `crewforge.yaml` you can pass with `--config`; the key
in it is a `${VAR}` reference, never the value.

## Recipes

Each example below was run against a real model (a Gemini Flash model behind an
OpenAI-compatible router) while building crewforge. Output is abbreviated; token
tables are trimmed to their totals.

| Command | Agents | What you get |
|---|---|---|
| `review PATH` | security, style, complexity, logic, testing, documentation (parallel) → summary | Findings by severity, a decision and a score; `-f json` for CI |
| `ingest FILES` | ingester, indexer (no LLM) | How each file was parsed and chunked |
| `ask FILES -q Q [--verify] [--rerank]` | retriever → answerer → fact-checker | An answer with `[Source N]` citations and a claim-by-claim verdict |
| `summarize FILES` | summarizer | Summary and key points per document |
| `scaffold "DESCRIPTION"` | parser → schema → router, model, auth, test_gen, doc_gen (parallel) → validator | A runnable FastAPI project with `openapi.json`, tests and docs |
| `validate PATH` | validator (no LLM) | Spec check; for a project directory, also checks the app serves every spec operation |
| `write "TOPIC"` | research → outline → writer → SEO → editor ⇄ quality → translator → publisher | Article as Markdown/HTML/JSON, social snippets, a usage file |
| `academic plan BRIEF` | brief → planner | Research questions, an outline with a word budget that adds up, sources to find, suggested readings labelled UNVERIFIED |
| `academic feedback DRAFT` | structure, argument, clarity, citations (parallel) + a citation cross-check (no LLM) | Comments tied to quoted text in your draft; no rewriting |
| `academic cite REFS` | formatter | Your references in APA 7, IEEE or Harvard; nothing added, missing details listed |
| `academic disclose` | none (no LLM) | An AI-use statement built from the record of what the tool did |

### `review`

```text
$ crewforge review app.py -f markdown -o review.md      # app.py builds SQL with an f-string
# crewforge review

**Decision:** REQUEST_CHANGES · **Quality score:** 25/100

### Top issues
1. Critical SQL injection vulnerability caused by string interpolation in database query (CWE-89)
2. Missing unit tests covering basic retrieval, missing records, and inputs with quotes
3. Missing docstring and incomplete type annotations for the 'name' parameter and return value

### Critical (3)
- **SQL Injection via string interpolation** (line 4) [CWE-89] — _security_: ...
  - Fix: conn.execute('SELECT * FROM users WHERE name = ?', (name,)).fetchall()
...
total   7 calls   22,366 tokens (provider-reported)
```

### `ask` and `summarize`

<p align="center">
  <img src="https://raw.githubusercontent.com/aimanmalib/crewforge/main/docs/demo/ask.gif" alt="Terminal demo: crewforge ask --verify answers two questions about a short project brief with [Source N] citations; the second answer says the document does not give the cost, and both answers are fact-checked claim by claim" width="900">
</p>
<p align="center"><sub>A real run of <code>crewforge ask --verify</code>: the answerer cites the passages it used as <code>[Source N]</code>, a second agent checks every claim against those passages, and the question the document does not answer is answered as such. Provider-reported tokens. Recorded with <a href="https://github.com/charmbracelet/vhs">VHS</a> from <a href="https://github.com/aimanmalib/crewforge/blob/main/docs/demo/ask.tape"><code>docs/demo/ask.tape</code></a> (the document is invented) using Gemini 3.8 Flash through an OpenAI-compatible gateway (the <code>custom</code> provider). The wait for the model is shown in full.</sub></p>

```text
$ crewforge ask kestrel.md -q "How many sensors does Project Kestrel use, and who leads it?" --verify --export session.md
✓ ingested kestrel.md (1 chunks)
Q: How many sensors does Project Kestrel use, and who leads it?
Project Kestrel uses 42 water-level sensors deployed along the Sarawak River, and the project is
led by Nadia Rahman [Source 1].
Confidence: high
Verification: verified (2/2 claims verified)
Exported to: session.md
total   2 calls   5,053 tokens (provider-reported)

$ crewforge summarize kestrel.md --length short
Summary: Project Kestrel is a river-monitoring pilot initiative launched in March 2025 by the
Kuching office under the leadership of Nadia Rahman. ...
total   1 call    2,821 tokens (provider-reported)
```

### `scaffold` and `validate`

```text
$ crewforge scaffold "Todo API: list todos, create a todo with a title, mark a todo done, and delete a todo. Bearer auth." -o todo-api
Wrote 11 files
todo-api/
  .env.example  API.md  Dockerfile  auth.py  main.py  models.py  openapi.json
  requirements.txt  routes.py  tests/conftest.py  tests/test_api.py
Validation: valid · 100/100 (4 operation(s) checked, 0 error(s), 0 warning(s))
App check: OK — app serves 5 route(s)
total   5 calls   20,711 tokens (provider-reported)

$ cd todo-api && pytest -q tests
4 passed

$ crewforge validate todo-api            # offline, no key needed
Validation: valid · 100/100 (4 operation(s) checked, 0 error(s), 0 warning(s))
App check: OK — app serves 5 route(s)
```

The first real run of this recipe produced a project whose own smoke test failed
(`DELETE /todos/1` correctly answered 404 and the generated test did not allow
it); that was fixed with a regression test before this output was taken.

### `write`

```text
$ crewforge write "Why unit tests matter" --words 300 --no-seo --max-iter 1 -f markdown -f html -o article
╭──────────── crewforge write — Why unit tests matter ────────────╮
│ Article: 711 words · quality score 88/100                        │
│ Files:                                                           │
│   article/why-unit-tests-matter.md                               │
│   article/why-unit-tests-matter.html                             │
│   article/why-unit-tests-matter.publisher.json                   │
│ Metrics: article/metrics/20261020_095052.json                    │
╰──────────────────────────────────────────────────────────────────╯
total   6 calls   35,351 tokens (provider-reported)
```

Two honest caveats from that run: the model wrote more than twice the requested
length (`--words` is a target given to the agents, not a hard limit), and the
research agent has no web access, so statistics it quotes come from the model's
training data. Review articles before publishing them.

### `academic`

An honest assistant for a student's or researcher's **own** work. It plans,
comments and formats; it does not write the assignment, does not invent
references, and has no "humanise" or AI-detector-evasion feature. Output in
English or Malaysian Malay (`--language en|ms`; Malay output is checked for
Indonesian forms such as *karena* or *kualitas*). Every step is recorded
(file names and hashes, never content or keys) so `disclose` can write the
AI-use statement many universities now ask for.

<p align="center">
  <img src="https://raw.githubusercontent.com/aimanmalib/crewforge/main/docs/demo/academic.gif" alt="Terminal demo: crewforge academic feedback --language ms comments in Malay on a student's essay draft, quoting the sentences it refers to, then a no-AI citation check lists (Lim, 2024) as cited in the text but missing from the reference list" width="900">
</p>
<p align="center"><sub>A real run of <code>crewforge academic feedback --language ms</code> on a short essay draft in Malay. Each comment quotes the student's own sentence and suggests a fix; nothing is rewritten. The citation check after it uses no AI: it finds <em>(Lim, 2024)</em> cited in the text but missing from the reference list. Only the <code>argument</code> reviewer is run so the result fits on one screen. Recorded with <a href="https://github.com/charmbracelet/vhs">VHS</a> from <a href="https://github.com/aimanmalib/crewforge/blob/main/docs/demo/academic.tape"><code>docs/demo/academic.tape</code></a> (draft, brief and reference are invented) using Gemini 3.8 Flash through an OpenAI-compatible gateway (the <code>custom</code> provider). The wait for the model is shown in full.</sub></p>

```text
$ crewforge academic plan brief.md -f markdown          # a 1,200-word TSL3013 essay brief
# Assignment plan: Regulated Integration over Prohibition: ...
- **Target length:** 1,200 words
- **Citation style:** APA 7th edition
## Research questions
1. What pedagogical benefits does generative AI offer secondary school students completing homework tasks?
...
| # | Section | Words | Purpose |
| 1 | Introduction | 150 | ... |   ...   Total: 1,200 words
## Suggested readings (UNVERIFIED)
> The AI proposed these. They may not exist, or may not say what is claimed. ...
- ⚠ **UNVERIFIED: proposed or altered by the AI, check it** — Holmes, W., & Tuomi, I. (2022). ...
total   2 calls   9,034 tokens (provider-reported)

$ crewforge academic feedback draft.md --brief brief.md -f markdown
## Argument
- **Paragraph 2** (major): “Everyone knows that tuition in Malaysia is very expensive.”
  - This is an unsupported generalization and an informal assertion rather than an evidence-based academic claim.
  - *Suggestion:* Replace the appeal to common knowledge with scholarly evidence or empirical data ...
## Citation check (no AI)
**Cited in the text but not in the reference list:**
- Lim, 2024
total   4 calls   17,892 tokens (provider-reported)

$ crewforge academic cite refs.txt --style ieee --language ms -f markdown
[4] W. Holmes, M. Bialik, and C. Fadel, *Artificial Intelligence in Education: ...*. Center for Curriculum Redesign, 2019, ISBN: 978-1-7941-1293-0.
  - ⚠ nombor semak ISBN salah: 9781794112930
  - Butiran yang perlu ditambah: tempat penerbitan

$ crewforge academic disclose --language ms             # no LLM, no key
## Pernyataan Penggunaan AI
Saya menggunakan crewforge academic (versi 0.1.0), sebuah alat berbantukan AI, dengan model gemini-3.8-flash (melalui gateway serasi OpenAI), bagi bahagian tugasan berikut:
- 22 Oktober 2026: Perancangan: alat ini menukar taklimat tugasan (brief-ms.md) kepada 3 soalan kajian, rangka 5 bahagian dan peruntukan perkataan. ...
```

How sources are labelled — there is no "verified" status, because the tool
cannot check that a source exists:

| Source | Label |
|---|---|
| You supplied it | *supplied by you (not checked online)* |
| The model proposed it, with a DOI, URL or valid ISBN | **UNVERIFIED** — check it |
| The model proposed it with none of those | **LIKELY FABRICATED** |
| The model added a DOI/URL/ISBN to a reference you supplied | **UNVERIFIED**, naming the added identifier |

A DOI the model proposes can be made up too, which is why even those stay
unverified. All text the student sees lives in
`src/crewforge/recipes/academic/locales/{en,ms}.yaml`; defaults (language,
style, log file, input size, suggestion length) are the `academic:` section of
`crewforge.yaml`.

## Providers

The table is checked against the code by `tests/test_readme.py`.

| Name | Provider | Base URL | Default model | Key variable | Auth |
|---|---|---|---|---|---|
| `openai` | OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | `OPENAI_API_KEY` | Bearer |
| `openrouter` | OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` | `OPENROUTER_API_KEY` | Bearer |
| `groq` | Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | `GROQ_API_KEY` | Bearer |
| `deepseek` | DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | `DEEPSEEK_API_KEY` | Bearer |
| `together` | Together AI | `https://api.together.xyz/v1` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | `TOGETHER_API_KEY` | Bearer |
| `mistral` | Mistral | `https://api.mistral.ai/v1` | `mistral-small-latest` | `MISTRAL_API_KEY` | Bearer |
| `ollama` | Ollama (local) | `http://localhost:11434/v1` | `llama3.1` | `OLLAMA_API_KEY` (optional) | Bearer |
| `llamacpp` | llama.cpp server (local) | `http://localhost:8080/v1` | `local` | `LLAMACPP_API_KEY` (optional) | Bearer |
| `mimo` | Xiaomi MiMo | `https://token-plan-sgp.xiaomimimo.com/v1` | `mimo-v2.5-pro` | `MIMO_API_KEY` | `api-key` header |
| `custom` | Any OpenAI-compatible endpoint | set `--base-url` / `CREWFORGE_BASE_URL` | set `--model` / `CREWFORGE_MODEL` | `CREWFORGE_API_KEY` (optional) | Bearer |

Resolution order for the key, base URL and model: command-line flag or
`crewforge.yaml` → `CREWFORGE_API_KEY` / `CREWFORGE_BASE_URL` / `CREWFORGE_MODEL`
→ the provider's own variables (e.g. `OPENAI_BASE_URL`) → the preset default.
Pick the provider with `--provider` or `CREWFORGE_PROVIDER`; the default is `openai`.
An unknown provider name is a configuration error, not a silent fallback.

## Architecture

<p align="center"><img src="https://raw.githubusercontent.com/aimanmalib/crewforge/main/docs/architecture.png" alt="Architecture: the CLI dispatches to five recipes; each recipe builds a Crew of Agents on the shared core (parsing, LLMClient, LLMConfig, UsageTracker), which talks to any OpenAI-compatible provider over /chat/completions" width="100%"></p>

<sub>Source: [docs/architecture.mmd](https://github.com/aimanmalib/crewforge/blob/main/docs/architecture.mmd) (re-render with `scripts/render_architecture.py`).</sub>

- **`core/client.py`** — one async client. It always sends `"stream": false`,
  retries only HTTP 429, 5xx and network/timeout errors (with capped exponential
  backoff that honours `Retry-After`), and fails on the first 401/403/4xx with a
  message naming the variable to fix. The key is only ever a request header.
- **`core/agent.py`** — an agent is a role, a system prompt and per-agent
  sampling defaults. `ask()` records usage and raises if the reply is blank;
  `ask_json()` additionally requires parseable JSON (optionally a pydantic schema).
- **`core/crew.py`** — runs agents as sequential steps or parallel stages and
  turns any failure into a `CrewFailedError` that lists every failed agent.
- **`core/usage.py`** — per-agent calls, tokens, retries and latency, taken from
  the provider's `usage` object. Calls without usage are counted as "not reported",
  never estimated.

Use the core directly:

```python
import asyncio
from crewforge.core import Agent, Crew, LLMConfig


class Haiku(Agent):
    name = "poet"
    system_prompt = "You write one haiku. Nothing else."


async def main():
    async with Crew("demo", LLMConfig(provider="groq")) as crew:
        reply = await crew.step("poet", crew.agent(Haiku).ask("autumn in Kuching"))
        print(reply.content, crew.tracker.one_line())


asyncio.run(main())
```

## Honest failure

A run whose agents return empty or unparseable output, or a validator that
checked nothing, **fails with exit code 1 and names the agent**. It never prints
a success message over a hollow result.

```text
$ crewforge ask kestrel.md -q "Who leads Project Kestrel?"        # with a wrong key
error: docs failed
  ✗ agent 'answerer' (http): HTTP 401 from <base-url> (authentication failed — check OPENAI_API_KEY): API key required for remote API access

$ crewforge validate empty-spec.json
Validation: INVALID · 0/100 (0 operation(s) checked, 1 error(s), 0 warning(s))
  ERROR: No endpoints defined (paths is empty)
```

| Situation | Before (the earlier tools) | crewforge |
|---|---|---|
| Every reviewer returns nothing | "Review Complete!", exit 0 | exit 1, names each reviewer |
| A reviewer answers in prose | treated as a review | exit 1, `agent 'style' (parse)` |
| Parser returns no endpoints | empty spec scored 100/100 | exit 1, names `parser` |
| Spec has paths but no operations | scored | score 0, invalid, exit 1 |
| Quality agent answers in prose | score 0, loop burns every round | exit 1 after one round, names `quality` |
| Quality never reaches the threshold | article published | exit 1 unless `--accept-below-threshold` |
| Question matches no passage | model asked to answer from nothing | exit 1, names `retriever`, no LLM call |
| Generated code does not compile | template silently reused | exit 1, names the agent |
| Model proposes a reference with no DOI/URL/ISBN | hermes-mimo-writer put invented "plausible" references in the bibliography | labelled LIKELY FABRICATED, never verified |
| Formatter skips a reference you supplied | n/a | exit 1, names `formatter` |
| `disclose` finds no recorded AI use | n/a | exit 1, no statement written |

Exit codes: `0` success · `1` run failed (agent, validator or provider) · `2`
usage or configuration error (bad flag, unknown provider, missing key).

The guards are covered by tests that were checked by removing each guard and
watching them fail; see [docs/porting.md](https://github.com/aimanmalib/crewforge/blob/main/docs/porting.md#honest-failure-guards-and-the-sabotage-check).

## How this was built

crewforge was built with AI coding assistance (Claude Code) under the
direction of its author, Muhammad Aiman. It consolidates four earlier tools by
the same author — [codeguard](https://github.com/aimanmalib/codeguard),
[documind](https://github.com/aimanmalib/documind),
[apiforge](https://github.com/aimanmalib/apiforge) and
[contentforge](https://github.com/aimanmalib/contentforge) — whose test suites
were carried over into this repository (see [docs/porting.md](https://github.com/aimanmalib/crewforge/blob/main/docs/porting.md)
for what was ported, re-targeted at the shared core, or dropped and why).

The evidence that it works is meant to be checkable: the test suite (run
`pytest`; it needs no key and no network), CI on Python 3.10–3.14, and the
real-provider runs shown above, two of which found bugs that were fixed with
tests before the output was recorded.

## Contributing

See [CONTRIBUTING.md](https://github.com/aimanmalib/crewforge/blob/main/CONTRIBUTING.md). In short: `uv sync --extra dev --extra docs`
(versions from the committed `uv.lock`, as in CI), `uv run pytest`,
`uv run ruff check . && uv run ruff format --check .`, and every new failure path
needs a test that fails if the guard is removed.

## Security

Please report vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/aimanmalib/crewforge/security/advisories/new).
See [SECURITY.md](https://github.com/aimanmalib/crewforge/blob/main/SECURITY.md) for scope notes (what is sent to your provider,
and what `validate` executes).

## License

[MIT](https://github.com/aimanmalib/crewforge/blob/main/LICENSE) © Muhammad Aiman

---

Built by [Sasa Teguh](https://sasateguh.com) · Malaysia
