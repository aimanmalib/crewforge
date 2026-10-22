# Security policy

## Reporting a vulnerability

Please report vulnerabilities **privately** through GitHub's
[private vulnerability reporting](https://github.com/aimanmalib/crewforge/security/advisories/new)
(Security tab → "Report a vulnerability"). Do not open a public issue.

Include what you found, how to reproduce it, and the impact you expect. You will
get an acknowledgement within 14 days, and a fix or a decision after that. Fixes for
confirmed vulnerabilities are released as soon as they are ready and named in the CHANGELOG.

## Supported versions

Only the latest release (and `main` before the first release) receives fixes.

## Scope notes

- crewforge sends the code, documents and descriptions you give it to the LLM
  provider you configure. Choose a provider you are allowed to share that data with.
- API keys are read from environment variables and are never written to disk
  by crewforge; `crewforge init` writes `${VAR}` references.
- `crewforge validate DIR` imports the scaffolded project's `main.py` in a
  separate Python process. Only run it on projects you generated or trust.
- Generated code, reviews, answers and articles are model output. Review them
  before you rely on them.
