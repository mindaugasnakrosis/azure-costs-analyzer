# azure-investigator

[![tests](https://github.com/mindaugasnakrosis/azure-costs-analyzer/actions/workflows/test.yml/badge.svg)](https://github.com/mindaugasnakrosis/azure-costs-analyzer/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-DE5FE9.svg)](https://docs.astral.sh/uv/)

**Read-only Azure cost & FinOps audit, delivered as a Claude Code skill.** Snapshots an Azure tenant via the `az` CLI, evaluates against published Microsoft + FinOps Foundation rules, and produces a written analysis (`report.md` + `findings.yaml`) suitable for forwarding to a portfolio CTO.

> Built for the **20-minute Azure cost review** of a freshly-acquired portfolio company — every finding grounded in a citable authority (Azure Well-Architected Framework, Cloud Adoption Framework, Advisor recommendation reference, FinOps Foundation, Retail Prices API).

---

## Who this is for

- **PE operating partners and portco CTOs** running cost audits post-acquisition or pre-investment, who need a forward-able artefact in week 1, not week 4.
- **FinOps practitioners** who want a starting point for a structured Azure cost review with citation-grounded thresholds rather than vibes.
- **DevOps / platform engineers** who want a read-only inventory of cost waste in a tenant they've inherited.
- **Claude Code users** who want a real-world example of a skill with a proper persona, knowledge corpus, and architectural firewall.

If you need a remediation tool, this isn't it. The skill is **read-only by architectural guarantee** (33 forbidden write verbs, enforced at the subprocess boundary, 23 unit tests). It produces investigations, not actions.

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
- **Two skills, one shared core.** `azure-cost-investigator` (FinOps persona) ships in v1; `azure-security-investigator` (security persona, same architecture) is a reserved namespace today and ships in v2. Skills never import each other.
- **GBP currency.** Retail Prices API queried with `currencyCode=GBP`; reports format figures as £.
- **Subscription scope.** Iterates every subscription the signed-in identity can access. `--subscription` and `--exclude` flags narrow scope.
- **Severity ≠ confidence.** A Medium-severity orphan disk (deterministic) and a Medium-severity oversized VM (CPU-only heuristic) are reported with different confidence levels so a reviewer knows where to push back.

See [`docs/architecture.md`](docs/architecture.md) for the full rationale.

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
  example-report.md                # sanitised sample report.md output
```

---

## Requirements

- **Python 3.11+** (3.12 also tested in CI).
- **[`uv`](https://docs.astral.sh/uv/)** for the Python toolchain. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh` or your platform's package manager.
- **[Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli)** logged into the tenant you want to analyse.
- **[Claude Code](https://claude.com/code)** if you want to use the skill experience (the CLI works without it).
- *(optional)* The `reservation` extension if your tenant has reservations: `az extension add --name reservation`.

### Required Azure permissions

The signed-in `az` identity needs **read access** to whatever you want analysed. The minimum set:

| Scope | Built-in role | What it enables |
|---|---|---|
| Subscription | **Reader** | All resource-graph collectors (vms, disks, public_ips, nics, snapshots, app_service_plans, app_services, sql, storage_accounts, resources, tags, advisor) |
| Subscription | **Monitoring Reader** *(or Reader is usually enough)* | `vm_metrics`, `consumption` |
| Reservation order / billing scope | **Reservations Reader** | `reservations` collector + utilisation merge |

If a role is missing the corresponding collector emits a structured error in `manifest.yaml` and the rules that depend on it downgrade to Info findings — the run never aborts. You can re-run after granting the role.

---

## Quickstart

```bash
git clone https://github.com/mindaugasnakrosis/azure-costs-analyzer.git
cd azure-costs-analyzer
uv sync --all-packages
bash scripts/install_skill.sh        # only needed if you want it as a Claude Code skill
```

Then, against your tenant:

```bash
az login
uv run azure-investigator init       # writes ~/.config/azure-investigator/config.yaml
uv run azure-investigator doctor     # verifies environment + corpus
uv run azure-investigator pull       # snapshots every accessible subscription (5–15 min)
uv run azure-cost-investigator analyse latest
```

Outputs land next to the snapshot manifest:

| OS | Snapshot root |
|---|---|
| Linux | `~/.local/share/azure-investigator/snapshots/<id>/` |
| macOS | `~/Library/Application Support/azure-investigator/snapshots/<id>/` |
| Windows | `%LOCALAPPDATA%\azure-investigator\snapshots\<id>\` |

Per snapshot:

```
manifest.yaml       per-collector status, identity, subscriptions
subscriptions/<id>/ raw `az` payloads (one JSON per collector family)
pricing/            snapshot-time price cache (reproducible reports)
report.md           ← user-facing artefact
findings.yaml       ← machine-readable findings
```

---

## Using as a Claude Code skill

After `bash scripts/install_skill.sh`, restart Claude Code (or run `/skills`). Then trigger the skill with a natural-language prompt — Claude reads `SKILL.md`, decides this skill matches, and drives the CLIs for you.

Example prompts that should trigger:

- *"Run an Azure cost review on my tenant. Use the latest snapshot."*
- *"Where is money being wasted in this Azure subscription? Walk me through the top 3 quick wins."*
- *"Do a 20-minute FinOps assessment of the production subscription. Cite the knowledge documents you're relying on."*

The skill will (in order): check `azure-investigator doctor` → decide whether to `pull` or reuse `latest` → run `azure-cost-investigator analyse` → narrate `report.md` to you, lifting the verbatim assumptions from each `SavingsRange` and citing the `knowledge/*.md` grounding each finding.

If you want to drive the engine directly without going through Claude Code, just use the CLI verbs above — the skill is optional.

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
azure-security-investigator analyse   # prints "v2 — not implemented", exits 2
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

To add a twelfth, see [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md). The discipline is *knowledge document first, then code, then tests* — and the analyser refuses to run a rule whose `knowledge_refs` are missing.

---

## Troubleshooting

**`az login active` fails in `doctor`.** Run `az login` and confirm you can run a read like `az account show -o table`. The skill never runs `az login` for you.

**`disks` collector errors with `the following arguments are required: --resource-group`.** Some Azure CLI builds reject `az disk list` without `-g`. The collector falls back to per-resource-group enumeration; if every per-RG call fails the `orphaned_disks` rule downgrades to an Info finding instead of running blind. Updating the Azure CLI usually clears it.

**`reservations` collector returns "all 'utilisation unknown'".** The `reservation` extension may be missing or out of date. Run `az extension add --name reservation` (or `az extension update --name reservation`) and re-pull. The next snapshot will merge `avgUtilizationPercentage` from `az consumption reservation summary list` onto each reservation record.

**`consumption` collector times out.** Cost Management can be slow on large subscriptions. The collector uses a 600s per-call timeout. If it still times out, narrow the pull with `--collector` to skip `consumption` for the first run; you can re-pull later for that one collector.

**`analyse` errors with `KnowledgeRefMissing`.** A rule cites a knowledge document that's not in the corpus. Either the file was renamed (update the rule's `KNOWLEDGE_REFS`) or you ran from a partial install (`uv sync --all-packages` from the repo root re-establishes the corpus).

**`bash scripts/install_skill.sh` reports `warning: ... exists and is not a symlink`.** A previous install left a real file at `~/.claude/skills/<name>/SKILL.md`. The script backs it up with a timestamped suffix and then symlinks; the warning is informational, not an error.

---

## Tests

```bash
uv run pytest                                              # 128 passed, 1 skipped (~1s)

# optional: run the smoke test against a real snapshot
AZURE_INVESTIGATOR_SMOKE_SNAPSHOT=/path/to/snapshot \
  uv run pytest packages/azure-cost-investigator/tests/test_real_snapshot_smoke.py
```

The smoke test runs every rule against a real on-disk snapshot. It silently skips without the env var so CI / fresh checkouts stay green without a tenant.

Lint + format:

```bash
uv run ruff check .
uv run ruff format --check .
```

CI runs all three on push and on PR against `main`, on Python 3.11 and 3.12.

---

## Roadmap

- **`azure-security-investigator` (v2).** Same core, same architectural firewall, security persona. Knowledge corpus will quote Microsoft Cloud Security Benchmark and CIS Microsoft Azure Foundations Benchmark verbatim.
- **Outbound-network metric collection** for VMs. Would lift `idle_vms` confidence from Medium to High by completing Microsoft's full Advisor shutdown criterion.
- **`PricingClient` wired into rule output** for per-finding Retail Prices API lookups (currently uses packaged GBP/instance bands as ceilings).
- **FinOps Foundation `/framework/phases/`** verbatim quotes (currently a `TODO: refetch` block in `knowledge/finops-framework.md`).
- **Resource-graph-based pull mode** as a faster alternative for whole-tenant snapshots (currently per-RG enumeration for disks).

If you have an authority, a metric, or a rule you'd want grounded — open an issue. The pattern of "verbatim quote → citing rule → testable threshold" is reusable for anything with published thresholds.

---

## Contributing

See [`docs/contributing-a-rule.md`](docs/contributing-a-rule.md) for adding a new cost rule. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the broader contribution flow (issues, PRs, code review).

If you find a security issue (especially anything that could let the read-only firewall be bypassed), see [`SECURITY.md`](SECURITY.md) for responsible-disclosure instructions.

---

## License

MIT — see [`LICENSE`](LICENSE).
