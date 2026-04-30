# Contributing to azure-investigator

Thanks for considering a contribution. The repo is small and the discipline behind it is non-negotiable: every cost rule must cite a published authority, every saving must be a range with a stated assumption, and the read-only contract is enforced in code, not in docs.

This page covers the broader flow. The mechanics of authoring a new cost rule live in [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md).

## Before opening a PR

1. **Discuss material changes in an issue first.** New rules, new collectors, knowledge-corpus changes, schema changes, and CLI verb additions all benefit from a short prior thread. Trivial fixes (typos, doc nits, dependency bumps) can go straight to PR.
2. **Run the suite locally.** `uv sync --all-packages && uv run pytest` should pass. Lint + format must be clean: `uv run ruff check . && uv run ruff format --check .`.
3. **Don't bypass the architectural firewall.** Any new Azure call must route through `azure_investigator_core.azcli.run_json`. Any new rule must declare `KNOWLEDGE_REFS` and cite a `knowledge/*.md` document. Any savings figure must be a `SavingsRange` with a non-empty `assumption`.

## Adding a cost rule

The full discipline is in [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md). The short version:

1. **Author the knowledge document first.** A `.md` file under `packages/azure-cost-investigator/src/azure_cost_investigator/knowledge/`, with frontmatter (source URL, retrieval date, content SHA-256, `cited_by`) and verbatim quotes from the upstream authority.
2. **Add the rule module** at `packages/azure-cost-investigator/src/azure_cost_investigator/rules/<rule_id>.py`. Set `RULE_ID`, `KNOWLEDGE_REFS`, write `evaluate(ctx) -> Iterable[Finding]`. Handle the missing-collector branch via `info_missing_data`.
3. **Register it** in `rules/__init__.py` (`RULE_MODULES = (..., "<rule_id>")`).
4. **Write tests** at `packages/azure-cost-investigator/tests/test_rules_<rule_id>.py`. Minimum surface: positive case, negative case, missing-collector → Info, knowledge_refs present.
5. **Run the suite**, open the PR.

## Adding a collector

Adding a new `az` query family to the snapshot:

1. **Create the module** at `packages/azure-investigator-core/src/azure_investigator_core/collectors/<name>.py`. Export `NAME` and `collect(subscription_id) -> CollectorOutput`. Route the `az` call through `safe_run_json` (which wraps the read-only firewall).
2. **Register the name** in `COLLECTOR_MODULES` in the package `__init__.py`.
3. **Update tests** in `test_collectors.py` if the dispatcher contract changes.
4. **If a rule depends on the new collector, add the missing-collector branch.** A rule should always handle a `None` payload via `info_missing_data` rather than crashing.

## Updating the knowledge corpus

Knowledge files are committed text. Updates land via:

- A **maintainer-driven re-fetch** with `uv run python scripts/refresh_knowledge.py`. The script records `upstream_sha256` separately from the body's own `source_sha256` so drift is visible per-file. The verbatim quoted body is *not* auto-rewritten — a human reviews the diff before commit.
- An **opened issue** describing the upstream change (URL, what specifically changed, which rules are affected) is preferred over a silent edit. Quotes are verbatim by contract; paraphrases hide changes that need calibration.

## PR review criteria

- Tests pass on Python 3.11 and 3.12 (CI enforces).
- `ruff check` clean and `ruff format --check` clean.
- For a new rule: knowledge document committed in the same PR as the rule + tests.
- For a savings change: the assumption string is updated to reflect the new band.
- For an architectural change to the read-only firewall: the test count for `test_azcli_refuses_writes.py` does not decrease.
- Commit messages follow the build-style of `git log --oneline` so the history reads as a build narrative, not a noise stream. See existing commits for shape.

## Code style

Ruff handles formatting (line length 100, double quotes, `py311` target). Imports are sorted by isort rules. Type hints required on public function signatures; tests can be looser. Docstrings on rule modules + collectors should state the authority and the severity / confidence rationale up front.

No emoji in code or docs unless requested. No comments restating what the code does — only WHY when a hidden constraint or non-obvious workaround is involved.

## Reporting bugs

Open a GitHub issue using the bug-report template. Include:

- The exact `az` version (`az version`) and Azure CLI extensions installed.
- The relevant section of `manifest.yaml` (specifically `collector_results` for the failing collector).
- The CLI command you ran and the full stderr output.
- Whether the issue reproduces with `--collector <one-name>` to narrow which family is affected.

## Reporting security issues

Don't open a public issue. See [`SECURITY.md`](SECURITY.md).

## Code of conduct

Be specific, be direct, be constructive. The same standard the rules hold themselves to: cite, don't claim. We're aiming for the £1000/day senior-contractor calibre in the *content* and the persona — so review style follows.
