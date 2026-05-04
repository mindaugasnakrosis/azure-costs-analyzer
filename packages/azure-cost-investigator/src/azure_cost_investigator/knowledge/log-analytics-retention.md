# Log Analytics retention & ingestion cost

## Authority

- [Azure Monitor Logs pricing (Microsoft)](https://azure.microsoft.com/en-us/pricing/details/monitor/)
- [Manage data retention in a Log Analytics workspace](https://learn.microsoft.com/azure/azure-monitor/logs/data-retention-archive)
- [Set daily cap on Log Analytics workspace](https://learn.microsoft.com/azure/azure-monitor/logs/daily-cap)
- [Log Analytics commitment tier pricing](https://learn.microsoft.com/azure/azure-monitor/logs/cost-logs)

## What costs money

A Log Analytics workspace bills on three independent axes:

1. **Ingestion** — £/GB ingested. Pay-As-You-Go retail in UK South is
   approximately **£2.05/GB** for the analytics tier; commitment tiers
   from 100 GB/day step down to roughly £1.45/GB.
2. **Interactive retention** — first 31 days are free, then **£0.10/GB/day**
   beyond that on the analytics tier. A workspace with 30 GB/day
   ingestion at 730-day retention is paying for ≈ 30 × 699 = 20,970 GB-days
   above the free band, or **~£60/month per GB/day of ingestion** on top
   of the ingestion charge alone.
3. **Archive tier** — long-term retention at roughly **£0.020/GB/month**,
   with restore-on-read pricing when queried. Microsoft's recommendation
   is to keep only "actively queried" data in interactive retention and
   move the rest to archive.

The default retention is 31 days (the free band). Anything above that is a
deliberate choice and should pay back in audit/compliance value.

## Detection signal

The `az monitor log-analytics workspace list` payload includes:

- `retentionInDays` — interactive retention. Free up to 31; charged above.
- `sku.name` — `PerGB2018` (current Pay-As-You-Go), `CapacityReservation`
  (commitment tier), or legacy `Standard` / `Premium` / `PerNode` /
  `Free`. Legacy SKUs are billed at higher rates and are subject to
  Microsoft deprecation timelines.
- `workspaceCapping.dailyQuotaGb` — `-1` means no cap; any positive
  number is the daily ingestion ceiling.
- `features.immediatePurgeDataOn30Days` — opt-in early purge for GDPR /
  privacy.

## When this tool flags a workspace

A finding is emitted when **any** of:

1. `retentionInDays > 31` and the workspace is on `PerGB2018` (the rule
   *can't* see the per-table archive split, so the figure is treated as
   an upper bound). **Severity**: Medium.
2. `sku.name` is one of `Standard`, `Premium`, `PerNode`, `Free`. These
   are legacy or capped SKUs. Microsoft's pricing page flags
   PerGB2018 / CapacityReservation as the supported families. **Severity**:
   Medium for legacy paid SKUs, Info for `Free` (no saving, but worth
   knowing the cap could be hit).
3. `workspaceCapping.dailyQuotaGb` is `-1` and `retentionInDays > 31`.
   Uncapped + extended retention is the configuration most likely to
   produce a surprise bill. **Severity**: Info (it's a governance flag,
   not a £ saving on its own).

## Savings band

Without per-workspace ingestion volume we cannot quote a precise £ figure.
The rule emits a band only when the consumption snapshot includes a
`Log Analytics` MeterCategory line for the workspace's resource ID; in
that case we apply:

- **Low**: `30d_gbp × 0.20`
- **High**: `30d_gbp × 0.40`

The factor reflects Microsoft's published guidance that **most workspaces
over 90-day retention can release 30–50%** of cost by moving cold data to
archive or shortening interactive retention. The figure is conservative
because table-level retention overrides may already be tighter than the
workspace default.

If consumption data is missing we still emit the finding (governance
value) but with no band.

## Confidence

**Medium**. The rule sees workspace-level retention but not per-table
overrides, doesn't know the customer's audit-compliance contract, and
can't tell which workspaces feed Microsoft Sentinel (which has different
default retention and pricing). Recommendation always asks the user to
confirm the compliance posture before reducing retention.
