---
title: Azure App Service plan billing model
source_url: https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans
source_retrieved: 2026-04-29
source_sha256: aaa3b7b851aa3cbcc3b3bb8f42c248c661a012c8731194229e171a228d832155
cited_by:
  - unused_app_service_plans
---

App Service plans bill on the underlying compute regardless of how many apps run on them. This is the authority for the `unused_app_service_plans` finding.

## Billing rule (verbatim)

> Except for the Free tier, an App Service plan carries a charge on the compute resources that it uses:
>
> - **Shared tier**: Each app receives a quota of CPU minutes, so *each app* is charged for the CPU quota.
> - **Dedicated compute tiers (Basic, Standard, Premium, PremiumV2, PremiumV3, PremiumV4)**: The App Service plan defines the number of VM instances that the apps are scaled to, so *each VM instance* in the App Service plan is charged. These VM instances are charged the same, regardless of how many apps are running on them. To avoid unexpected charges, see [Delete an App Service plan].
> - **IsolatedV2 tier**: The App Service Environment defines the number of isolated workers that run your apps, and *each worker* is charged.

## Pricing tiers (verbatim)

> The pricing tier of an App Service plan determines what App Service features you get and how much you pay for the plan.
>
> | Category | Tiers | Description |
> | --- | --- | --- |
> | Shared compute | Free, Shared | Free and Shared, the two base tiers, run an app on the same Azure VM as other App Service apps, including apps of other customers. […] These tiers are intended for only development and testing purposes. |
> | Dedicated compute | Basic, Standard, Premium, PremiumV2, PremiumV3, PremiumV4 | The Basic, Standard, Premium, PremiumV2, PremiumV3, and PremiumV4 tiers run apps on dedicated Azure VMs. |
> | Isolated | IsolatedV2 | The IsolatedV2 tier runs dedicated Azure VMs on dedicated Azure virtual networks. |

## Plan-level scaling (verbatim)

> All apps in an App Service plan scale together, because they share the same underlying compute resources (VM instances). Scaling the plan — whether manually or through autoscale rules — affects all apps in the plan.

---

**How the rule uses this:**

- `unused_app_service_plans` flags any plan where `numberOfSites == 0` and the SKU tier is in `{Basic, Standard, Premium, PremiumV2, PremiumV3, PremiumV4, IsolatedV2}` (i.e. dedicated compute that bills regardless of apps).
- Confidence: **High** — deterministic from inventory.
- The rule mirrors Advisor's "Unused/Empty App Service plan" recommendation (`Recommendation ID: 39a8510f-5bbf-4304-9bcd-4106c996473b`).
