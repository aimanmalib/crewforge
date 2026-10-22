# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-22

### Added
- `academic` recipe: `crewforge academic plan | feedback | cite | disclose`, an
  honest academic-writing assistant that replaces
  hermes-mimo-writer (an earlier, now retired project). It plans
  from a brief (research questions, outline, a word budget that adds up,
  sources to find), comments on the user's own draft without rewriting it,
  formats references the user supplies (APA 7, IEEE, Harvard) without adding
  any, and writes an AI-use statement from a record of the steps it ran.
  Output in English or Malaysian Malay (`--language en|ms`). Sources the model
  proposes are labelled UNVERIFIED, or LIKELY FABRICATED without a DOI, URL or
  ISBN; nothing is ever shown as verified. The old project's essay drafting,
  style mimicry and "AI-detector" sanitiser were deliberately dropped; see
  [docs/porting.md](docs/porting.md#academic-from-hermes-mimo-writer).
- `academic:` section in `crewforge.yaml` (language, citation style, log file,
  input and suggestion limits).

## [0.1.0] - 2026-10-22

First version: one framework replacing four separate tools
([codeguard](https://github.com/aimanmalib/codeguard),
[documind](https://github.com/aimanmalib/documind),
[apiforge](https://github.com/aimanmalib/apiforge),
[contentforge](https://github.com/aimanmalib/contentforge)).

### Added
- Shared core: provider presets (OpenAI, OpenRouter, Groq, DeepSeek, Together,
  Mistral, Ollama, llama.cpp, Xiaomi MiMo, custom), one OpenAI-compatible client,
  `Agent` and `Crew` (sequential steps and parallel stages), structured-output
  parsing, provider-reported usage accounting, and a typed error hierarchy.
- Honest failure as a core rule: blank, unparseable or empty agent output fails
  the run with exit code 1 and names the agent.
- Recipes: `review`, `ingest` / `ask` / `summarize`, `scaffold` / `validate`,
  `write`; plus `providers` and `init`.
- `validate DIR` imports a scaffolded app in a subprocess and checks that it
  serves every operation in its `openapi.json`.
- Extras: `crewforge[docs]` (PDF/DOCX), `crewforge[api]` (FastAPI app check).
- CI on Python 3.10–3.13, and a release workflow that publishes to PyPI via
  Trusted Publishing when a GitHub Release is published.

### Changed (compared with the four earlier tools)
- Configuration env vars are `CREWFORGE_PROVIDER`, `CREWFORGE_API_KEY`,
  `CREWFORGE_BASE_URL` and `CREWFORGE_MODEL`, plus each provider's own key
  variable (e.g. `OPENAI_API_KEY`).
- Unknown provider names are reported instead of silently using OpenAI's URL.
- See [docs/porting.md](docs/porting.md) for every behaviour that changed on
  purpose and how the earlier test suites were carried over.

### Removed
- apiforge's web dashboard and the illustrative token "stats"/daily estimates.
