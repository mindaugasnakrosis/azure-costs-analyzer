---
title: Identifying unattached Azure managed disks
source_url: https://learn.microsoft.com/en-us/azure/virtual-machines/disks-find-unattached-portal
source_retrieved: 2026-04-29
source_sha256: b3ce58f61fde9ea0833105c58eaff2e19063f330b23658dd5c6463548b893d41
cited_by:
  - orphaned_disks
---

Microsoft documents that disks survive the deletion of their parent VM and continue to bill until manually removed. The verbatim text below grounds the `orphaned_disks` rule and the language it uses in `recommended_investigation`.

## What "unattached" means

> When you delete a virtual machine (VM) in Azure, by default, any disks that are attached to the VM aren't deleted. This helps to prevent data loss due to the unintentional deletion of VMs. After a VM is deleted, you will continue to pay for unattached disks. This article shows you how to find and delete any unattached disks using the Azure portal, and reduce unnecessary costs. Deletions are permanent, you will not be able to recover data once you delete a disk.

## How the portal exposes the state

> On the **Disks** blade, you are presented with a list of all your disks. Select the disk you'd like to delete, this brings you to the individual disk's blade. On the individual disk's blade, confirm the disk state is unattached, then select **Delete**.

## Programmatic signal

The Azure Resource Manager managed disk resource exposes `diskState`. Values that indicate an orphan candidate, per Microsoft's published [Managed Disks REST API](https://learn.microsoft.com/en-us/rest/api/compute/disks):

- `Unattached` — disk is provisioned but `managedBy` is null. Billing continues.
- `Reserved` — disk was attached but the VM is deleted; reattachment may still be possible.

A disk in either state with `managedBy == null` is the analyser's strict orphan definition.

---

**How the rule uses this:**

- `orphaned_disks` flags any managed disk where `diskState in {Unattached, Reserved}` and `managedBy is null`.
- Confidence: **High** — the signal is deterministic from inventory, no metrics required.
- `recommended_investigation` quotes Microsoft's irreversibility warning verbatim: *"Deletions are permanent, you will not be able to recover data once you delete a disk."* The analyser does not recommend deletion; it recommends the snapshot-then-confirm investigation Microsoft documents.
