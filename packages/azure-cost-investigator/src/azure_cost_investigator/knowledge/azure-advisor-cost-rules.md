---
title: Azure Advisor — cost recommendation reference
source_url: https://learn.microsoft.com/en-us/azure/advisor/advisor-reference-cost-recommendations
source_retrieved: 2026-04-29
source_sha256: 05df44c9ec80400d7cb5e024db557e41e79467edc0893255296300560b6801b4
cited_by:
  - orphaned_disks
  - unattached_public_ips
  - unused_app_service_plans
  - underused_reservations
  - old_snapshots
---

The Azure Advisor cost catalogue is the canonical taxonomy of Microsoft's cost recommendations. The analyser's rules deliberately mirror Advisor's titles and triggers so findings are cross-referenceable against the Advisor blade. Verbatim entries below are quoted from the catalogue.

## App Service — Unused/Empty App Service plan

> Your App Service plan has no apps running. Consider deleting the resource to save costs.
>
> ResourceType: microsoft.web/sites Recommendation ID: 39a8510f-5bbf-4304-9bcd-4106c996473b

## App Service — Right-size underutilized App Service plans

> We've analyzed the usage patterns of your app service plan over the past 7 days and identified low CPU usage. While certain scenarios can result in low utilization by design, you can often save money by choosing a less expensive SKU while retaining the same features.
>
> ResourceType: microsoft.web/sites Recommendation ID: cc9d34f5-f9b8-4d4f-9de7-98b45c698a49

## Virtual Machines — Right-size or shutdown underutilized virtual machines

> We've analyzed the usage patterns of your virtual machine and identified virtual machines with low usage. While certain scenarios can result in low utilization by design, you can often save money by managing the size and number of virtual machines.
>
> ResourceType: microsoft.compute/virtualmachines Recommendation ID: e10b1381-5f0a-47ff-8c7b-37bd13d7c974

## Virtual Machines — Review disks that aren't attached to a VM and evaluate if you still need the disks

> There are disks not attached to a VM. Evaluate if you still need them. Deleting a disk is irreversible. Create a snapshot before deletion and confirm the data is no longer needed.
>
> ResourceType: microsoft.compute/disks Recommendation ID: 48eda464-1485-4dcf-a674-d0905df5054a

## Virtual Machines — Use Standard Storage to store Managed Disks snapshots

> To save 60% of cost, we recommend storing your snapshots in Standard Storage, regardless of the storage type of the parent disk. This option is the default for Managed Disks snapshots. Migrate your snapshot from Premium to Standard Storage. Refer to Managed Disks pricing details.
>
> Potential benefits: 60% reduction in the snapshot cost for Managed Disks
>
> ResourceType: microsoft.compute/snapshots Recommendation ID: 702b474d-698f-4029-9f9d-4782c626923e

## Reservations — Configure automatic renewal for the expiring reservations

> Reservations shown below are expiring soon or recently expired. Your resources will continue to operate normally, however, you will be billed at the on-demand rates going forward. To optimize your costs, configure automatic renewal for these reservations or purchase a replacement manually.
>
> ResourceType: microsoft.capacity/reservationorders/reservations Recommendation ID: abb1f687-2d58-4197-8f5b-8882f05c04b8

## Reservations — Consider virtual machine reserved instance to save over the on-demand costs

> Based on your usage over the selected term and look-back period, we recommend reservations to maximize savings. Reservations apply automatically to matching deployments. Savings are estimated per subscription. Shared scope options are available during purchase.
>
> Impact: High
> ResourceType: microsoft.subscriptions/subscriptions Recommendation ID: 84b1a508-fc21-49da-979e-96894f1665df

## Storage — Premium storage for high transactions/TB ratio

> The customer can lower the bill if the transactions/TB ratio is high. Exact number would depend on transaction mix and region but anywhere >30 or 35 TPB/TB may be good candidates to at least evaluate a move to premium storage.

---

**How rules use this:** each cost rule's `rule_id` corresponds to the Advisor recommendation it mirrors. The analyser cross-validates against `consumption.json` and `advisor.json` from the snapshot — a finding present in both the rule and Advisor's response is High confidence by construction.
