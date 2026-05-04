# Azure Dev/Test offer eligibility

## Authority

- [Azure Dev/Test pricing overview (Microsoft)](https://azure.microsoft.com/en-us/pricing/dev-test/)
- [Enterprise Dev/Test subscription docs](https://learn.microsoft.com/azure/cost-management-billing/manage/ea-portal-administration#enterprise-dev-test-subscriptions)
- [Subscription quotaIds — Microsoft.Subscription resource provider](https://learn.microsoft.com/rest/api/subscription/subscriptions/get)

## What the offer does

A subscription enrolled under a **Dev/Test offer** ("MSDN Dev/Test", "EA
Dev/Test", or "Pay-As-You-Go Dev/Test") receives:

- **Up to 55%** off Windows Server VM compute (no separate Windows licence
  charge — the OS is bundled at the Linux VM rate).
- No SQL Server, BizTalk, SharePoint, Project Server, or Visual Studio
  licence charges on subscriptions where the workload is **non-production**
  and access is restricted to active Visual Studio subscribers.
- Lower DTU/vCore prices for SQL Database Dev/Test SKUs.
- Otherwise identical Linux VM, storage, networking, and PaaS pricing
  (Linux VMs are not discounted further on Dev/Test).

The offer is a billing/contractual arrangement, not a technical feature: a
subscription is either Dev/Test-enrolled or it is not. **You cannot mix
production workloads on a Dev/Test subscription** — Microsoft reserves the
right to cancel and back-charge if the use breaches the licence terms.

## How we detect it

The Microsoft.Subscription Get API
(`/subscriptions/{id}?api-version=2022-12-01`, also surfaced via
`az account subscription show --id <id>`) returns a
`subscriptionPolicies.quotaId`. The known Dev/Test quotaIds are:

| quotaId prefix | Offer family |
|---|---|
| `MSDNDevTest_` | MSDN Dev/Test (legacy) |
| `MSDN_DevTest_` | MSDN Dev/Test (newer) |
| `EnterpriseAgreement_DevTest_` | EA Dev/Test |
| `MPN_2014-09-01` | Microsoft Partner Network (treated as Dev/Test eligible) |
| `PayAsYouGoDevTest_` | PAYG Dev/Test |
| `Sponsored_*` | Sponsored / Visual Studio Enterprise |

Any other `quotaId` (e.g. `EnterpriseAgreement_2014-09-01`,
`PayAsYouGo_2014-09-01`, `Internal_2014-09-01`,
`MSDN_2014-09-01` without `DevTest`) means the subscription is **not** on
Dev/Test rates.

## When we flag it

A finding is emitted when **both** are true:

1. The subscription's `quotaId` is a non-Dev/Test offer.
2. The subscription has a "test-shaped" signal:
   - Its `displayName` matches `(?i)\b(test|dev|staging|uat|sandbox|qa)\b`,
     **or**
   - More than 50% of its VMs carry an `environment` / `env` tag whose
     value matches the same pattern.

The match on display name alone is high-signal in practice (most
organisations name their non-prod subscriptions explicitly), but the tag
fallback catches subs that follow a different naming convention.

## Savings band

Microsoft's published headline is *"up to 55%"* off Windows VM compute. We
take a deliberately conservative band at the rule layer:

- **Low**: `compute_30d_gbp × 0.20`
- **High**: `compute_30d_gbp × 0.40`

`compute_30d_gbp` is summed from the consumption snapshot,
`MeterCategory == "Virtual Machines"` over the 30-day window. Reasons we
discount the headline:

- Not every VM on the subscription runs Windows; Linux VMs see no compute
  discount on Dev/Test.
- Some workloads on a "test"-named subscription may actually be production
  and therefore ineligible for the offer.
- The 55% headline is the maximum, not the average; the EA Dev/Test
  contract page quotes 40–55% on Windows and 25–55% on SQL Server VMs.

If consumption data is not in the snapshot we still emit the finding (so
the procurement action is visible) but with no band.

## Severity / confidence

Authored as **High** with **Medium confidence**. The procurement decision
is single-action and reversible (a subscription can be moved back to
PAYG/EA at any time), but the eligibility determination is not something
this tool can make alone — it depends on the workloads' Visual Studio
licensing posture and the tenant's contract type, which the rule cannot
see. The recommendation always points at the billing administrator
rather than asserting eligibility outright.
