# Changelog

All notable changes to this project will be documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0] — 2026-04-29

First public release. Initial 5-commit build of the workspace, core package, cost skill, security namespace stub, and tooling/docs.

### Added

- **Workspace scaffolding** — `uv` workspace with three member packages, MIT license, GitHub Actions CI on Python 3.11 + 3.12, ruff config (lint + format), `.gitignore`.
- **`azure-investigator-core`** package: read-only `az` wrapper (`azcli.py`) with 33-verb forbidden list and 23 unit tests; Pydantic schema (`Finding`, `SavingsRange`, `Severity`, `Confidence`, `SnapshotManifest`, `Report`); 16 collectors covering subscriptions, resources, vms, vm_metrics, disks (per-RG), public_ips, nics, snapshots, app_service_plans, app_services, sql, storage_accounts, reservations (with consumption-summary utilisation merge), advisor, consumption, tags; pull orchestrator with per-collector failure tolerance; Retail Prices API client with on-disk JSON cache (GBP-default); knowledge-corpus loader; Typer CLI (`init` / `doctor` / `pull` / `snapshot ls/show` / `schema`).
- **`azure-cost-investigator`** package: 11-document knowledge corpus (WAF Cost Optimization, Advisor cost recommendation reference, Advisor VM/VMSS shutdown+resize logic, Microsoft "unattached disks", reservation utilisation reporting, App Service plan billing model, Standard SKU public IP billing, Blob storage access tiers, CAF resource tagging, FinOps Foundation framework, Retail Prices REST API) — each with frontmatter (source URL, retrieval date, SHA-256, `cited_by`) and verbatim upstream quotes; 11 cost rules (`orphaned_disks`, `unattached_public_ips`, `stopped_not_deallocated_vms`, `idle_vms`, `oversized_vms`, `unused_app_service_plans`, `old_snapshots`, `underused_reservations`, `dev_skus_in_prod`, `untagged_costly_resources`, `legacy_storage_redundancy`); `analyse` + markdown / YAML report rendering with low-severity compression; Typer CLI (`analyse` / `report` / `knowledge list` / `knowledge show` / `schema`); SKILL.md persona prompt (£1000/day senior FinOps architect).
- **`azure-security-investigator`** package: reserved-namespace stub with deflecting `analyse` verb and one-paragraph SKILL.md.
- **Tooling**: `scripts/install_skill.sh` (idempotent SKILL.md symlinks); `scripts/refresh_knowledge.py` (maintainer knowledge-source refresh with drift detection); `docs/architecture.md`, `docs/contributing-a-rule.md`, `docs/example-report.md` (sanitised sample).
- **Repo polish**: status badges, CONTRIBUTING, SECURITY, CHANGELOG, issue + PR templates.

### Architectural guarantees in 0.1.0

- Read-only is absolute (33 forbidden verbs, enforced at the subprocess boundary, 23 tests).
- Every cost rule must cite a `knowledge/*.md` document; analyser refuses to run otherwise.
- Savings as ranges with non-empty `assumption` (Pydantic-enforced).
- Severity (Critical → Info) and confidence (High / Medium / Low) reported as separate axes.
- GBP currency by default.
- Subscription scope; never reaches above the subscription boundary.
- 128 tests passing on Python 3.11 + 3.12; 1 skipped (real-snapshot smoke test, env-var gated).

### Known follow-ups (deferred to v0.2)

- Outbound-network metric collection for VMs (would lift `idle_vms` confidence from Medium to High).
- Wiring `PricingClient` into rule output for per-finding Retail Prices API lookups (currently uses packaged GBP/instance bands).
- Re-fetch FinOps Foundation `/framework/phases/` for the per-phase definitions (currently a `TODO: refetch` in `knowledge/finops-framework.md`).
- `azure-security-investigator` v2 — same architecture, security persona, CIS + Microsoft Cloud Security Benchmark corpus.

[Unreleased]: https://github.com/mindaugasnakrosis/azure-costs-analyzer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mindaugasnakrosis/azure-costs-analyzer/releases/tag/v0.1.0
