# azure-investigator

[![tests](https://github.com/mindaugasnakrosis/azure-costs-analyzer/actions/workflows/test.yml/badge.svg)](https://github.com/mindaugasnakrosis/azure-costs-analyzer/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-DE5FE9.svg)](https://docs.astral.sh/uv/)

**Read-only Azure cost & FinOps audit, delivered as a Claude Code skill.** Snapshots an Azure tenant via the `az` CLI, evaluates against published Microsoft + FinOps Foundation rules, and produces a written analysis (`report.md` + `findings.yaml`) suitable for forwarding to a portfolio CTO.

> Built for private-equity ops teams who need a **20-minute Azure cost review** of a freshly-acquired portfolio company, with every finding grounded in a citable authority (Azure Well-Architected Framework, Cloud Adoption Framework, Advisor recommendation reference, FinOps Foundation, Retail Prices API).

---

## What it produces

A `report.md` that opens with headline GBP savings range, top-3 quick wins, top-3 strategic recommendations, then severity-grouped findings. Plus a flat `findings.yaml` for any downstream consumer. See [`docs/example-report.md`](docs/example-report.md) for a full sanitised sample.

```
# Azure cost review — 2026-04-29T14-41-29Z

- Total estimated monthly savings: £97 – £316 / month
- Findings by severity: Critical 0 · High 0 · Medium 12 · Low 136 · Info 60

## Top 3 quick wins
1. Orphaned managed disk: ...-containerRootVolume — £31–£38/mo (severity Medium, confidence High)
2. Orphaned managed disk: ...-osDisk — £4/mo (severity Medium, confidence High)
3. Unattached Standard public IP: pip-test-natgw-01 — £2–£3/mo (severity Medium, confidence High)
```

Every finding cites the `knowledge/*.md` document grounding it. Savings figures are GBP retail-rate ceilings — reservations and negotiated discounts are explicitly not netted out. Severity (Critical → Info) and confidence (High / Medium / Low) are separate axes, both reported.

---

## Architectural guarantees

- **Read-only is absolute.** The core `azcli.py` wrapper refuses 33 write verbs (`update`, `delete`, `create`, `set`, `add`, `remove`, `assign`, `start`, `stop`, `restart`, `deallocate`, `tag update`, `policy assignment`, …) at the subprocess boundary. Verified by 23 dedicated unit tests. Safe to run against production without a change-management window.
- **Knowledge corpus is hardcoded, versioned, citable.** Each `knowledge/*.md` ships with frontmatter (canonical URL, retrieval date, content SHA-256, `cited_by` list) and verbatim quotes the rule it grounds. The analyser refuses to run a rule whose declared `knowledge_refs` are absent. No live web fetches at runtime.
- **GBP currency.** Retail Prices API queried with `currencyCode=GBP`; reports format figures as £.
- **Subscription scope.** Iterates every subscription the signed-in identity can access. `--subscription` and `--exclude` flags narrow scope.
- **Severity ≠ confidence.** A Medium-severity orphan disk (deterministic) and a Medium-severity oversized VM (CPU-only heuristic) are reported with different confidence levels so a reviewer knows where to push back.

---

## Layout

```
packages/
  azure-investigator-core/         # shared: auth, az wrapper, snapshot, pricing, schema, knowledge loader
  azure-cost-investigator/         # cost / FinOps skill (v1) — 11 rules, 11-doc knowledge corpus
  azure-security-investigator/     # reserved namespace; ships in v2 (stub today)
scripts/
  install_skill.sh                 # symlinks each SKILL.md into ~/.claude/skills/
  refresh_knowledge.py             # maintainer-only: re-fetch knowledge sources, surface drift
docs/
  architecture.md                  # one-page: why two skills + one core
  contributing-a-rule.md           # how to author a new cost rule
```

Skills never import each other. Both depend on `azure-investigator-core`.

---

## Quickstart

Requires [`uv`](https://docs.astral.sh/uv/) and the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli).

```bash
git clone <this-repo>
cd azure-investigator
uv sync --all-packages
bash scripts/install_skill.sh        # symlinks SKILL.md into ~/.claude/skills/
```

Then, against your tenant:

```bash
az login
uv run azure-investigator init       # writes ~/.config/azure-investigator/config.yaml
uv run azure-investigator doctor     # verifies environment + corpus
uv run azure-investigator pull       # snapshots every accessible subscription
uv run azure-cost-investigator analyse latest
```

Outputs land in `~/.local/share/azure-investigator/snapshots/<id>/`:

```
manifest.yaml       per-collector status, identity, subscriptions
subscriptions/<id>/ raw `az` payloads (one JSON per collector family)
pricing/            snapshot-time price cache (reproducible reports)
report.md           ← user-facing artefact
findings.yaml       ← machine-readable findings
```

---

## CLI surface

```bash
# core
azure-investigator init
azure-investigator doctor
azure-investigator pull [--subscription ...] [--exclude ...] [--collector ...]
azure-investigator snapshot ls
azure-investigator snapshot show <id|latest>
azure-investigator schema [finding|snapshot]

# cost skill
azure-cost-investigator analyse <id|latest> [--rule ...] [--exclude-rule ...] [--no-show]
azure-cost-investigator report  <id|latest> [--format md|json] [--output PATH]
azure-cost-investigator knowledge list
azure-cost-investigator knowledge show <filename>
azure-cost-investigator schema [finding|report]

# security skill — v2 stub
azure-security-investigator analyse   # prints "v2 — not implemented"
```

No mutating verbs. No `apply`, `remediate`, `fix`, `delete`. The naming is part of the read-only contract.

---

## Authorities the cost skill grounds itself in

| Authority | Used by |
|---|---|
| [Azure Well-Architected Framework — Cost Optimization pillar](https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/principles) | Strategic narrative, dev-vs-prod SKU mismatches |
| [Microsoft Cloud Adoption Framework — resource tagging](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging) | Untagged-resources rule, governance findings |
| [Azure Advisor — cost recommendation reference](https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations) | Mirroring the canonical taxonomy of cost findings |
| [Azure Advisor — VM / VMSS shutdown + resize logic](https://learn.microsoft.com/en-us/azure/advisor/advisor-cost-recommendations) | Verbatim P95 CPU + outbound thresholds for idle / oversized VMs |
| [FinOps Foundation framework](https://www.finops.org/framework/) | Inform / Optimize / Operate phases; reservation utilisation threshold |
| [Azure Retail Prices REST API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) | All GBP savings figures |

The full corpus is 11 in-repo `.md` files at `packages/azure-cost-investigator/src/azure_cost_investigator/knowledge/`. List with `azure-cost-investigator knowledge list`; read individual docs with `azure-cost-investigator knowledge show <filename>`.

---

## Cost rules implemented in v1

| Rule | Severity (typical) | Confidence | Authority |
|---|---|---|---|
| `orphaned_disks` | Medium | High | Microsoft "unattached disks" + Advisor |
| `unattached_public_ips` | Medium / High | High | Standard SKU billing + Basic SKU retirement |
| `stopped_not_deallocated_vms` | Critical | High | Advisor + VM lifecycle |
| `idle_vms` | Medium | Medium | Advisor P95 CPU < 3% (verbatim) |
| `oversized_vms` | Medium | Low | Advisor user-facing target P95 ≤ 40% |
| `unused_app_service_plans` | High | High | App Service plan billing model + Advisor |
| `old_snapshots` | Medium | High | Cool tier 90-day minimum + Advisor |
| `underused_reservations` | Medium | Medium | FinOps Foundation 80% / 30-day |
| `dev_skus_in_prod` | Medium | Medium | WAF Principle 2 + CAF tagging |
| `untagged_costly_resources` | Low | High | CAF tagging schema + FinOps Inform phase |
| `legacy_storage_redundancy` | Low / Medium | Medium | Storage redundancy + WAF cost pillar |

Each one is documented in `docs/contributing-a-rule.md` for the pattern of adding a twelfth.

---

## Status

- **129 tests passing** across the workspace; the `azcli.py` write-verb firewall has its own 23-test guard.
- **Validated against a real Azure tenant** (single subscription, 869 resources, 15 VMs, 51 reservations, 106 storage accounts) — produces a 1–2 page `report.md` headlined with a £97–£316/mo savings range.
- **Reservation utilisation** plumbing wired through `az consumption reservation summary list` (`avgUtilizationPercentage` over a 30-day window).
- **Two known follow-ups** kept out of v1 by design:
  - Outbound-network metric collection for VMs (would lift `idle_vms` confidence from Medium to High).
  - Wiring the `PricingClient` into rule output for per-finding Retail Prices API lookups (currently uses packaged GBP/instance bands).

---

## Why two skills, one core

Persona is what makes a Claude Code skill credible. A single skill that's both *senior FinOps architect* and *senior security engineer* dilutes both — the prompts pull in opposite directions, and the user can't tell which voice they're getting. Splitting on persona while sharing read-only data plumbing lets each skill stay sharp; the security skill ships next.

See [`docs/architecture.md`](docs/architecture.md) for the full rationale and the three-place enforcement of the read-only contract. See [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md) for the discipline behind adding a new rule (knowledge first, then code, then tests).

---

## Tests

```bash
uv run pytest                                              # 128 tests, ~1s
AZURE_INVESTIGATOR_SMOKE_SNAPSHOT=/path/to/snapshot \
  uv run pytest packages/azure-cost-investigator/tests/test_real_snapshot_smoke.py
```

The smoke test runs every rule against a real on-disk snapshot. It silently skips without the env var so CI / fresh checkouts stay green without a tenant.

---

## License

MIT — see [`LICENSE`](LICENSE).
