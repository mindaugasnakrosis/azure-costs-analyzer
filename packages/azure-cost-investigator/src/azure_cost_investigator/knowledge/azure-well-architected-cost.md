---
title: Azure Well-Architected Framework — Cost Optimization design principles
source_url: https://learn.microsoft.com/en-us/azure/well-architected/cost-optimization/principles
source_retrieved: 2026-04-29
source_sha256: 65408d463635b10a8a155c3fa38c59f419ba76bae50a4154d089ff79bb84fb1b
cited_by:
  - dev_skus_in_prod
  - oversized_vms
  - underused_reservations
---

The Cost Optimization pillar of the Microsoft Azure Well-Architected Framework defines five design principles for cost-optimised workloads. The verbatim "Goal" statements below frame the analyser's recommendations.

## Principle 1 — Develop cost-management discipline

> Build a team culture that has awareness of budget, expenses, reporting, and cost tracking.

> Cost optimization is conducted at various levels of the organization. It's important to understand how your workload cost is aligned with organizational FinOps practices. A view into the business units, resource organization, and centralized audit policies allows you to adopt a standardized financial system.

## Principle 2 — Design with a cost-efficiency mindset

> Spend only on what you need to achieve the highest return on your investments.

> Every architectural decision has direct and indirect financial implications. Understand the costs associated with build versus buy options, technology choices, the billing model and licensing, training, operations, and so on.

> Treat different SDLC environments differently, and deploy the right number of environments. […] You can save money by understanding that not all environments need to simulate production. Nonproduction environments can have different features, SKUs, instance counts, and even logging.

## Principle 3 — Design for usage optimization

> Maximize the use of resources and operations. Apply them to the negotiated functional and nonfunctional requirements of the solution.

> Services and offerings provide various capabilities and pricing tiers. After you purchase a set of features, avoid underutilizing them. Find ways to maximize your investment in the tier. Likewise, continuously evaluate billing models to find those that better align to your usage, based on current production workloads.

## Principle 4 — Design for rate optimization

> Increase efficiency without redesigning, renegotiating, or sacrificing functional or nonfunctional requirements.

> Identify resources that have stable or predictable usage patterns over time. Optimize costs by prepurchasing these resources to take advantage of available discounts.

> Use fixed-price billing instead of consumption-based billing for a resource when its utilization is high and predictable and a comparable SKU or billing option is available.

## Principle 5 — Monitor and optimize over time

> Continuously right-size investment as your workload evolves with the ecosystem.

> Decommission resources that are underutilized, unused, obsolete, or can be replaced with more efficient alternatives. Regularly delete unnecessary data. By resizing or removing underutilized resources, or even changing SKUs, you can reduce costs. Shutting down unused resources and deleting data when you no longer need it reduces waste and frees up funds so you can invest them elsewhere.

---

**How rules use this:** Principle 5 is the explicit authority behind "decommission" findings. Principle 2's "treat SDLC environments differently" is the basis for `dev_skus_in_prod`. Principle 4 backs the reservations rule (low-utilisation reservations indicate the wrong tier choice, not a remediation gap).
