---
title: Azure reservation utilisation reporting
source_url: https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/reservation-utilization
source_retrieved: 2026-04-29
source_sha256: 55ece21cef288f7bbf59f029898a179378e2395bd4587befcae62ab5fd830d99
cited_by:
  - underused_reservations
---

Microsoft Cost Management exposes reservation utilisation as a percentage on the reservation order. The page below documents the reporting surfaces but does **not** publish a single numeric "underused" threshold — the threshold is left to the customer to set per reservation via the alert feature.

## Microsoft's documented surfaces

> Each reservation shows the last known utilization percentage. Select the utilization percentage to see the utilization history and details.

> With reservation utilization alerts, you can promptly take remedial actions to ensure optimal utilization of your reservation purchases.

## What Microsoft does *not* publish

The reservation-utilisation reference page does **not** state a single percentage that constitutes "underused" — the threshold is configurable per-reservation. The closest Microsoft-published guidance is the Advisor recommendation [Configure automatic renewal for the expiring reservations](https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations#configure-automatic-renewal-for-the-expiring-reservations) (impact: High) and the FinOps Foundation guidance on commitment optimisation.

## Industry-standard thresholds (cited as informational, not as Microsoft authority)

The FinOps Foundation [Rate Optimization capability](https://www.finops.org/framework/capabilities/rate-optimization/) suggests reservation utilisation below **80% over a 30-day window** as a flag for review. The analyser uses this 80% / 30-day default and exposes it as a config value.

---

**How the rule uses this:**

- `underused_reservations` flags any reservation whose `utilizationPercentage` over the last 30 days is < 80%.
- Confidence: **Medium** — Microsoft does not publish a numeric threshold; we cite the FinOps Foundation default and surface the threshold in the report so reviewers can challenge it.
- `recommended_investigation` cites the Microsoft alert feature as the channel for resolving the finding, not a write action by us.
