# OpenSSF Best Practices — answers for the "passing" level

Prepared for registering crewforge at <https://www.bestpractices.dev> (log in with GitHub, "Add project",
repository `https://github.com/aimanmalib/crewforge`). Each answer points at evidence in this repository.
**The badge is not claimed until the project is registered and the form is submitted by the maintainer.**

Base URL for evidence: `https://github.com/aimanmalib/crewforge`

## Basics

| Criterion | Answer | Evidence |
|---|---|---|
| description_good | Met | README first paragraph: what crewforge does and the five recipes. |
| interact | Met | Issues and pull requests on GitHub; [CONTRIBUTING.md](../CONTRIBUTING.md). |
| contribution | Met | [CONTRIBUTING.md](../CONTRIBUTING.md) explains setup, tests and the PR process. |
| contribution_requirements | Met | CONTRIBUTING.md "Rules that keep crewforge honest" and "Commit messages". |
| floss_license / floss_license_osi | Met | MIT ([LICENSE](../LICENSE)), OSI-approved. |
| license_location | Met | `LICENSE` at the repository root. |
| documentation_basics | Met | README: install, quickstart, every recipe with an example, providers, architecture. |
| documentation_interface | Met | `crewforge --help` and `crewforge <recipe> --help`; README recipe sections; library API in README. |
| sites_https | Met | GitHub and PyPI (`https://pypi.org/project/crewforge/`) are HTTPS only. |
| discussion | Met | GitHub issues are searchable, addressable by URL, and open to anyone with a GitHub account. |
| english | Met | All documentation and code comments are in English. |
| maintained | Met | Active commits and releases (see CHANGELOG). |

## Change control

| Criterion | Answer | Evidence |
|---|---|---|
| repo_public / repo_track / repo_interim / repo_distributed | Met | Public git repository on GitHub with full history and pull requests. |
| version_unique / version_semver | Met | SemVer (`0.1.0`, `0.2.0`, …), each a git tag and a GitHub Release. |
| version_tags | Met | Tags `v0.1.0`, `v0.2.0`, … |
| release_notes | Met | [CHANGELOG.md](../CHANGELOG.md) (Keep a Changelog) and GitHub Release notes. |
| release_notes_vulns | N/A (so far) | No publicly known vulnerabilities have been fixed yet; the changelog will name any that are. |

## Reporting

| Criterion | Answer | Evidence |
|---|---|---|
| report_process / report_tracker | Met | GitHub issues with forms (`.github/ISSUE_TEMPLATE/`). |
| report_responses / enhancement_responses | Met | Issues are triaged and labelled by the maintainer (`good first issue`, `help wanted`, `enhancement`). |
| report_archive | Met | GitHub issues are public and archived. |
| vulnerability_report_process | Met | [SECURITY.md](../SECURITY.md) "Reporting a vulnerability". |
| vulnerability_report_private | Met | GitHub private vulnerability reporting is enabled (Security → Report a vulnerability). |
| vulnerability_report_response | Met | SECURITY.md: acknowledgement within 14 days. |

## Quality

| Criterion | Answer | Evidence |
|---|---|---|
| build / build_common_tools | Met | Standard `pyproject.toml` build (`uv build`), installable with `pip install crewforge`. |
| build_floss_tools | Met | Built and tested with free tools only (uv, pip, pytest, ruff, mypy). |
| test / test_invocation | Met | `pytest` (documented in CONTRIBUTING.md); 700+ tests. |
| test_most | Met | Line + branch coverage ~93%, printed in every CI job summary. |
| test_continuous_integration | Met | `.github/workflows/ci.yml` on every push and pull request (Python 3.10–3.14). |
| test_policy | Met | CONTRIBUTING.md rule 2: every new failure path gets a test that would go red if the guard were removed; new recipes ship with tests in `tests/recipes/<name>/` (rule 5). |
| tests_are_added | Met | Recent pull requests add tests with features (e.g. the `academic` recipe). |
| tests_documented_added | Met | CONTRIBUTING.md and the PR template. |
| warnings / warnings_fixed | Met | ruff (explicit rule set) and mypy run in CI; both must pass. |
| warnings_strict | Met | mypy with `check_untyped_defs`, `strict_equality`, `warn_unused_ignores`; ruff fails the build. |

## Security

| Criterion | Answer | Evidence |
|---|---|---|
| know_secure_design / know_common_errors | Met | Keys only from the environment, never written to disk (`init` writes `${VAR}` references); no retry on 401/403; honest-failure rules (CONTRIBUTING.md rules 1–4). |
| crypto_* | N/A | crewforge implements no cryptography; TLS comes from httpx when the provider URL is HTTPS. |
| delivery_mitm | Met | Releases are published to PyPI over HTTPS by GitHub Actions with Trusted Publishing (OIDC) and signed provenance attestations. |
| delivery_unsigned | Met | No unsigned hash is fetched over HTTP. |
| vulnerabilities_fixed_60_days | Met | No unpatched publicly known vulnerabilities; Dependabot alerts and security updates are enabled. |
| vulnerabilities_critical_fixed | Met | As above. |
| no_leaked_credentials | Met | No secrets in the repository; GitHub secret scanning and push protection are enabled. |

## Analysis

| Criterion | Answer | Evidence |
|---|---|---|
| static_analysis | Met | CodeQL (GitHub default setup) on every push and PR, plus ruff and mypy in CI. |
| static_analysis_common_vulnerabilities | Met | CodeQL security queries for Python and GitHub Actions. |
| static_analysis_fixed | Met | Open CodeQL code alerts: none (Scorecard findings are tracked separately). |
| static_analysis_often | Met | Runs on every change. |
| dynamic_analysis | Met (unit/integration level) | The test suite runs every recipe end to end against a fake OpenAI-compatible endpoint; real-provider runs are recorded in the README demos. |
| dynamic_analysis_unsafe | N/A | Python is memory-safe. |
| dynamic_analysis_enable_assertions | Met | Tests run with assertions enabled (pytest default). |
| dynamic_analysis_fixed | Met | Failures found by tests are fixed before merge (CI is required by the branch ruleset). |
