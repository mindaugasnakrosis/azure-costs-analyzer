---
title: Cloud Adoption Framework — resource tagging strategy
source_url: https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-tagging
source_retrieved: 2026-04-29
source_sha256: 8f1cb3053a1a267e89868fd7cabb37b2427d12726691559cd927e40dc6e67754
cited_by:
  - untagged_costly_resources
  - dev_skus_in_prod
---

Microsoft's Cloud Adoption Framework recommends a foundational tagging schema split across Functional, Classification, Accounting, Purpose, and Ownership categories. The `untagged_costly_resources` rule flags resources that lack tags from the Accounting and Functional categories — the two that gate cost allocation and environment classification.

## Tag categories (verbatim)

> 1. **Use functional tags for operational management.** Functional tags categorize resources by their technical role, environment, and deployment characteristics within your workloads.
>
> 2. **Apply classification tags for governance and security.** Classification tags identify the sensitivity level, compliance requirements, and usage policies that apply to each resource.
>
> 3. **Implement accounting tags for cost management.** Accounting tags associate resources with specific organizational units, projects, or cost centers to enable accurate financial tracking and reporting. Finance teams need detailed cost attribution to support chargeback, showback, and budget management processes. Use accounting tags like department, program, and region for precise cost allocation.
>
> 4. **Establish purpose tags for business alignment.** Purpose tags connect resources to specific business functions, processes, and impact levels to support investment decisions and priority management.
>
> 5. **Define ownership tags for accountability.** Ownership tags identify the business units and operational teams responsible for each resource to ensure clear accountability and effective communication.

## Canonical tag examples (verbatim)

> | Tag type | Examples |
> | --- | --- |
> | Functional | `app : catalogsearch1`, `tier : web`, `webserver : apache`, `env : prod`, `env : staging`, `env : dev`, `region : eastus`, `region : uksouth` |
> | Classification | `criticality : mission-critical`, `criticality : medium`, `criticality : low`, `confidentiality : private`, `sla : 24hours` |
> | Accounting | `department : finance`, `program : business-initiative`, `businesscenter : northamerica`, `budget : $200,000`, `costcenter : 55332` |
> | Purpose | `businessprocess : support`, `businessimpact : moderate`, `revenueimpact : high` |
> | Ownership | `businessunit : finance`, `opsteam : central it`, `opsteam : cloud operations` |

## Case-sensitivity rule (verbatim)

> Tag names (keys) are case insensitive, but tag values are case-sensitive. […] For example, `Environment: production` and `environment: production` represent the same tag name (the first part). However, `environment: Production` and `environment: production` are different tag values (second part), and they appear separately in cost reports and resource queries.

---

**How rules use this:**

- `untagged_costly_resources` flags resources whose monthly cost in `consumption.json` exceeds £50/month and which are missing **either** an Accounting tag (any of `costcenter`, `department`, `businessunit`, `program`) **or** a Functional environment tag (any of `env`, `environment`).
- `dev_skus_in_prod` and the converse use the Functional `env` tag to classify resources for cross-tag-and-SKU consistency checks.
- The rule's `recommended_investigation` cites CAF's "centralised IT typically enforces core tags" guidance verbatim — the analyser does not write tags, it identifies the policy gap.
