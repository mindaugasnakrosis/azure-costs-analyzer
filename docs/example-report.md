<!--
Sanitised sample report — resource names anonymised, all numbers and severities preserved.
Generated against a real Azure tenant (single subscription, ~870 resources, 15 VMs, 51 reservations, 106 storage accounts)
by `azure-cost-investigator analyse latest`.
-->

# Azure cost review — `2026-04-29T14-41-29Z`

_Generated: 2026-04-29T15:02:57.447856+00:00 · Currency: GBP_

## Headline numbers

- **Total estimated monthly savings: £97 – £316 / month**
- Findings by severity:
  - Critical: 0
  - High: 0
  - Medium: 12
  - Low: 136
  - Info: 60

_Savings figures are GBP-converted retail rates and don't net out negotiated discounts or reservation coverage. Treat them as ceilings, not invoiced amounts._

## Top 3 quick wins

1. **Orphaned managed disk: databricks-worker-01-containerRootVolume** — £31–£38/mo _(severity Medium, confidence High)_
2. **Orphaned managed disk: databricks-worker-01-osDisk** — £4–£4/mo _(severity Medium, confidence High)_
3. **Unattached Standard public IP: pip-test-natgw-01** — £2–£3/mo _(severity Medium, confidence High)_

## Top 3 strategic recommendations

1. **untagged_costly_resources** — across 135 resources
   - Example: Untagged VM: databricks-worker-02 missing accounting, functional/env tag(s)
   - Authority: tagging-and-governance.md, finops-framework.md
2. **oversized_vms** — total £60–£270/mo across 5 resources
   - Example: Oversized VM (avg 5.9%, p95 9.3% over 14d): databricks-worker-03
   - Authority: vm-rightsizing-thresholds.md, azure-advisor-cost-rules.md, pricing-sources.md
3. **legacy_storage_redundancy** — across 3 resources
   - Example: Geo-redundant storage (Standard_GRS, Hot): finance-storage-qa
   - Authority: storage-tiering.md, azure-well-architected-cost.md

## Medium findings (12)

- **Orphaned managed disk: databricks-worker-01-containerRootVolume** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £31–£38 / month. _Assumes the disk is genuinely orphaned and not a manual backup. Cost band uses retail rates for Premium Premium_LRS 256 GB; actual savings depend on negotiated discounts and reservations._
  Severity: Medium · Confidence: High
  Authority: disk-orphan-criteria.md, azure-advisor-cost-rules.md
  Recommended investigation: Per Microsoft: 'Deletions are permanent, you will not be able to recover data once you delete a disk.' Confirm the disk is not a manual backup; create a snapshot before any deletion decision.

- **Orphaned managed disk: databricks-worker-01-osDisk** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £4–£4 / month. _Assumes the disk is genuinely orphaned and not a manual backup. Cost band uses retail rates for Premium Premium_LRS 30 GB; actual savings depend on negotiated discounts and reservations._
  Severity: Medium · Confidence: High
  Authority: disk-orphan-criteria.md, azure-advisor-cost-rules.md
  Recommended investigation: Per Microsoft: 'Deletions are permanent, you will not be able to recover data once you delete a disk.' Confirm the disk is not a manual backup; create a snapshot before any deletion decision.

- **Unattached Standard public IP: pip-test-natgw-01** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £2–£3 / month. _Assumes the IP remains unattached and is not required for an outbound-firewall pinhole or DNS A record. Band uses retail Standard SKU IPv4 rates._
  Severity: Medium · Confidence: High
  Authority: public-ip-orphan.md, azure-advisor-cost-rules.md
  Recommended investigation: Confirm the address isn't allow-listed by an external partner before release; static IPv4 is released permanently on delete (Microsoft).

- **Oversized VM (avg 5.9%, p95 9.3% over 14d): databricks-worker-03** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £12–£54 / month. _Assumes a one-step-smaller SKU within the same family (Standard_DS4_v2) keeps P95 CPU ≤ 40%. Memory and outbound-network utilisation are not in this snapshot, so the saving is bounded above; validate against Advisor's specific SKU recommendation before planning a change._
  Severity: Medium · Confidence: Low
  Authority: vm-rightsizing-thresholds.md, azure-advisor-cost-rules.md, pricing-sources.md
  Recommended investigation: Cross-reference Advisor's `Right-size or shutdown underutilized virtual machines` recommendation for the specific target SKU. Confirm memory headroom before resizing — this rule only sees CPU.

- **Oversized VM (avg 20.3%, p95 22.5% over 14d): databricks-worker-04** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £12–£54 / month. _Assumes a one-step-smaller SKU within the same family (Standard_D4ads_v5) keeps P95 CPU ≤ 40%. Memory and outbound-network utilisation are not in this snapshot, so the saving is bounded above; validate against Advisor's specific SKU recommendation before planning a change._
  Severity: Medium · Confidence: Low
  Authority: vm-rightsizing-thresholds.md, azure-advisor-cost-rules.md, pricing-sources.md
  Recommended investigation: Cross-reference Advisor's `Right-size or shutdown underutilized virtual machines` recommendation for the specific target SKU. Confirm memory headroom before resizing — this rule only sees CPU.

- **Oversized VM (avg 14.0%, p95 14.6% over 14d): databricks-worker-05** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £12–£54 / month. _Assumes a one-step-smaller SKU within the same family (Standard_DS4_v2) keeps P95 CPU ≤ 40%. Memory and outbound-network utilisation are not in this snapshot, so the saving is bounded above; validate against Advisor's specific SKU recommendation before planning a change._
  Severity: Medium · Confidence: Low
  Authority: vm-rightsizing-thresholds.md, azure-advisor-cost-rules.md, pricing-sources.md
  Recommended investigation: Cross-reference Advisor's `Right-size or shutdown underutilized virtual machines` recommendation for the specific target SKU. Confirm memory headroom before resizing — this rule only sees CPU.

- **Oversized VM (avg 9.7%, p95 14.9% over 14d): databricks-worker-06** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £12–£54 / month. _Assumes a one-step-smaller SKU within the same family (Standard_DS4_v2) keeps P95 CPU ≤ 40%. Memory and outbound-network utilisation are not in this snapshot, so the saving is bounded above; validate against Advisor's specific SKU recommendation before planning a change._
  Severity: Medium · Confidence: Low
  Authority: vm-rightsizing-thresholds.md, azure-advisor-cost-rules.md, pricing-sources.md
  Recommended investigation: Cross-reference Advisor's `Right-size or shutdown underutilized virtual machines` recommendation for the specific target SKU. Confirm memory headroom before resizing — this rule only sees CPU.

- **Oversized VM (avg 12.9%, p95 43.3% over 14d): FINANCE-SQL-VM01** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Estimated savings: £12–£54 / month. _Assumes a one-step-smaller SKU within the same family (Standard_D4ds_v4) keeps P95 CPU ≤ 40%. Memory and outbound-network utilisation are not in this snapshot, so the saving is bounded above; validate against Advisor's specific SKU recommendation before planning a change._
  Severity: Medium · Confidence: Low
  Authority: vm-rightsizing-thresholds.md, azure-advisor-cost-rules.md, pricing-sources.md
  Recommended investigation: Cross-reference Advisor's `Right-size or shutdown underutilized virtual machines` recommendation for the specific target SKU. Confirm memory headroom before resizing — this rule only sees CPU.

- **Environment / tier mismatch (prod tier on non-prod-tagged App Service Plan): platform-cds-qa-app-service-plan** _(sub: ACME-PORTFOLIO-CO-TEST, region: UK South)_
  Severity: Medium · Confidence: Medium
  Authority: azure-well-architected-cost.md, tagging-and-governance.md
  Recommended investigation: Premium-tier plan under a non-production tag. WAF Principle 2: SDLC environments should be right-sized differently. Confirm the environment tag is accurate and decide whether to retag or rescale the plan.

- **Environment / tier mismatch (prod tier on non-prod-tagged App Service Plan): platform-cds-qa-fnapp-service-plan** _(sub: ACME-PORTFOLIO-CO-TEST, region: UK South)_
  Severity: Medium · Confidence: Medium
  Authority: azure-well-architected-cost.md, tagging-and-governance.md
  Recommended investigation: Premium-tier plan under a non-production tag. WAF Principle 2: SDLC environments should be right-sized differently. Confirm the environment tag is accurate and decide whether to retag or rescale the plan.

- **Geo-redundant storage (Standard_GRS, Hot): finance-storage-qa** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Severity: Medium · Confidence: Medium
  Authority: storage-tiering.md, azure-well-architected-cost.md
  Recommended investigation: Geo-replicated accounts roughly double per-GB storage cost vs LRS. Confirm the RPO requirement justifies cross-region replication; non-prod data rarely does. Consider LRS or ZRS where appropriate.

- **Geo-redundant storage (Standard_GRS, Hot): finance-storage-uat** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Severity: Medium · Confidence: Medium
  Authority: storage-tiering.md, azure-well-architected-cost.md
  Recommended investigation: Geo-replicated accounts roughly double per-GB storage cost vs LRS. Confirm the RPO requirement justifies cross-region replication; non-prod data rarely does. Consider LRS or ZRS where appropriate.

## Low findings (136)

### untagged_costly_resources — 135 resource(s)

- Untagged VM: databricks-worker-02 missing accounting, functional/env tag(s)
- Untagged VM: databricks-worker-03 missing accounting, functional/env tag(s)
- Untagged VM: databricks-worker-07 missing accounting, functional/env tag(s)
- Untagged VM: databricks-worker-08 missing accounting, functional/env tag(s)
- Untagged VM: databricks-worker-09 missing accounting, functional/env tag(s)
- _… and 130 more_

_Authority: tagging-and-governance.md, finops-framework.md._

_Recommended investigation_: CAF: 'Centralized IT policies typically enforce core tags.' Confirm the tagging policy is enforced via Azure Policy and that this resource is in scope; remediation is out of scope for this read-only skill.

- **Geo-redundant storage (Standard_GRS, Hot): databricks-managed-storage** _(sub: ACME-PORTFOLIO-CO-TEST, region: uksouth)_
  Severity: Low · Confidence: Medium
  Authority: storage-tiering.md, azure-well-architected-cost.md
  Recommended investigation: Geo-replicated accounts roughly double per-GB storage cost vs LRS. Confirm the RPO requirement justifies cross-region replication; non-prod data rarely does. Consider LRS or ZRS where appropriate.

## Info findings (60)

_Findings here mean the analyser couldn't reach a verdict — usually missing data, sparse metrics, or an API field the collector didn't capture._

### idle_vms — 9 item(s)
- Idle VM check: insufficient metrics for databricks-worker-02
- Idle VM check: insufficient metrics for databricks-worker-07
- Idle VM check: insufficient metrics for databricks-worker-08
- Idle VM check: insufficient metrics for databricks-worker-09
- Idle VM check: insufficient metrics for databricks-worker-10
- _… and 4 more_

### underused_reservations — 51 item(s)
- Reservation utilisation unknown: 0467abc5-b3a2-492e-aa83-af396eb2127d
- Reservation utilisation unknown: 787637f0-83cb-4bab-ac26-95a5042d098b
- Reservation utilisation unknown: 1a596dd4-065f-43ea-8100-e4d4b4f5a77c
- Reservation utilisation unknown: 455ec16c-0094-470f-afc3-8c5f47cfee51
- Reservation utilisation unknown: 1cfcd647-9c65-44b0-856b-a469352f2419
- _… and 46 more_

---

_Read-only analysis. Every claim is grounded in a `knowledge/*.md` document; no `az` write commands are issued. Findings are suggestions, not actions._
