# Security policy

## Supported versions

This project is on `0.1.0`. Security fixes will be applied to the latest commit on `main` and to the most recent tagged release. Older tags are not supported.

## The read-only invariant

The skill's safety guarantee is that no `az` invocation it makes can mutate Azure state. This is enforced in code by `azure_investigator_core.azcli`:

- 33 write verbs (`update`, `delete`, `create`, `set`, `add`, `remove`, `assign`, `start`, `stop`, `restart`, `deallocate`, `tag update`, `policy assignment`, …) are refused at the subprocess boundary before `az` is invoked.
- 23 unit tests in `packages/azure-investigator-core/tests/test_azcli_refuses_writes.py` cover representative invocation patterns.
- Verb naming across both CLIs reinforces the same property — there is no `apply`, `remediate`, `fix`, `delete` verb anywhere.

**A bypass of this invariant is the most serious class of security bug this project can have.** If you can construct an `az` invocation that mutates state and is not refused by the firewall, please report it via the channel below before disclosing publicly.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.

Instead, use one of:

- **GitHub Security Advisory** (preferred): https://github.com/mindaugasnakrosis/azure-costs-analyzer/security/advisories/new
- Email: `mindaugasm@intelme.ai` with subject line `[security] azure-investigator`.

Include in the report:

- The category (read-only bypass / dependency CVE / credential leak / other).
- A minimal reproduction (CLI invocation, or unit test that demonstrates the issue against the firewall).
- The Azure CLI version and Python version where the issue reproduces.
- Whether you've shared the finding elsewhere.

## What constitutes a security issue here

In rough order of severity:

1. **Read-only firewall bypass.** Any path through the codebase that lets an `az` invocation mutate Azure state.
2. **Credential leak.** The skill is read-only and does not handle credentials directly (it relies on `az` for auth), but report any code path that logs, persists, or transmits authentication material.
3. **Path traversal / unsafe file ops.** Snapshot writes go to a configured root; if you can construct inputs that write outside that root, that's a security bug.
4. **Dependency vulnerabilities.** Reported via Dependabot in the normal flow; high-severity ones get fast-tracked.
5. **Knowledge-corpus tampering.** The corpus is committed text; if you can convince the analyser to load knowledge content from a non-corpus path at runtime, that's an integrity issue.

## What's not a security issue here

- **Slow Azure responses, collector timeouts, or `az` extension misalignment.** These produce structured errors in the manifest, not silent corruption. They're operational issues — open a regular bug report.
- **Stale knowledge documents.** Microsoft updates pages; the verbatim quotes drift. The maintainer-only `scripts/refresh_knowledge.py` surfaces drift; humans review before commit. Stale text isn't a security issue.
- **A finding the analyser produced that turned out to be wrong on your tenant.** That's a calibration issue. Open a regular bug report with the finding's `evidence` block.

## Disclosure timeline

- Acknowledgement within 5 business days of receipt.
- Triage and severity assessment within 14 days.
- A fix or mitigation in `main` within 30 days for critical and high-severity issues; longer for lower severities.
- Public disclosure (advisory + commit + release notes) only after a fix lands, with credit to the reporter unless declined.
