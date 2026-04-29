---
title: Azure Blob Storage access tiers — minimum durations and early-deletion penalties
source_url: https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview
source_retrieved: 2026-04-29
source_sha256: 3717f2ae0e7c2649f01fec7cf420ed9b0e7ee475eff0c3bd13abfc51a3d65d04
cited_by:
  - legacy_storage_redundancy
  - old_snapshots
---

Microsoft documents four blob access tiers (Hot / Cool / Cold / Archive) and explicit minimum-storage-duration penalties on the cooler tiers. The cost analyser uses these durations to evaluate snapshot retention and storage-account redundancy choices.

## Tier definitions (verbatim)

> - **Hot tier** - An online tier optimized for storing data that is accessed or modified frequently. The hot tier has the highest storage costs, but the lowest access costs.
> - **Cool tier** - An online tier optimized for storing data that is infrequently accessed or modified. Data in the cool tier should be stored for a minimum of **30** days. The cool tier has lower storage costs and higher access costs compared to the hot tier.
> - **Cold tier** - An online tier optimized for storing data that is rarely accessed or modified, but still requires fast retrieval. Data in the cold tier should be stored for a minimum of **90** days. The cold tier has lower storage costs and higher access costs compared to the cool tier.
> - **Archive tier** - An offline tier optimized for storing data that is rarely accessed, and that has flexible latency requirements, on the order of hours. Data in the archive tier should be stored for a minimum of **180** days.

## Early-deletion penalty (verbatim)

> Blobs are subject to an early deletion penalty if they are deleted, overwritten or moved to a different tier before the minimum number of days required by the tier have transpired. For example, a blob in the cool tier in a general-purpose v2 account is subject to an early deletion penalty if it's deleted or moved to a different tier before 30 days has elapsed. For a blob in the cold tier, the deletion penalty applies if it's deleted or moved to a different tier before 90 days has elapsed. This charge is prorated.

## Archive-tier redundancy restriction (verbatim)

> Only storage accounts that are configured for LRS, GRS, or RA-GRS support moving blobs to the archive tier. The archive tier isn't supported for ZRS, GZRS, or RA-GZRS accounts.

## Snapshot pricing — verbatim from the Advisor catalogue

(See `azure-advisor-cost-rules.md`.)

> To save 60% of cost, we recommend storing your snapshots in Standard Storage, regardless of the storage type of the parent disk. This option is the default for Managed Disks snapshots. Migrate your snapshot from Premium to Standard Storage.

---

**How rules use this:**

- `old_snapshots` quotes the Advisor "Use Standard Storage for snapshots" rule and flags any disk snapshot whose creation timestamp is older than the configured retention threshold (default 90 days) AND whose underlying storage account is Premium.
- `legacy_storage_redundancy` flags storage accounts whose redundancy SKU is in `{LRS, GRS, RA-GRS}` *and* whose access tier is Hot when the access pattern in `consumption.json` indicates the data has not been read in the last 30 days — Microsoft's published threshold for Cool eligibility.
