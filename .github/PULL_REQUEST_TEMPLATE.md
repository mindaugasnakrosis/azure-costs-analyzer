<!-- Thanks for the PR. Keep the description tight. -->

## What this PR does

<!-- One paragraph. Lead with the user-visible change. -->

## Why

<!-- The problem this solves, or the upstream motivation. Link to the issue if there is one. -->

## How

<!-- Approach and any non-obvious tradeoffs. Not a summary of the diff. -->

## Checklist

- [ ] Tests pass locally (`uv run pytest`)
- [ ] Lint + format clean (`uv run ruff check . && uv run ruff format --check .`)
- [ ] If a new rule: knowledge document committed in this PR, `KNOWLEDGE_REFS` declared, missing-collector branch handled, tests cover positive / negative / missing-collector cases
- [ ] If a new collector: routes through `azcli.run_json` (read-only firewall), registered in `COLLECTOR_MODULES`
- [ ] If a savings change: `SavingsRange.assumption` updated to reflect the new band
- [ ] If touching `azcli.py`: `test_azcli_refuses_writes.py` count did not decrease
- [ ] No `apply` / `remediate` / `fix` / `delete` verbs introduced
- [ ] Commit message matches the build-narrative style of `git log --oneline`

## Related issue

<!-- "Fixes #123" or "Closes #123" if applicable. -->
