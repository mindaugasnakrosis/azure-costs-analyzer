# Knowledge corpus — azure-cost-investigator

Each `.md` file in this folder grounds one or more cost rules in a published
authority. The format is uniform:

```
---
title: <short title>
source_url: <canonical URL>
source_retrieved: <YYYY-MM-DD>
source_sha256: <SHA-256 of the body of this file>
cited_by: [rule_id, rule_id, ...]
---

<verbatim quote(s) from the source, framed by short connecting commentary>
```

Hard rules:

1. **Verbatim quotes only for the rule, threshold, or definition the analyser depends on.** Paraphrase is fine in surrounding commentary; the cited rule itself is copied exactly.
2. **`cited_by` is a list of `rule_id` values.** The cost analyser refuses to run a rule whose declared `knowledge_refs` are absent from this corpus.
3. **`source_retrieved` is an absolute date** (ISO `YYYY-MM-DD`). Never relative.
4. **`source_sha256`** is the hex digest of this file's body (everything after the closing `---` of the frontmatter). Refresh via `scripts/refresh_knowledge.py`.

A maintainer-only `scripts/refresh_knowledge.py` re-fetches the canonical sources, regenerates each file's quoted block, and updates the hash + retrieval date. The diff is human-reviewed before commit.

## Files in this corpus

| File | Authority |
| --- | --- |
| `azure-well-architected-cost.md` | Microsoft WAF — Cost Optimization pillar (design principles) |
| `azure-advisor-cost-rules.md` | Azure Advisor — Cost recommendation reference |
| `vm-rightsizing-thresholds.md` | Azure Advisor — VM/VMSS shutdown + resize recommendation logic (CPU and network thresholds, lookback window) |
| `disk-orphan-criteria.md` | Microsoft Learn — "Identify unattached Azure disks" |
| `reservations-utilisation.md` | Microsoft Learn — Reservation utilisation reporting |
| `app-service-plan-utilisation.md` | Microsoft Learn — App Service plan billing model |
| `public-ip-orphan.md` | Microsoft Learn — Public IP addresses (Standard SKU billing) |
| `storage-tiering.md` | Microsoft Learn — Blob access tiers (Hot/Cool/Cold/Archive minimum durations + early-deletion penalty) |
| `tagging-and-governance.md` | Microsoft CAF — Resource tagging strategy |
| `finops-framework.md` | FinOps Foundation — Six FinOps Principles + Inform/Optimize/Operate phases |
| `pricing-sources.md` | Microsoft — Azure Retail Prices REST API |
